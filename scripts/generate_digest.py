"""
Генерация дайджеста дня.

Использование:
    python scripts/generate_digest.py --date 2025-01-03
    python scripts/generate_digest.py --date today --format json
    python scripts/generate_digest.py --date yesterday --analyze-density
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from src.digest.generator import DigestGenerator
from src.digest.analyzer import InformationDensityAnalyzer
from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("generate_digest")


def parse_date(date_str: str) -> date:
    """Парсит дату из строки."""
    if date_str.lower() == "today":
        return date.today()
    elif date_str.lower() == "yesterday":
        return date.fromordinal(date.today().toordinal() - 1)
    else:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Неверный формат даты: {date_str}. Используйте YYYY-MM-DD, 'today' или 'yesterday'")


def main():
    """Точка входа."""
    parser = argparse.ArgumentParser(description="Генерация дайджеста дня")
    parser.add_argument(
        "--date",
        default="today",
        help="Дата для дайджеста (YYYY-MM-DD, 'today', 'yesterday')",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Формат вывода",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Минимальная уверенность для фактов (не используется в MVP)",
    )
    parser.add_argument(
        "--include-metadata",
        action="store_true",
        default=True,
        help="Включать метаданные в дайджест",
    )
    parser.add_argument(
        "--no-metadata",
        dest="include_metadata",
        action="store_false",
        help="Не включать метаданные",
    )
    parser.add_argument(
        "--analyze-density",
        action="store_true",
        help="Только анализ информационной плотности",
    )
    parser.add_argument(
        "--output-digest",
        action="store_true",
        default=True,
        help="Генерировать дайджест (по умолчанию)",
    )
    parser.add_argument(
        "--no-output-digest",
        dest="output_digest",
        action="store_false",
        help="Не генерировать дайджест",
    )
    
    args = parser.parse_args()
    
    # Парсим дату
    try:
        target_date = parse_date(args.date)
    except ValueError as e:
        print(f"❌ Ошибка: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"📊 Reflexio Digest Generator")
    print(f"   Дата: {target_date.isoformat()}")
    print()
    
    # Анализ плотности
    if args.analyze_density:
        print("🔍 Анализ информационной плотности...")
        analyzer = InformationDensityAnalyzer()
        analysis = analyzer.analyze_day(target_date)
        
        density = analysis["density_analysis"]
        stats = analysis["statistics"]
        
        print()
        print("=" * 60)
        print("Результаты анализа информационной плотности")
        print("=" * 60)
        print(f"Дата: {target_date.isoformat()}")
        print()
        print("📈 Статистика:")
        print(f"   Транскрипций: {stats['transcriptions_count']}")
        print(f"   Общая длительность: {stats['total_duration_minutes']} мин")
        print(f"   Символов: {stats['total_characters']}")
        print()
        print("🎯 Информационная плотность:")
        print(f"   Оценка: {density['score']}/100")
        print(f"   Уровень: {density['level']}")
        print()
        print("📊 Компоненты:")
        print(f"   Плотность по времени: {density['components']['time_density']:.1f}")
        print(f"   Плотность по объёму: {density['components']['volume_density']:.1f}")
        print(f"   Равномерность: {density['components']['distribution_score']:.1f}")
        print()
        print(f"💡 Интерпретация: {density['interpretation']}")
        print("=" * 60)
        
        if not args.output_digest:
            sys.exit(0)
        print()
    
    # Генерация дайджеста
    if args.output_digest:
        print(f"📝 Генерация дайджеста ({args.format})...")
        generator = DigestGenerator()
        
        try:
            output_file = generator.generate(
                target_date=target_date,
                output_format=args.format,
                include_metadata=args.include_metadata,
            )
            
            print()
            print("=" * 60)
            print("✅ Дайджест успешно сгенерирован!")
            print("=" * 60)
            print(f"Файл: {output_file}")
            print(f"Размер: {output_file.stat().st_size} байт")
            print("=" * 60)
            
        except Exception as e:
            logger.error("digest_generation_failed", error=str(e))
            print(f"❌ Ошибка генерации дайджеста: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()













