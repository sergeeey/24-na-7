"""
SERP Collector — сбор данных из поисковых систем через Bright Data SERP API.

Поддерживает Google, Bing, Yahoo и другие поисковые системы.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.mcp.clients import get_bright_client
from src.osint.schemas import Source

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.serp")
except Exception:
    import logging
    logger = logging.getLogger("osint.serp")


def collect_serp_results(
    query: str,
    search_engine: str = "google",
    zone: Optional[str] = None,
    limit: int = 10,
    scrape_content: bool = True,
) -> List[Source]:
    """
    Собирает результаты SERP через Bright Data SERP API.
    
    Args:
        query: Поисковый запрос
        search_engine: Поисковая система ("google", "bing", "yahoo")
        zone: Зона Bright Data (опционально)
        limit: Количество результатов
        scrape_content: Извлекать ли полный контент страниц
        
    Returns:
        Список источников из SERP
    """
    sources = []
    
    try:
        bright = get_bright_client(zone=zone)
        
        logger.info(
            "serp_collection_started",
            query=query,
            search_engine=search_engine,
            zone=zone or "default",
        )
        
        # Получаем SERP через Bright Data API
        serp_data = bright.scrape_serp(
            query=query,
            search_engine=search_engine,
            zone=zone,
            format="raw",
            count=limit,
        )
        
        if not serp_data:
            logger.warning("serp_collection_failed", query=query)
            return sources
        
        # Извлекаем структурированные результаты
        serp_results = bright.extract_serp_results(serp_data)
        
        if not serp_results:
            logger.warning("serp_results_empty", query=query)
            return sources
        
        logger.info("serp_results_extracted", count=len(serp_results))
        
        # Извлекаем полный контент если нужно
        for result in serp_results[:limit]:
            url = result.get("url", "")
            title = result.get("title", "")
            
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
                
                logger.debug("serp_source_collected", url=url, has_content=content is not None)
                
            except Exception as e:
                logger.warning("serp_source_scrape_failed", url=url, error=str(e))
                # Добавляем источник без контента
                sources.append(Source(
                    url=url,
                    title=title,
                    content=None,
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                ))
        
        logger.info(
            "serp_collection_completed",
            query=query,
            sources_count=len(sources),
            with_content=sum(1 for s in sources if s.content),
        )
        
        return sources
        
    except Exception as e:
        logger.error("serp_collection_failed", query=query, error=str(e))
        return []


def collect_multi_serp(
    query: str,
    search_engines: List[str] = None,
    zone: Optional[str] = None,
    limit_per_engine: int = 5,
) -> Dict[str, List[Source]]:
    """
    Собирает результаты из нескольких поисковых систем.
    
    Args:
        query: Поисковый запрос
        search_engines: Список поисковых систем (по умолчанию ["google", "bing"])
        zone: Зона Bright Data
        limit_per_engine: Лимит результатов на поисковую систему
        
    Returns:
        Словарь {search_engine: [sources]}
    """
    if search_engines is None:
        search_engines = ["google", "bing"]
    
    results = {}
    
    for engine in search_engines:
        try:
            sources = collect_serp_results(
                query=query,
                search_engine=engine,
                zone=zone,
                limit=limit_per_engine,
                scrape_content=True,
            )
            results[engine] = sources
            logger.info("multi_serp_engine_completed", engine=engine, count=len(sources))
        except Exception as e:
            logger.error("multi_serp_engine_failed", engine=engine, error=str(e))
            results[engine] = []
    
    return results













