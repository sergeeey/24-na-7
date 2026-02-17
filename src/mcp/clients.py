"""
MCP Clients для Brave Search и Bright Data.

Адаптеры для работы с внешними API-сервисами поиска и извлечения данных.
"""
import os
from typing import Optional, Dict, Any, List

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("mcp.clients")
except Exception:
    # Fallback если logging не настроен
    import logging
    logger = logging.getLogger("mcp.clients")


class BraveSearchClient:
    """
    Клиент для Brave Search API.
    
    Использует официальный API Brave Search для веб-поиска.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Инициализация клиента Brave Search."""
        self.api_key = api_key or os.getenv("BRAVE_API_KEY")
        
        if not self.api_key:
            logger.warning("brave_api_key_not_set")
            raise ValueError("BRAVE_API_KEY not set in environment")
        
        self.base_url = "https://api.search.brave.com/res/v1"
        
        # Пытаемся импортировать официальный SDK если доступен
        try:
            import brave_search
            self.client = brave_search.BraveSearch(api_key=self.api_key)
            self.use_sdk = True
        except ImportError:
            # Используем прямые HTTP запросы
            self.use_sdk = False
            import requests
            self.session = requests.Session()
            self.session.headers.update({
                "X-Subscription-Token": self.api_key,
                "Accept": "application/json",
            })
            logger.info("brave_client_initialized_http")
    
    def search(self, query: str, limit: int = 10, **kwargs) -> list[Dict[str, Any]]:
        """
        Выполняет поисковый запрос.
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            **kwargs: Дополнительные параметры поиска
            
        Returns:
            Список результатов поиска
        """
        try:
            if self.use_sdk:
                results = self.client.search(query, count=limit, **kwargs)
                # Конвертируем в унифицированный формат
                return [
                    {
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        "description": item.get("description", ""),
                        "age": item.get("age", ""),
                    }
                    for item in results.get("web", {}).get("results", [])
                ]
            else:
                # HTTP запрос напрямую
                params = {
                    "q": query,
                    "count": limit,
                    "safesearch": kwargs.get("safesearch", "moderate"),
                }
                
                response = self.session.get(
                    f"{self.base_url}/web/search",
                    params=params,
                    timeout=10,
                )
                response.raise_for_status()
                
                data = response.json()
                return [
                    {
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        "description": item.get("description", ""),
                        "age": item.get("age", ""),
                    }
                    for item in data.get("web", {}).get("results", [])
                ]
                
        except Exception as e:
            logger.error("brave_search_failed", query=query, error=str(e))
            return []


class BrightDataClient:
    """
    Клиент для Bright Data API.
    
    Использует Bright Data для извлечения контента с веб-страниц.
    Поддерживает работу через proxy endpoints и SERP API.
    """
    
    def __init__(self, api_key: Optional[str] = None, proxy_http: Optional[str] = None, proxy_ws: Optional[str] = None, zone: Optional[str] = None):
        """Инициализация клиента Bright Data."""
        self.api_key = api_key or os.getenv("BRIGHTDATA_API_KEY")
        self.proxy_http = proxy_http or os.getenv("BRIGHTDATA_PROXY_HTTP")
        self.proxy_ws = proxy_ws or os.getenv("BRIGHTDATA_PROXY_WS")
        self.zone = zone or os.getenv("BRIGHTDATA_ZONE", "serp_api1")  # Зона по умолчанию
        
        # Если есть proxy, используем его вместо API ключа
        if not self.proxy_http and not self.api_key:
            logger.warning("brightdata_credentials_not_set")
            raise ValueError("BRIGHTDATA_API_KEY or BRIGHTDATA_PROXY_HTTP must be set in environment")
        
        self.base_url = "https://api.brightdata.com"
        
        # Пытаемся импортировать официальный SDK
        try:
            import brightdata
            if self.api_key:
                self.client = brightdata.BrightData(api_key=self.api_key)
            self.use_sdk = True
        except ImportError:
            # Используем прямые HTTP запросы через proxy или API
            self.use_sdk = False
            import requests
            self.session = requests.Session()
            
            if self.proxy_http:
                # Настройка proxy для сессии
                # Извлекаем credentials из proxy URL
                from urllib.parse import urlparse
                urlparse(self.proxy_http)  # проверка формата URL
                
                # Настраиваем proxies для requests
                self.session.proxies = {
                    "http": self.proxy_http,
                    "https": self.proxy_http,
                }
                logger.info("brightdata_client_initialized_proxy", proxy=self.proxy_http[:50] + "...")
            else:
                # Используем API ключ
                self.session.headers.update({
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                })
                logger.info("brightdata_client_initialized_http")
    
    def scrape_page(self, url: str, **kwargs) -> Optional[str]:
        """
        Извлекает HTML контент страницы.
        
        Args:
            url: URL страницы для скрапинга
            **kwargs: Дополнительные параметры (proxy, headers и т.д.)
            
        Returns:
            HTML контент или None при ошибке
        """
        try:
            if self.use_sdk:
                result = self.client.scrape(url, **kwargs)
                return result.get("html") or result.get("content")
            else:
                # Если используем proxy, делаем прямой запрос через proxy
                if self.proxy_http:
                    response = self.session.get(
                        url,
                        timeout=30,
                        allow_redirects=True,
                    )
                    response.raise_for_status()
                    return response.text
                else:
                    # HTTP запрос через Bright Data API
                    response = self.session.post(
                        f"{self.base_url}/scrape",
                        json={
                            "url": url,
                            **kwargs,
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    data = response.json()
                    return data.get("html") or data.get("content")
                
        except Exception as e:
            logger.error("brightdata_scrape_failed", url=url, error=str(e))
            return None
    
    def scrape_markdown(self, url: str, **kwargs) -> Optional[str]:
        """
        Извлекает контент страницы в формате Markdown.
        
        Args:
            url: URL страницы
            **kwargs: Дополнительные параметры
            
        Returns:
            Markdown контент или None при ошибке
        """
        try:
            # Получаем HTML
            html = self.scrape_page(url, **kwargs)
            
            if not html:
                return None
            
            # Конвертируем HTML в Markdown
            try:
                from markdownify import markdownify
                markdown = markdownify(html, heading_style="ATX")
                return markdown
            except ImportError:
                # Упрощённая конвертация через regex (fallback)
                import re
                # Удаляем скрипты и стили
                html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
                # Базовое преобразование заголовков
                html = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1', html)
                html = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1', html)
                html = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html, flags=re.DOTALL)
                # Удаляем остальные HTML теги
                markdown = re.sub(r'<[^>]+>', '', html)
                return markdown
                
        except Exception as e:
            logger.error("brightdata_markdown_failed", url=url, error=str(e))
            return None
    
    def scrape_serp(self, query: str, search_engine: str = "google", zone: Optional[str] = None, format: str = "raw", **kwargs) -> Optional[Dict[str, Any]]:
        """
        Получает результаты поисковой выдачи (SERP) через Bright Data SERP API.
        
        Args:
            query: Поисковый запрос
            search_engine: Поисковая система ("google", "bing", "yahoo")
            zone: Зона Bright Data (по умолчанию используется self.zone)
            format: Формат ответа ("raw", "html", "json")
            **kwargs: Дополнительные параметры
            
        Returns:
            Результаты SERP или None при ошибке
        """
        if not self.api_key:
            logger.error("serp_api_key_required")
            return None
        
        try:
            import requests
            
            # Формируем URL поисковой системы
            search_urls = {
                "google": f"https://www.google.com/search?q={query}",
                "bing": f"https://www.bing.com/search?q={query}",
                "yahoo": f"https://search.yahoo.com/search?p={query}",
            }
            
            serp_url = search_urls.get(search_engine.lower(), search_urls["google"])
            
            # Добавляем дополнительные параметры поиска
            if "count" in kwargs or "num" in kwargs:
                count = kwargs.get("count") or kwargs.get("num", 10)
                serp_url += f"&num={count}"
            
            zone_to_use = zone or self.zone
            
            # Запрос к Bright Data SERP API
            response = requests.post(
                f"{self.base_url}/request",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={
                    "zone": zone_to_use,
                    "url": serp_url,
                    "format": format,
                    **{k: v for k, v in kwargs.items() if k not in ["count", "num"]},
                },
                timeout=30,
            )
            
            response.raise_for_status()
            
            if format == "json":
                return response.json()
            else:
                # Raw или HTML формат
                return {
                    "content": response.text,
                    "format": format,
                    "url": serp_url,
                    "search_engine": search_engine,
                }
                
        except Exception as e:
            logger.error("brightdata_serp_failed", query=query, search_engine=search_engine, error=str(e))
            return None
    
    def extract_serp_results(self, serp_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Извлекает структурированные результаты из SERP данных.
        
        Args:
            serp_data: Данные SERP от scrape_serp()
            
        Returns:
            Список результатов поиска
        """
        results = []
        
        try:
            content = serp_data.get("content", "")
            if not content:
                return results
            
            # Парсим HTML SERP (простая эвристика для Google/Bing)
            import re
            
            # Паттерны для извлечения результатов
            # Google
            google_pattern = r'<div[^>]*class="[^"]*g[^"]*"[^>]*>.*?<h3[^>]*>(.*?)</h3>.*?<a[^>]*href="([^"]+)"'
            
            # Bing
            bing_pattern = r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>.*?<h2[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
            
            # Пытаемся извлечь результаты
            matches = re.finditer(google_pattern, content, re.DOTALL)
            for match in matches:
                title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                url = match.group(2)
                
                if url.startswith("/url?q="):
                    # Google URL формат
                    url = url.split("&")[0].replace("/url?q=", "")
                
                if url.startswith("http"):
                    results.append({
                        "title": title,
                        "url": url,
                        "source": "google_serp",
                    })
            
            # Если не нашли через Google паттерн, пробуем Bing
            if not results:
                matches = re.finditer(bing_pattern, content, re.DOTALL)
                for match in matches:
                    url = match.group(1)
                    title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                    
                    if url.startswith("http"):
                        results.append({
                            "title": title,
                            "url": url,
                            "source": "bing_serp",
                        })
            
            logger.info("serp_results_extracted", count=len(results))
            
        except Exception as e:
            logger.error("serp_extraction_failed", error=str(e))
        
        return results


def get_brave_client(api_key: Optional[str] = None) -> BraveSearchClient:
    """Фабрика для создания клиента Brave Search."""
    return BraveSearchClient(api_key=api_key)


def get_bright_client(
    api_key: Optional[str] = None,
    proxy_http: Optional[str] = None,
    proxy_ws: Optional[str] = None,
    zone: Optional[str] = None,
) -> BrightDataClient:
    """Фабрика для создания клиента Bright Data."""
    return BrightDataClient(api_key=api_key, proxy_http=proxy_http, proxy_ws=proxy_ws, zone=zone)

