"""
MCP Configuration Validator — проверка структуры и корректности .cursor/mcp.json.

Проверяет:
- Структуру JSON
- Наличие обязательных полей
- Корректность URL/command для серверов
- Доступность переменных окружения
- Согласованность конфигурации
"""
import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("mcp.config.validator")
except Exception:
    import logging
    logger = logging.getLogger("mcp.config.validator")


class MCPConfigValidator:
    """Валидатор конфигурации MCP."""
    
    def __init__(self, config_path: Path = None):
        """
        Инициализация валидатора.
        
        Args:
            config_path: Путь к файлу конфигурации MCP
        """
        if config_path is None:
            config_path = Path(".cursor/mcp.json")
        
        self.config_path = config_path
        self.config = None
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.info: List[Dict[str, Any]] = []
    
    def load_config(self) -> bool:
        """
        Загружает конфигурацию из файла.
        
        Returns:
            True если конфигурация успешно загружена
        """
        if not self.config_path.exists():
            self.errors.append({
                "component": "config_file",
                "message": f"Файл конфигурации не найден: {self.config_path}",
                "severity": "error",
            })
            return False
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            return True
        except json.JSONDecodeError as e:
            self.errors.append({
                "component": "config_file",
                "message": f"Ошибка парсинга JSON: {e}",
                "severity": "error",
            })
            return False
        except Exception as e:
            self.errors.append({
                "component": "config_file",
                "message": f"Ошибка чтения файла: {e}",
                "severity": "error",
            })
            return False
    
    def validate_structure(self) -> bool:
        """
        Проверяет базовую структуру конфигурации.
        
        Returns:
            True если структура корректна
        """
        if not self.config:
            return False
        
        valid = True
        
        # Проверка обязательных секций
        required_sections = ["mcpServers"]
        
        for section in required_sections:
            if section not in self.config:
                self.errors.append({
                    "component": "structure",
                    "message": f"Отсутствует обязательная секция: {section}",
                    "severity": "error",
                })
                valid = False
        
        # Проверка версии
        if "version" not in self.config:
            self.warnings.append({
                "component": "structure",
                "message": "Отсутствует поле 'version' в конфигурации",
                "severity": "warning",
            })
        
        return valid
    
    def validate_server_config(self, server_name: str, server_config: Dict[str, Any]) -> bool:
        """
        Валидирует конфигурацию одного MCP-сервера.
        
        Args:
            server_name: Имя сервера
            server_config: Конфигурация сервера
            
        Returns:
            True если конфигурация корректна
        """
        valid = True
        
        # Проверка наличия способа запуска (command или url)
        has_command = "command" in server_config
        has_url = "url" in server_config
        
        if not has_command and not has_url:
            self.errors.append({
                "component": f"server.{server_name}",
                "message": "Сервер должен иметь либо 'command', либо 'url'",
                "severity": "error",
            })
            valid = False
        
        if has_command and has_url:
            self.warnings.append({
                "component": f"server.{server_name}",
                "message": "У сервера указаны и 'command', и 'url' — будет использоваться 'command'",
                "severity": "warning",
            })
        
        # Проверка command-серверов
        if has_command:
            if "args" not in server_config:
                self.warnings.append({
                    "component": f"server.{server_name}",
                    "message": "У command-сервера отсутствуют 'args'",
                    "severity": "warning",
                })
            
            # Проверка существования команды
            command = server_config["command"]
            if command not in ["python", "uvicorn", "node", "npm"]:
                # Проверяем, доступна ли команда в системе
                import shutil
                if not shutil.which(command):
                    self.warnings.append({
                        "component": f"server.{server_name}",
                        "message": f"Команда '{command}' не найдена в PATH",
                        "severity": "warning",
                    })
        
        # Проверка URL-серверов
        if has_url:
            url = server_config["url"]
            if not url.startswith(("http://", "https://", "ws://", "wss://")):
                self.errors.append({
                    "component": f"server.{server_name}",
                    "message": f"Некорректный URL: {url}",
                    "severity": "error",
                })
                valid = False
        
        # Проверка enabled
        if "enabled" not in server_config:
            self.warnings.append({
                "component": f"server.{server_name}",
                "message": "Отсутствует поле 'enabled' (по умолчанию считается false)",
                "severity": "warning",
            })
        
        # Проверка api_key_env для внешних сервисов
        if has_url and "api_key_env" in server_config:
            env_var = server_config["api_key_env"]
            if not os.getenv(env_var):
                self.warnings.append({
                    "component": f"server.{server_name}",
                    "message": f"Переменная окружения '{env_var}' не установлена",
                    "severity": "warning",
                })
        
        # Проверка capabilities
        if "capabilities" in server_config:
            if not isinstance(server_config["capabilities"], list):
                self.errors.append({
                    "component": f"server.{server_name}",
                    "message": "Поле 'capabilities' должно быть списком",
                    "severity": "error",
                })
                valid = False
        
        return valid
    
    def validate_all_servers(self) -> bool:
        """
        Валидирует все MCP-серверы.
        
        Returns:
            True если все серверы корректны
        """
        if not self.config or "mcpServers" not in self.config:
            return False
        
        servers = self.config["mcpServers"]
        valid = True
        
        if not isinstance(servers, dict):
            self.errors.append({
                "component": "mcpServers",
                "message": "Секция 'mcpServers' должна быть объектом",
                "severity": "error",
            })
            return False
        
        if not servers:
            self.warnings.append({
                "component": "mcpServers",
                "message": "Не настроено ни одного MCP-сервера",
                "severity": "warning",
            })
        
        for server_name, server_config in servers.items():
            if not isinstance(server_config, dict):
                self.errors.append({
                    "component": f"server.{server_name}",
                    "message": "Конфигурация сервера должна быть объектом",
                    "severity": "error",
                })
                valid = False
                continue
            
            if not self.validate_server_config(server_name, server_config):
                valid = False
        
        # Статистика
        enabled_servers = [
            name for name, cfg in servers.items()
            if isinstance(cfg, dict) and cfg.get("enabled", False)
        ]
        
        self.info.append({
            "component": "mcpServers",
            "message": f"Найдено серверов: {len(servers)}, включено: {len(enabled_servers)}",
            "severity": "info",
        })
        
        return valid
    
    def validate_services(self) -> bool:
        """
        Валидирует секцию services.
        
        Returns:
            True если services корректны
        """
        if not self.config or "services" not in self.config:
            return True  # services опциональны
        
        services = self.config["services"]
        
        if not isinstance(services, dict):
            self.errors.append({
                "component": "services",
                "message": "Секция 'services' должна быть объектом",
                "severity": "error",
            })
            return False
        
        return True
    
    def validate_connectivity(self) -> bool:
        """
        Валидирует секцию connectivity.
        
        Returns:
            True если connectivity корректна
        """
        if not self.config or "connectivity" not in self.config:
            return True  # connectivity опциональна
        
        connectivity = self.config["connectivity"]
        
        if not isinstance(connectivity, dict):
            self.errors.append({
                "component": "connectivity",
                "message": "Секция 'connectivity' должна быть объектом",
                "severity": "error",
            })
            return False
        
        return True
    
    def validate_metadata(self) -> bool:
        """
        Валидирует секцию metadata.
        
        Returns:
            True если metadata корректна
        """
        if not self.config or "metadata" not in self.config:
            return True  # metadata опциональна
        
        metadata = self.config["metadata"]
        
        if not isinstance(metadata, dict):
            self.errors.append({
                "component": "metadata",
                "message": "Секция 'metadata' должна быть объектом",
                "severity": "error",
            })
            return False
        
        # Проверка уровня
        if "level" in metadata:
            level = metadata["level"]
            if not isinstance(level, int) or level < 1 or level > 5:
                self.warnings.append({
                    "component": "metadata",
                    "message": f"Некорректный уровень: {level} (должен быть от 1 до 5)",
                    "severity": "warning",
                })
        
        return True
    
    def validate_all(self) -> Dict[str, Any]:
        """
        Выполняет полную валидацию конфигурации.
        
        Returns:
            Результаты валидации
        """
        self.errors.clear()
        self.warnings.clear()
        self.info.clear()
        
        if not self.load_config():
            return self._build_result()
        
        self.validate_structure()
        self.validate_all_servers()
        self.validate_services()
        self.validate_connectivity()
        self.validate_metadata()
        
        return self._build_result()
    
    def _build_result(self) -> Dict[str, Any]:
        """
        Строит итоговый результат валидации.
        
        Returns:
            Словарь с результатами валидации
        """
        has_errors = len(self.errors) > 0
        has_warnings = len(self.warnings) > 0
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config_path": str(self.config_path),
            "valid": not has_errors,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "info": len(self.info),
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
        }


def main():
    """CLI для валидации конфигурации MCP."""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Configuration Validator")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(".cursor/mcp.json"),
        help="Путь к файлу конфигурации MCP",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Сохранить результаты в JSON",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=None,
        help="Сохранить результаты в Markdown",
    )
    parser.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Завершить с ошибкой при обнаружении проблем",
    )
    
    args = parser.parse_args()
    
    validator = MCPConfigValidator(args.config)
    results = validator.validate_all()
    
    # Вывод результатов
    print("\n" + "=" * 70)
    print("MCP Configuration Validation")
    print("=" * 70)
    print(f"Config: {results['config_path']}")
    print(f"Timestamp: {results['timestamp']}")
    print()
    
    # Ошибки
    if results["errors"]:
        print(f"❌ Ошибки ({results['summary']['errors']}):")
        for error in results["errors"]:
            print(f"  [{error['component']}] {error['message']}")
        print()
    
    # Предупреждения
    if results["warnings"]:
        print(f"⚠️  Предупреждения ({results['summary']['warnings']}):")
        for warning in results["warnings"]:
            print(f"  [{warning['component']}] {warning['message']}")
        print()
    
    # Информация
    if results["info"]:
        print(f"ℹ️  Информация ({results['summary']['info']}):")
        for info in results["info"]:
            print(f"  [{info['component']}] {info['message']}")
        print()
    
    # Итог
    if results["valid"]:
        print("✅ Конфигурация MCP валидна!")
    else:
        print("❌ Конфигурация MCP содержит ошибки")
    
    print("=" * 70)
    print()
    
    # Сохранение JSON
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"📄 JSON отчёт сохранён: {args.output_json}")
    
    # Сохранение Markdown
    if args.output_markdown:
        _generate_markdown_report(results, args.output_markdown)
        print(f"📄 Markdown отчёт сохранён: {args.output_markdown}")
    
    # Exit code
    if args.fail_on_errors and not results["valid"]:
        return 1
    
    return 0


def _generate_markdown_report(results: Dict[str, Any], output_path: Path) -> None:
    """Генерирует Markdown отчёт."""
    lines = [
        "# MCP Configuration Validation Report",
        "",
        f"**Timestamp:** {results['timestamp']}",
        f"**Config:** `{results['config_path']}`",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- **Valid:** {'✅ Yes' if results['valid'] else '❌ No'}",
        f"- **Errors:** {results['summary']['errors']}",
        f"- **Warnings:** {results['summary']['warnings']}",
        f"- **Info:** {results['summary']['info']}",
        "",
    ]
    
    if results["errors"]:
        lines.extend([
            "---",
            "",
            "## ❌ Errors",
            "",
        ])
        for error in results["errors"]:
            lines.append(f"### [{error['component']}]")
            lines.append(f"**{error['message']}**")
            lines.append("")
    
    if results["warnings"]:
        lines.extend([
            "---",
            "",
            "## ⚠️ Warnings",
            "",
        ])
        for warning in results["warnings"]:
            lines.append(f"### [{warning['component']}]")
            lines.append(f"**{warning['message']}**")
            lines.append("")
    
    if results["info"]:
        lines.extend([
            "---",
            "",
            "## ℹ️ Information",
            "",
        ])
        for info in results["info"]:
            lines.append(f"- **[{info['component']}]** {info['message']}")
        lines.append("")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())












