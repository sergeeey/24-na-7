"""
OSINT Collector — сбор данных через Brave Search и Bright Data.

Реализует паттерны A (Brave-first) и B (BrightData-first) для сбора информации.
"""
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.mcp.clients import get_brave_client, get_bright_client
from src.osint.schemas import Source
from src.osint.serp_collector import collect_serp_results
from src.osint.zone_manager import get_zone_for_mission

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.collector")
except Exception:
    import logging
    logger = logging.getLogger("osint.collector")


def extract_links_from_serp(serp_data: Any) -> List[str]:
    """
    Извлекает ссылки из результатов поиска (SERP).
    
    Args:
        serp_data: Данные SERP (HTML или структурированный JSON)
        
    Returns:
        Список URL
    """
    links = []
    
    if isinstance(serp_data, dict):
        # Структурированные данные от Brave Search
        results = serp_data.get("web", {}).get("results", [])
        for item in results:
            url = item.get("url")
            if url:
                links.append(url)
    elif isinstance(serp_data, str):
        # HTML от Bright Data - извлекаем ссылки
        url_pattern = r'href=["\'](https?://[^"\']+)["\']'
        links = re.findall(url_pattern, serp_data)
        # Убираем дубликаты и фильтруем только http(s)
        links = list(set([link for link in links if link.startswith(("http://", "https://"))]))
    
    return links


def gather_osint(
    query: str,
    goggle_url: Optional[str] = None,
    limit: int = 10,
    scrape_content: bool = True,
    use_serp: bool = False,
    search_engine: str = "google",
    zone: Optional[str] = None,
) -> List[Source]:
    """
    Собирает OSINT данные через Brave Search, Bright Data или SERP API.
    
    Реализует паттерны:
    - A (Brave-first): Brave Search → Bright Data scraping
    - B (BrightData-first): Goggle SERP → Bright Data scraping
    - C (SERP API): Bright Data SERP API → Direct scraping
    
    Args:
        query: Поисковый запрос
        goggle_url: Опциональный URL Goggle для прямого скрапинга (паттерн B)
        limit: Максимальное количество результатов
        scrape_content: Извлекать ли полный контент страниц
        use_serp: Использовать ли SERP API вместо Brave Search
        search_engine: Поисковая система для SERP ("google", "bing", "yahoo")
        zone: Зона Bright Data (опционально, выбирается автоматически)
        
    Returns:
        Список источников (Source objects)
    """
    # Паттерн C: SERP API
    if use_serp:
        logger.info("osint_collector_pattern_c_serp", query=query, search_engine=search_engine)
        
        # Выбираем зону если не указана
        if not zone:
            zone = get_zone_for_mission("serp")
        
        sources = collect_serp_results(
            query=query,
            search_engine=search_engine,
            zone=zone,
            limit=limit,
            scrape_content=scrape_content,
        )
        
        return sources
    sources = []
    
    try:
        if goggle_url:
            # Паттерн B: BrightData-first через Goggle
            logger.info("osint_collector_pattern_b", query=query, goggle_url=goggle_url)
            
            bright = get_bright_client()
            
            # Скрапим Goggle SERP
            serp_html = bright.scrape_page(goggle_url)
            
            if serp_html:
                # Извлекаем ссылки из SERP
                links = extract_links_from_serp(serp_html)
                
                logger.info("osint_goggle_links_extracted", links_count=len(links))
                
                # Скрапим каждую ссылку
                for url in links[:limit]:
                    try:
                        content = bright.scrape_markdown(url) if scrape_content else None
                        
                        sources.append(Source(
                            url=url,
                            content=content,
                            scraped_at=datetime.now(timezone.utc).isoformat(),
                        ))
                        
                        logger.debug("osint_source_collected", url=url)
                    except Exception as e:
                        logger.warning("osint_source_failed", url=url, error=str(e))
        else:
            # Паттерн A: Brave-first
            logger.info("osint_collector_pattern_a", query=query, limit=limit)
            
            brave = get_brave_client()
            bright = get_bright_client()
            
            # Поиск через Brave
            search_results = brave.search(query, limit=limit)
            
            logger.info("osint_brave_search_completed", results_count=len(search_results))
            
            # Извлекаем контент через Bright Data
            for item in search_results[:limit]:
                url = item.get("url", "")
                title = item.get("title", "")
                
                if not url:
                    continue
                
                try:
                    content = None
                    if scrape_content:
                        content = bright.scrape_markdown(url)
                    
                    sources.append(Source(
                        url=url,
                        title=title,
                        content=content,
                        scraped_at=datetime.now(timezone.utc).isoformat(),
                    ))
                    
                    logger.debug("osint_source_collected", url=url, has_content=content is not None)
                except Exception as e:
                    logger.warning("osint_source_scrape_failed", url=url, error=str(e))
                    # Добавляем источник без контента
                    sources.append(Source(
                        url=url,
                        title=title,
                        content=None,
                        scraped_at=datetime.now(timezone.utc).isoformat(),
                    ))
        
        logger.info(
            "osint_collection_completed",
            query=query,
            sources_count=len(sources),
            with_content=sum(1 for s in sources if s.content),
        )
        
        return sources
        
    except Exception as e:
        logger.error("osint_collection_failed", query=query, error=str(e))
        return []


def gather_osint_batch(
    queries: List[str],
    limit_per_query: int = 5,
) -> Dict[str, List[Source]]:
    """
    Собирает OSINT данные для нескольких запросов параллельно.
    
    Args:
        queries: Список поисковых запросов
        limit_per_query: Лимит результатов на запрос
        
    Returns:
        Словарь {query: [sources]}
    """
    results = {}
    
    for query in queries:
        sources = gather_osint(query, limit=limit_per_query)
        results[query] = sources
    
    return results

