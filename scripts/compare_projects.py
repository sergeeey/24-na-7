"""
Проект сравнения двух кодовых баз.

Сканирует и анализирует файлы в двух директориях проектов для выявления различий,
уникальных файлов и формирования рекомендаций по слиянию.
"""
import sys
import difflib
from pathlib import Path
from typing import List, Set, Dict, Any, Tuple
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("compare_projects")
except Exception:
    import logging
    logger = logging.getLogger("compare_projects")


def discover_files(root_path: str, ignore_patterns: Set[str] = None) -> List[Path]:
    """
    Рекурсивно обнаруживает все файлы в директории, исключая игнорируемые паттерны.

    Args:
        root_path: Корневая директория для сканирования
        ignore_patterns: Множество паттернов директорий для исключения

    Returns:
        Список объектов Path всех найденных файлов
    """
    if ignore_patterns is None:
        ignore_patterns = {
            '.git',
            '__pycache__',
            'node_modules',
            '.venv',
            'venv',
            '.pytest_cache',
            '.mypy_cache',
            '.tox',
            'dist',
            'build',
            '*.egg-info',
            '.DS_Store',
            'Thumbs.db',
            '.auto-claude'
        }

    root = Path(root_path)

    if not root.exists():
        logger.error("path_not_found", path=str(root))
        return []

    if not root.is_dir():
        logger.error("path_not_directory", path=str(root))
        return []

    files = []

    try:
        for item in root.rglob('*'):
            # Проверяем, содержит ли путь игнорируемые паттерны
            should_ignore = False
            for pattern in ignore_patterns:
                if pattern.startswith('*'):
                    # Паттерн для расширений файлов
                    if item.name.endswith(pattern[1:]):
                        should_ignore = True
                        break
                else:
                    # Паттерн для имен директорий
                    if pattern in item.parts:
                        should_ignore = True
                        break

            if not should_ignore and item.is_file():
                files.append(item)

        logger.info("files_discovered", root=str(root), count=len(files))

    except PermissionError as e:
        logger.warning("permission_error", path=str(root), error=str(e))
    except Exception as e:
        logger.error("discovery_error", path=str(root), error=str(e))

    return sorted(files)


class ProjectComparator:
    """Сравнивает два проекта и генерирует отчет."""

    def __init__(self, project1_path: str, project2_path: str):
        """
        Инициализирует компаратор проектов.

        Args:
            project1_path: Путь к первому проекту (golos)
            project2_path: Путь ко второму проекту (24 na 7)
        """
        self.project1_path = Path(project1_path)
        self.project2_path = Path(project2_path)
        self.project1_name = self.project1_path.name
        self.project2_name = self.project2_path.name

        self.project1_files: List[Path] = []
        self.project2_files: List[Path] = []

        self.unique_to_project1: List[Path] = []
        self.unique_to_project2: List[Path] = []
        self.overlapping_files: List[tuple[Path, Path]] = []

        self.results: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project1": str(self.project1_path),
            "project2": str(self.project2_path),
            "summary": {
                "project1_total_files": 0,
                "project2_total_files": 0,
                "unique_to_project1": 0,
                "unique_to_project2": 0,
                "overlapping": 0,
            },
        }

    def get_relative_path(self, file_path: Path, root: Path) -> Path:
        """
        Получает относительный путь файла от корня проекта.

        Args:
            file_path: Полный путь к файлу
            root: Корневая директория проекта

        Returns:
            Относительный путь
        """
        try:
            return file_path.relative_to(root)
        except ValueError:
            return file_path

    def discover_projects(self):
        """Обнаруживает файлы в обоих проектах."""
        logger.info("starting_discovery",
                   project1=str(self.project1_path),
                   project2=str(self.project2_path))

        self.project1_files = discover_files(str(self.project1_path))
        self.project2_files = discover_files(str(self.project2_path))

        self.results["summary"]["project1_total_files"] = len(self.project1_files)
        self.results["summary"]["project2_total_files"] = len(self.project2_files)

        logger.info("discovery_complete",
                   project1_count=len(self.project1_files),
                   project2_count=len(self.project2_files))

    def categorize_files(self):
        """Категоризирует файлы как уникальные или пересекающиеся."""
        logger.info("starting_categorization")

        # Создаем множества относительных путей для быстрого поиска
        project1_rel_paths = {
            self.get_relative_path(f, self.project1_path): f
            for f in self.project1_files
        }
        project2_rel_paths = {
            self.get_relative_path(f, self.project2_path): f
            for f in self.project2_files
        }

        # Находим пересечения и уникальные файлы
        common_rel_paths = set(project1_rel_paths.keys()) & set(project2_rel_paths.keys())
        unique_to_p1_rel = set(project1_rel_paths.keys()) - set(project2_rel_paths.keys())
        unique_to_p2_rel = set(project2_rel_paths.keys()) - set(project1_rel_paths.keys())

        # Формируем списки
        self.overlapping_files = [
            (project1_rel_paths[rel], project2_rel_paths[rel])
            for rel in sorted(common_rel_paths)
        ]

        self.unique_to_project1 = [
            project1_rel_paths[rel] for rel in sorted(unique_to_p1_rel)
        ]

        self.unique_to_project2 = [
            project2_rel_paths[rel] for rel in sorted(unique_to_p2_rel)
        ]

        # Обновляем результаты
        self.results["summary"]["unique_to_project1"] = len(self.unique_to_project1)
        self.results["summary"]["unique_to_project2"] = len(self.unique_to_project2)
        self.results["summary"]["overlapping"] = len(self.overlapping_files)

        logger.info("categorization_complete",
                   unique_to_project1=len(self.unique_to_project1),
                   unique_to_project2=len(self.unique_to_project2),
                   overlapping=len(self.overlapping_files))

    def compare_file_content(self, relative_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Сравнивает содержимое файла в обоих проектах используя difflib.

        Args:
            relative_path: Относительный путь к файлу от корня проектов

        Returns:
            (success, result_dict) где result_dict содержит статистику различий
        """
        file1 = self.project1_path / relative_path
        file2 = self.project2_path / relative_path

        # Проверяем существование файлов
        if not file1.exists():
            logger.error("file_not_found", project=self.project1_name, file=relative_path)
            return False, {"error": f"File not found in {self.project1_name}"}

        if not file2.exists():
            logger.error("file_not_found", project=self.project2_name, file=relative_path)
            return False, {"error": f"File not found in {self.project2_name}"}

        try:
            # Читаем содержимое файлов
            with open(file1, 'r', encoding='utf-8') as f:
                lines1 = f.readlines()

            with open(file2, 'r', encoding='utf-8') as f:
                lines2 = f.readlines()

            # Используем difflib для сравнения
            diff = difflib.unified_diff(
                lines1,
                lines2,
                fromfile=f"{self.project1_name}/{relative_path}",
                tofile=f"{self.project2_name}/{relative_path}",
                lineterm=''
            )

            diff_lines = list(diff)

            # Подсчитываем статистику
            additions = sum(1 for line in diff_lines if line.startswith('+') and not line.startswith('+++'))
            deletions = sum(1 for line in diff_lines if line.startswith('-') and not line.startswith('---'))

            result = {
                "file": relative_path,
                "project1": str(file1),
                "project2": str(file2),
                "identical": len(diff_lines) == 0,
                "lines_project1": len(lines1),
                "lines_project2": len(lines2),
                "additions": additions,
                "deletions": deletions,
                "total_changes": additions + deletions,
                "diff_lines": diff_lines if len(diff_lines) > 0 else []
            }

            logger.info("file_compared",
                       file=relative_path,
                       identical=result["identical"],
                       additions=additions,
                       deletions=deletions)

            return True, result

        except UnicodeDecodeError:
            logger.warning("binary_file_skip", file=relative_path)
            return False, {"error": "Binary file or encoding issue"}
        except Exception as e:
            logger.error("comparison_error", file=relative_path, error=str(e))
            return False, {"error": str(e)}

    def print_summary(self):
        """Выводит краткую сводку результатов."""
        summary = self.results["summary"]

        print("\n" + "=" * 70)
        print(f"Сравнение проектов: {self.project1_name} vs {self.project2_name}")
        print("=" * 70)
        print()
        print(f"Проект 1 ({self.project1_name}): {summary['project1_total_files']} файлов")
        print(f"Проект 2 ({self.project2_name}): {summary['project2_total_files']} файлов")
        print()
        print(f"Уникальных для {self.project1_name}: {summary['unique_to_project1']}")
        print(f"Уникальных для {self.project2_name}: {summary['unique_to_project2']}")
        print(f"Пересекающихся файлов: {summary['overlapping']}")
        print()
        print("=" * 70)


def main():
    """Основная функция для тестирования."""
    import argparse

    parser = argparse.ArgumentParser(description="Сравнение двух проектов")
    parser.add_argument(
        "--mode",
        choices=["discovery", "categorize", "full", "diff"],
        default="full",
        help="Режим работы"
    )
    parser.add_argument(
        "--project1",
        default=r"C:\Users\serge\Desktop\golos",
        help="Путь к первому проекту"
    )
    parser.add_argument(
        "--project2",
        default=r"D:\24 na 7",
        help="Путь ко второму проекту"
    )
    parser.add_argument(
        "--sample",
        help="Относительный путь к файлу для сравнения (используется с --mode=diff)"
    )

    args = parser.parse_args()

    comparator = ProjectComparator(args.project1, args.project2)

    if args.mode == "diff":
        if not args.sample:
            logger.error("sample_required", message="--sample argument required for diff mode")
            print("Error: --sample argument is required for diff mode")
            return

        success, result = comparator.compare_file_content(args.sample)

        if not success:
            logger.error("diff_failed", error=result.get("error"))
            print(f"Error: {result.get('error')}")
            return

        # Выводим статистику
        print("\n" + "=" * 70)
        print(f"Diff statistics for: {result['file']}")
        print("=" * 70)
        print(f"Project 1: {result['project1']}")
        print(f"Project 2: {result['project2']}")
        print()
        print(f"Lines in project 1: {result['lines_project1']}")
        print(f"Lines in project 2: {result['lines_project2']}")
        print()
        print(f"Identical: {result['identical']}")
        if not result['identical']:
            print(f"Additions: {result['additions']}")
            print(f"Deletions: {result['deletions']}")
            print(f"Total changes: {result['total_changes']}")
        print("=" * 70)

        return

    if args.mode in ["discovery", "full"]:
        comparator.discover_projects()

        if args.mode == "discovery":
            comparator.print_summary()
            return

    if args.mode in ["categorize", "full"]:
        if not comparator.project1_files:
            comparator.discover_projects()

        comparator.categorize_files()
        comparator.print_summary()


if __name__ == "__main__":
    main()
