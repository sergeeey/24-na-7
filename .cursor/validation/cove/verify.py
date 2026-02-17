"""
CoVe (Consistency & Verification) — проверка согласованности данных.
"""
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import re

try:
    import jsonschema
    from jsonschema import validate, ValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    ValidationError = Exception

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("validation.cove")
except Exception:
    import logging
    logger = logging.getLogger("validation.cove")


class CoVeVerifier:
    """Класс для выполнения CoVe проверок."""
    
    def __init__(self, schemas_path: Optional[Path] = None):
        """Инициализация с загрузкой схем."""
        if schemas_path is None:
            schemas_path = Path(__file__).parent / "schema_contracts.yaml"
        
        self.schemas = self._load_schemas(schemas_path)
        
    def _load_schemas(self, path: Path) -> Dict[str, Any]:
        """Загружает схемы из YAML."""
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    return data.get("schemas", {})
            return {}
        except Exception as e:
            logger.error("failed_to_load_schemas", error=str(e), path=str(path))
            return {}
    
    def verify_schema(self, data: Dict[str, Any], schema_name: str) -> Tuple[bool, List[str]]:
        """
        Проверяет данные по JSONSchema.
        
        Returns:
            (is_valid, errors)
        """
        if not HAS_JSONSCHEMA:
            logger.warning("jsonschema_not_installed")
            return True, ["jsonschema library not available"]
        
        if schema_name not in self.schemas:
            return False, [f"Schema '{schema_name}' not found"]
        
        schema = self.schemas[schema_name]
        
        try:
            validate(instance=data, schema=schema)
            return True, []
        except ValidationError as e:
            errors = [f"{e.path}: {e.message}"]
            return False, errors
        except Exception as e:
            return False, [f"Validation error: {str(e)}"]
    
    def verify_source_references(self, claim: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Проверяет корректность ссылок на источники.
        
        Returns:
            (is_valid, errors)
        """
        errors = []
        source_urls = claim.get("source_urls", [])
        
        # Проверка формата URL
        url_pattern = re.compile(
            r'^https?://'  # http:// или https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # доменное имя
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
            r'(?::\d+)?'  # порт
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        
        for url in source_urls:
            if not isinstance(url, str):
                errors.append(f"Source URL must be string: {url}")
            elif not url_pattern.match(url):
                errors.append(f"Invalid URL format: {url}")
        
        return len(errors) == 0, errors
    
    def verify_timestamps(self, data: Dict[str, Any], required_fields: List[str]) -> Tuple[bool, List[str]]:
        """
        Проверяет корректность timestamp полей.
        
        Returns:
            (is_valid, errors)
        """
        errors = []
        
        for field in required_fields:
            if field not in data:
                continue
            
            timestamp_str = data[field]
            
            # Проверяем формат ISO 8601
            try:
                datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                errors.append(f"Invalid timestamp format in '{field}': {timestamp_str}")
        
        return len(errors) == 0, errors
    
    def verify_confidence_range(self, data: Dict[str, Any], confidence_fields: List[str]) -> Tuple[bool, List[str]]:
        """
        Проверяет, что confidence значения в диапазоне [0, 1].
        
        Returns:
            (is_valid, errors)
        """
        errors = []
        
        for field in confidence_fields:
            if field not in data:
                continue
            
            value = data[field]
            
            if not isinstance(value, (int, float)):
                errors.append(f"Confidence field '{field}' must be number: {type(value)}")
            elif not (0.0 <= value <= 1.0):
                errors.append(f"Confidence field '{field}' out of range [0, 1]: {value}")
        
        return len(errors) == 0, errors
    
    def verify_claim(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        """
        Полная проверка Claim.
        
        Returns:
            Результат проверки
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
        }
        
        # Проверка схемы
        schema_valid, schema_errors = self.verify_schema(claim, "claim")
        if not schema_valid:
            result["valid"] = False
            result["errors"].extend(schema_errors)
        
        # Проверка ссылок на источники
        refs_valid, refs_errors = self.verify_source_references(claim)
        if not refs_valid:
            result["valid"] = False
            result["errors"].extend(refs_errors)
        
        # Проверка timestamps
        ts_valid, ts_errors = self.verify_timestamps(claim, ["extracted_at"])
        if not ts_valid:
            result["valid"] = False
            result["errors"].extend(ts_errors)
        
        # Проверка confidence
        conf_valid, conf_errors = self.verify_confidence_range(claim, ["confidence"])
        if not conf_valid:
            result["valid"] = False
            result["errors"].extend(conf_errors)
        
        return result
    
    def verify_validated_claim(self, validated_claim: Dict[str, Any]) -> Dict[str, Any]:
        """
        Полная проверка ValidatedClaim.
        
        Returns:
            Результат проверки
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
        }
        
        # Проверка схемы
        schema_valid, schema_errors = self.verify_schema(validated_claim, "validated_claim")
        if not schema_valid:
            result["valid"] = False
            result["errors"].extend(schema_errors)
        
        # Проверка внутреннего claim
        if "claim" in validated_claim:
            claim_result = self.verify_claim(validated_claim["claim"])
            if not claim_result["valid"]:
                result["valid"] = False
                result["errors"].extend([f"Claim validation: {e}" for e in claim_result["errors"]])
        
        # Проверка validation_status
        status = validated_claim.get("validation_status")
        if status not in ["supported", "refuted", "uncertain"]:
            result["valid"] = False
            result["errors"].append(f"Invalid validation_status: {status}")
        
        # Проверка timestamps
        ts_valid, ts_errors = self.verify_timestamps(validated_claim, ["validated_at"])
        if not ts_valid:
            result["valid"] = False
            result["errors"].extend(ts_errors)
        
        # Проверка confidence значений
        conf_valid, conf_errors = self.verify_confidence_range(
            validated_claim,
            ["critic_confidence", "calibrated_confidence"]
        )
        if not conf_valid:
            result["valid"] = False
            result["errors"].extend(conf_errors)
        
        return result


def get_cove_verifier() -> CoVeVerifier:
    """Фабричная функция для получения CoVe verifier."""
    return CoVeVerifier()











