"""
SAFE checks — проверки безопасности и функциональности.
"""
import os
import re
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("validation.safe")
except Exception:
    import logging
    logger = logging.getLogger("validation.safe")


class SAFEChecker:
    """Класс для выполнения SAFE проверок."""
    
    def __init__(self, policies_path: Optional[Path] = None):
        """Инициализация с загрузкой политик."""
        if policies_path is None:
            policies_path = Path(__file__).parent / "policies.yaml"
        
        self.policies = self._load_policies(policies_path)
        self.pii_patterns = self._compile_patterns()
        
    def _load_policies(self, path: Path) -> Dict[str, Any]:
        """Загружает политики из YAML."""
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            return {}
        except Exception as e:
            logger.error("failed_to_load_policies", error=str(e), path=str(path))
            return {}
    
    def _compile_patterns(self) -> List[Tuple[re.Pattern, str]]:
        """Компилирует PII паттерны."""
        patterns = []
        if "pii_mask" in self.policies and self.policies["pii_mask"].get("enabled"):
            for pii_rule in self.policies["pii_mask"].get("patterns", []):
                try:
                    pattern = re.compile(pii_rule["pattern"], re.IGNORECASE)
                    replacement = pii_rule.get("replacement", "[REDACTED]")
                    patterns.append((pattern, replacement))
                except Exception as e:
                    logger.warning("failed_to_compile_pattern", pattern=pii_rule.get("pattern"), error=str(e))
        return patterns
    
    def check_pii_in_text(self, text: str) -> Tuple[bool, List[str], str]:
        """
        Проверяет наличие PII в тексте.
        
        Returns:
            (has_pii, detected_types, masked_text)
        """
        if not text:
            return False, [], text
        
        masked_text = text
        detected = []
        
        for pattern, replacement in self.pii_patterns:
            matches = pattern.findall(text)
            if matches:
                detected.append(pattern.pattern)
                masked_text = pattern.sub(replacement, masked_text)
        
        return len(detected) > 0, detected, masked_text
    
    def check_secrets_in_logs(self, log_text: str) -> Tuple[bool, List[str]]:
        """
        Проверяет наличие секретов в логах.
        
        Returns:
            (has_secrets, detected_types)
        """
        if not self.policies.get("log_security", {}).get("mask_secrets"):
            return False, []
        
        detected = []
        secret_patterns = self.policies.get("log_security", {}).get("secret_patterns", [])
        
        for rule in secret_patterns:
            pattern = re.compile(rule["pattern"], re.IGNORECASE)
            if pattern.search(log_text):
                detected.append(rule.get("replacement", "SECRET"))
        
        return len(detected) > 0, detected
    
    def check_domain_access(self, url: str) -> Tuple[bool, str]:
        """
        Проверяет, разрешён ли доступ к домену.
        
        Returns:
            (is_allowed, reason)
        """
        if not self.policies.get("domain_allowlist", {}).get("enabled"):
            return True, "Domain allowlist disabled"
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split("/")[0]
            
            mode = self.policies.get("domain_allowlist", {}).get("mode", "whitelist")
            allowed = self.policies.get("domain_allowlist", {}).get("allowed", [])
            blocked = self.policies.get("domain_allowlist", {}).get("blocked", [])
            
            # Проверка blacklist
            for blocked_pattern in blocked:
                if self._match_pattern(domain, blocked_pattern):
                    return False, f"Domain blocked: {domain}"
            
            # Проверка whitelist
            if mode == "whitelist":
                for allowed_pattern in allowed:
                    if self._match_pattern(domain, allowed_pattern):
                        return True, f"Domain allowed: {domain}"
                return False, f"Domain not in allowlist: {domain}"
            
            return True, "Access granted"
            
        except Exception as e:
            logger.warning("domain_check_failed", url=url, error=str(e))
            return False, f"Invalid URL: {str(e)}"
    
    def _match_pattern(self, domain: str, pattern: str) -> bool:
        """Проверяет соответствие домена паттерну (поддерживает wildcards)."""
        if "*" in pattern:
            pattern_re = pattern.replace(".", r"\.").replace("*", r".*")
            return bool(re.match(pattern_re, domain, re.IGNORECASE))
        return domain.lower() == pattern.lower()
    
    def check_file_size(self, file_path: Path) -> Tuple[bool, str]:
        """
        Проверяет размер файла.
        
        Returns:
            (is_valid, reason)
        """
        if not self.policies.get("file_validation", {}).get("enabled"):
            return True, "File validation disabled"
        
        max_size_mb = self.policies.get("file_validation", {}).get("max_file_size_mb", 100)
        max_size_bytes = max_size_mb * 1024 * 1024
        
        try:
            file_size = file_path.stat().st_size
            if file_size > max_size_bytes:
                return False, f"File too large: {file_size / 1024 / 1024:.2f}MB > {max_size_mb}MB"
            return True, "File size OK"
        except Exception as e:
            return False, f"Cannot check file size: {str(e)}"
    
    def check_file_extension(self, file_path: Path) -> Tuple[bool, str]:
        """
        Проверяет расширение файла.
        
        Returns:
            (is_valid, reason)
        """
        if not self.policies.get("file_validation", {}).get("enabled"):
            return True, "File validation disabled"
        
        ext = file_path.suffix.lower()
        allowed = self.policies.get("file_validation", {}).get("allowed_extensions", [])
        blocked = self.policies.get("file_validation", {}).get("blocked_extensions", [])
        
        if ext in blocked:
            return False, f"Blocked extension: {ext}"
        
        if allowed and ext not in allowed:
            return False, f"Extension not allowed: {ext}"
        
        return True, "Extension OK"
    
    def validate_payload(self, payload: Dict[str, Any], require_pii_mask: bool = True) -> Dict[str, Any]:
        """
        Валидирует payload (входящий или исходящий).
        
        Returns:
            Результат валидации
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "masked_payload": payload,
        }
        
        # Проверка размера
        payload_str = json.dumps(payload)
        max_size = self.policies.get("outbound_safeguards", {}).get("max_payload_size_mb", 10) * 1024 * 1024
        if len(payload_str.encode("utf-8")) > max_size:
            result["valid"] = False
            result["errors"].append(f"Payload too large: {len(payload_str)} bytes")
        
        # Проверка PII
        if require_pii_mask and self.policies.get("outbound_safeguards", {}).get("require_pii_mask"):
            payload_str = json.dumps(payload)
            has_pii, detected, masked = self.check_pii_in_text(payload_str)
            if has_pii:
                result["warnings"].append(f"PII detected: {detected}")
                try:
                    result["masked_payload"] = json.loads(masked)
                except:
                    result["masked_payload"] = payload  # Fallback
        
        return result


def get_safe_checker() -> SAFEChecker:
    """Фабричная функция для получения SAFE checker."""
    return SAFEChecker()











