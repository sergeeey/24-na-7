"""
Plugin Gateway — система подключения внешних MCP плагинов.

Позволяет Reflexio подключать дополнительные источники данных (Twitter, YouTube, Patents и т.д.).
"""
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.plugins")
except Exception:
    import logging
    logger = logging.getLogger("osint.plugins")


class Plugin:
    """Базовый класс для OSINT плагинов."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.enabled = False
    
    def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Выполняет поиск через плагин.
        
        Args:
            query: Поисковый запрос
            **kwargs: Дополнительные параметры
            
        Returns:
            Список результатов поиска
        """
        raise NotImplementedError
    
    def validate_config(self) -> bool:
        """Проверяет конфигурацию плагина."""
        return True


class PluginRegistry:
    """Реестр OSINT плагинов."""
    
    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
    
    def register(self, plugin: Plugin):
        """Регистрирует плагин."""
        self.plugins[plugin.name] = plugin
        logger.info("plugin_registered", name=plugin.name)
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Получает плагин по имени."""
        return self.plugins.get(name)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """Возвращает список всех плагинов."""
        return [
            {
                "name": p.name,
                "description": p.description,
                "enabled": p.enabled,
            }
            for p in self.plugins.values()
        ]
    
    def enable_plugin(self, name: str) -> bool:
        """Включает плагин."""
        plugin = self.plugins.get(name)
        if plugin:
            plugin.enabled = True
            logger.info("plugin_enabled", name=name)
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """Выключает плагин."""
        plugin = self.plugins.get(name)
        if plugin:
            plugin.enabled = False
            logger.info("plugin_disabled", name=name)
            return True
        return False


# Глобальный реестр
_plugin_registry = PluginRegistry()


def register_plugin(plugin: Plugin):
    """Регистрирует плагин в глобальном реестре."""
    _plugin_registry.register(plugin)


def get_plugin(name: str) -> Optional[Plugin]:
    """Получает плагин из глобального реестра."""
    return _plugin_registry.get_plugin(name)


def search_with_plugins(query: str, plugin_names: Optional[List[str]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Выполняет поиск через несколько плагинов.
    
    Args:
        query: Поисковый запрос
        plugin_names: Список имён плагинов (если None, используются все включённые)
        
    Returns:
        Словарь {plugin_name: [results]}
    """
    results = {}
    
    plugins_to_use = []
    
    if plugin_names:
        plugins_to_use = [
            _plugin_registry.get_plugin(name)
            for name in plugin_names
            if _plugin_registry.get_plugin(name) and _plugin_registry.get_plugin(name).enabled
        ]
    else:
        plugins_to_use = [p for p in _plugin_registry.plugins.values() if p.enabled]
    
    for plugin in plugins_to_use:
        try:
            plugin_results = plugin.search(query)
            results[plugin.name] = plugin_results
            logger.debug("plugin_search_completed", plugin=plugin.name, results=len(plugin_results))
        except Exception as e:
            logger.error("plugin_search_failed", plugin=plugin.name, error=str(e))
            results[plugin.name] = []
    
    return results


# Пример плагина-заглушки для демонстрации
class TwitterPlugin(Plugin):
    """Плагин для поиска в Twitter (заглушка)."""
    
    def __init__(self):
        super().__init__("twitter", "Twitter search plugin (requires API key)")
    
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Поиск в Twitter."""
        # TODO: Интеграция с Twitter API
        logger.warning("twitter_plugin_not_implemented")
        return []


class YouTubePlugin(Plugin):
    """Плагин для поиска в YouTube (заглушка)."""
    
    def __init__(self):
        super().__init__("youtube", "YouTube search plugin (requires API key)")
    
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Поиск в YouTube."""
        # TODO: Интеграция с YouTube Data API
        logger.warning("youtube_plugin_not_implemented")
        return []


class PatentsPlugin(Plugin):
    """Плагин для поиска патентов (заглушка)."""
    
    def __init__(self):
        super().__init__("patents", "Patent search plugin (USPTO/EPO)")
    
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Поиск патентов."""
        # TODO: Интеграция с патентными базами
        logger.warning("patents_plugin_not_implemented")
        return []


def load_default_plugins():
    """Загружает плагины по умолчанию."""
    register_plugin(TwitterPlugin())
    register_plugin(YouTubePlugin())
    register_plugin(PatentsPlugin())


def main():
    """CLI для Plugin Gateway."""
    import argparse
    
    parser = argparse.ArgumentParser(description="OSINT Plugin Gateway")
    parser.add_argument(
        "action",
        choices=["list", "enable", "disable", "search"],
        help="Действие",
    )
    parser.add_argument(
        "--plugin",
        help="Имя плагина",
    )
    parser.add_argument(
        "--query",
        help="Поисковый запрос (для search)",
    )
    
    args = parser.parse_args()
    
    # Загружаем плагины
    load_default_plugins()
    
    if args.action == "list":
        plugins = _plugin_registry.list_plugins()
        
        print("\n" + "=" * 70)
        print("OSINT Plugin Gateway — Available Plugins")
        print("=" * 70)
        
        for p in plugins:
            status = "✅ Enabled" if p["enabled"] else "⏸️  Disabled"
            print(f"\n{status}: {p['name']}")
            print(f"   {p['description']}")
        
        print("=" * 70 + "\n")
    
    elif args.action == "enable":
        if not args.plugin:
            print("Error: --plugin required")
            return 1
        
        if _plugin_registry.enable_plugin(args.plugin):
            print(f"✅ Plugin enabled: {args.plugin}")
        else:
            print(f"❌ Plugin not found: {args.plugin}")
            return 1
    
    elif args.action == "disable":
        if not args.plugin:
            print("Error: --plugin required")
            return 1
        
        if _plugin_registry.disable_plugin(args.plugin):
            print(f"✅ Plugin disabled: {args.plugin}")
        else:
            print(f"❌ Plugin not found: {args.plugin}")
            return 1
    
    elif args.action == "search":
        if not args.query:
            print("Error: --query required")
            return 1
        
        results = search_with_plugins(args.query)
        
        print("\n" + "=" * 70)
        print(f"Search Results: {args.query}")
        print("=" * 70)
        
        for plugin_name, plugin_results in results.items():
            print(f"\n{plugin_name}: {len(plugin_results)} results")
            for idx, result in enumerate(plugin_results[:3], 1):
                print(f"  {idx}. {result.get('title', 'No title')[:60]}...")
        
        print("=" * 70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())













