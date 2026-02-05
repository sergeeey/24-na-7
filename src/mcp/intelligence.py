"""
MCP Intelligence Module — интеллектуальный поиск и извлечение данных.

Объединяет Brave Search и Bright Data для комплексного анализа внешних источников.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.mcp.clients import get_brave_client, get_bright_client
try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("mcp.intelligence")
except Exception:
    # Fallback если logging не настроен
    import logging
    logger = logging.getLogger("mcp.intelligence")


def combined_search_and_scrape(
    query: str,
    max_results: int = 5,
    scrape_content: bool = True,
    timeout_per_url: int = 10,
) -> List[Dict[str, Any]]:
    """
    Комбинированный поиск и извлечение данных.
    
    Этап 1: Brave Search находит релевантные ссылки
    Этап 2: Bright Data извлекает контент с каждой страницы
    
    Args:
        query: Поисковый запрос
        max_results: Максимальное количество результатов для поиска
        scrape_content: Извлекать ли контент через Bright Data
        timeout_per_url: Таймаут для каждого URL при скрапинге
        
    Returns:
        Список результатов с URL, title и content
    """
    results = []
    
    try:
        logger.info("intelligence_search_started", query=query, max_results=max_results)
        
        # Этап 1: Разведка через Brave Search
        brave = get_brave_client()
        search_results = brave.search(query, limit=max_results)
        
        logger.info(
            "brave_search_completed",
            query=query,
            results_count=len(search_results),
        )
        
        if not search_results:
            logger.warning("brave_search_no_results", query=query)
            return results
        
        # Этап 2: Извлечение контента через Bright Data
        if scrape_content:
            bright = get_bright_client()
            
            for idx, link in enumerate(search_results[:max_results], 1):
                url = link.get("url", "")
                title = link.get("title", "")
                
                if not url:
                    continue
                
                logger.debug(
                    "scraping_url",
                    url=url,
                    progress=f"{idx}/{len(search_results)}",
                )
                
                try:
                    # Извлекаем Markdown контент
                    content = bright.scrape_markdown(url)
                    
                    if content:
                        # Ограничиваем размер контента (первые 5000 символов)
                        if len(content) > 5000:
                            content = content[:5000] + "...\n\n[Content truncated]"
                        
                        results.append({
                            "url": url,
                            "title": title,
                            "description": link.get("description", ""),
                            "content": content,
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                            "source": "brave+brightdata",
                        })
                        
                        logger.debug("url_scraped_successfully", url=url)
                    else:
                        # Добавляем результат без контента
                        results.append({
                            "url": url,
                            "title": title,
                            "description": link.get("description", ""),
                            "content": None,
                            "scraped_at": None,
                            "source": "brave",
                            "error": "Failed to scrape content",
                        })
                        
                        logger.warning("url_scrape_failed", url=url)
                        
                except Exception as e:
                    logger.error(
                        "url_scrape_error",
                        url=url,
                        error=str(e),
                    )
                    
                    # Добавляем результат с ошибкой
                    results.append({
                        "url": url,
                        "title": title,
                        "description": link.get("description", ""),
                        "content": None,
                        "error": str(e),
                        "source": "brave",
                    })
        else:
            # Без скрапинга - только результаты поиска
            results = [
                {
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "source": "brave",
                }
                for item in search_results
            ]
        
        logger.info(
            "intelligence_search_completed",
            query=query,
            total_results=len(results),
            scraped_count=sum(1 for r in results if r.get("content")),
        )
        
        return results
        
    except Exception as e:
        logger.error(
            "intelligence_search_failed",
            query=query,
            error=str(e),
        )
        return []


def save_to_memory_bank(topic: str, data: List[Dict[str, Any]]) -> bool:
    """
    Сохраняет результаты поиска в Memory Bank.
    
    Args:
        topic: Тема поиска
        data: Результаты поиска и скрапинга
        
    Returns:
        True если успешно сохранено
    """
    try:
        memory_path = Path(".cursor/memory/external_research.md")
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Формируем запись
        lines = [
            f"# External Research: {topic}",
            "",
            f"**Date:** {datetime.now(timezone.utc).isoformat()}",
            f"**Source:** Brave Search + Bright Data",
            f"**Results:** {len(data)}",
            "",
            "---",
            "",
        ]
        
        for idx, item in enumerate(data, 1):
            lines.append(f"## {idx}. {item.get('title', 'Untitled')}")
            lines.append(f"**URL:** {item.get('url', '')}")
            lines.append(f"**Description:** {item.get('description', '')}")
            lines.append("")
            
            if item.get("content"):
                lines.append("**Content:**")
                lines.append("")
                lines.append(item["content"])
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        # Добавляем в файл (append mode)
        with memory_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        logger.info(
            "memory_bank_updated",
            topic=topic,
            items_saved=len(data),
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "memory_bank_update_failed",
            topic=topic,
            error=str(e),
        )
        return False


def discover_topics(query: str, depth: int = 2) -> List[str]:
    """
    Обнаруживает связанные темы через поиск.
    
    Args:
        query: Начальный запрос
        depth: Глубина поиска связанных тем
        
    Returns:
        Список связанных тем
    """
    topics = [query]
    
    try:
        brave = get_brave_client()
        
        # Ищем связанные запросы
        search_results = brave.search(f"related to {query}", limit=10)
        
        # Извлекаем потенциальные темы из заголовков
        for item in search_results[:depth * 3]:
            title = item.get("title", "")
            description = item.get("description", "")
            
            # Простая эвристика: извлекаем ключевые слова
            # В реальности можно использовать NLP
            if title and len(title.split()) <= 5:
                topics.append(title)
        
        # Убираем дубликаты
        unique_topics = list(dict.fromkeys(topics))[:depth * 2]
        
        logger.info(
            "topics_discovered",
            query=query,
            topics_count=len(unique_topics),
        )
        
        return unique_topics
        
    except Exception as e:
        logger.error("topic_discovery_failed", query=query, error=str(e))
        return topics


def main():
    """CLI для тестирования модуля."""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Intelligence Module")
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum search results",
    )
    parser.add_argument(
        "--no-scrape",
        action="store_true",
        help="Don't scrape content, only search",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save results to memory bank",
    )
    
    args = parser.parse_args()
    
    # Выполняем поиск и извлечение
    results = combined_search_and_scrape(
        args.query,
        max_results=args.max_results,
        scrape_content=not args.no_scrape,
    )
    
    # Выводим результаты
    print(f"\n{'='*70}")
    print(f"Search Results: {args.query}")
    print(f"{'='*70}\n")
    
    for idx, item in enumerate(results, 1):
        print(f"{idx}. {item.get('title', 'Untitled')}")
        print(f"   URL: {item.get('url', '')}")
        if item.get("description"):
            print(f"   {item['description'][:100]}...")
        if item.get("content"):
            print(f"   Content: {len(item['content'])} chars")
        print()
    
    # Сохраняем в Memory Bank если запрошено
    if args.save:
        save_to_memory_bank(args.query, results)
        print(f"✅ Results saved to Memory Bank\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

