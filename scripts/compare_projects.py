"""
Проект сравнения двух кодовых баз.

Сканирует и анализирует файлы в двух директориях проектов для выявления различий,
уникальных файлов и формирования рекомендаций по слиянию.
"""
import sys
import re
import json
import difflib
from pathlib import Path
from typing import List, Set, Dict, Any, Tuple, Optional
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


def parse_requirements_txt(file_path: Path) -> Dict[str, Optional[str]]:
    """
    Парсит requirements.txt файл и извлекает зависимости.

    Args:
        file_path: Путь к requirements.txt файлу

    Returns:
        Словарь {package_name: version_spec}, где version_spec может быть None
    """
    dependencies = {}

    if not file_path.exists():
        return dependencies

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # Пропускаем комментарии и пустые строки
                if not line or line.startswith('#'):
                    continue

                # Пропускаем флаги pip (например, --index-url)
                if line.startswith('-'):
                    continue

                # Удаляем комментарии в конце строки
                line = line.split('#')[0].strip()

                # Парсим имя пакета и версию
                # Поддерживаем операторы: ==, >=, <=, >, <, !=, ~=
                match = re.match(r'^([a-zA-Z0-9_\-\[\]\.]+)\s*([>=<!~]+.*)?$', line)

                if match:
                    package_name = match.group(1).lower()
                    version_spec = match.group(2).strip() if match.group(2) else None
                    dependencies[package_name] = version_spec

        logger.info("requirements_parsed", file=str(file_path), count=len(dependencies))

    except Exception as e:
        logger.error("requirements_parse_error", file=str(file_path), error=str(e))

    return dependencies


def parse_package_json(file_path: Path) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Парсит package.json файл и извлекает зависимости.

    Args:
        file_path: Путь к package.json файлу

    Returns:
        Словарь с ключами 'dependencies' и 'devDependencies',
        каждый содержит {package_name: version_spec}
    """
    result = {
        'dependencies': {},
        'devDependencies': {}
    }

    if not file_path.exists():
        return result

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

            if 'dependencies' in data:
                result['dependencies'] = {
                    k.lower(): v for k, v in data['dependencies'].items()
                }

            if 'devDependencies' in data:
                result['devDependencies'] = {
                    k.lower(): v for k, v in data['devDependencies'].items()
                }

        total_count = len(result['dependencies']) + len(result['devDependencies'])
        logger.info("package_json_parsed", file=str(file_path), count=total_count)

    except json.JSONDecodeError as e:
        logger.error("package_json_parse_error", file=str(file_path), error=str(e))
    except Exception as e:
        logger.error("package_json_error", file=str(file_path), error=str(e))

    return result


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

    def analyze_python_dependencies(self) -> Dict[str, Any]:
        """
        Анализирует зависимости Python из requirements.txt файлов.

        Returns:
            Словарь с результатами анализа зависимостей
        """
        logger.info("analyzing_python_dependencies")

        # Ищем requirements.txt в обоих проектах
        req1_path = self.project1_path / "requirements.txt"
        req2_path = self.project2_path / "requirements.txt"

        deps1 = parse_requirements_txt(req1_path)
        deps2 = parse_requirements_txt(req2_path)

        # Находим общие, уникальные и конфликтующие зависимости
        all_packages = set(deps1.keys()) | set(deps2.keys())
        shared = []
        unique_to_p1 = []
        unique_to_p2 = []
        conflicts = []

        for package in sorted(all_packages):
            version1 = deps1.get(package)
            version2 = deps2.get(package)

            if package in deps1 and package in deps2:
                if version1 == version2:
                    shared.append({
                        "package": package,
                        "version": version1
                    })
                else:
                    conflicts.append({
                        "package": package,
                        "version_project1": version1,
                        "version_project2": version2
                    })
            elif package in deps1:
                unique_to_p1.append({
                    "package": package,
                    "version": version1
                })
            else:
                unique_to_p2.append({
                    "package": package,
                    "version": version2
                })

        result = {
            "type": "python",
            "file_project1": str(req1_path) if req1_path.exists() else None,
            "file_project2": str(req2_path) if req2_path.exists() else None,
            "total_project1": len(deps1),
            "total_project2": len(deps2),
            "shared": shared,
            "unique_to_project1": unique_to_p1,
            "unique_to_project2": unique_to_p2,
            "conflicts": conflicts
        }

        logger.info("python_dependencies_analyzed",
                   shared=len(shared),
                   unique_to_p1=len(unique_to_p1),
                   unique_to_p2=len(unique_to_p2),
                   conflicts=len(conflicts))

        return result

    def analyze_node_dependencies(self) -> Dict[str, Any]:
        """
        Анализирует зависимости Node.js из package.json файлов.

        Returns:
            Словарь с результатами анализа зависимостей
        """
        logger.info("analyzing_node_dependencies")

        # Ищем package.json в обоих проектах
        pkg1_path = self.project1_path / "package.json"
        pkg2_path = self.project2_path / "package.json"

        pkg1_data = parse_package_json(pkg1_path)
        pkg2_data = parse_package_json(pkg2_path)

        # Объединяем dependencies и devDependencies для сравнения
        deps1 = {**pkg1_data['dependencies'], **pkg1_data['devDependencies']}
        deps2 = {**pkg2_data['dependencies'], **pkg2_data['devDependencies']}

        # Находим общие, уникальные и конфликтующие зависимости
        all_packages = set(deps1.keys()) | set(deps2.keys())
        shared = []
        unique_to_p1 = []
        unique_to_p2 = []
        conflicts = []

        for package in sorted(all_packages):
            version1 = deps1.get(package)
            version2 = deps2.get(package)

            if package in deps1 and package in deps2:
                if version1 == version2:
                    shared.append({
                        "package": package,
                        "version": version1
                    })
                else:
                    conflicts.append({
                        "package": package,
                        "version_project1": version1,
                        "version_project2": version2
                    })
            elif package in deps1:
                unique_to_p1.append({
                    "package": package,
                    "version": version1
                })
            else:
                unique_to_p2.append({
                    "package": package,
                    "version": version2
                })

        result = {
            "type": "node",
            "file_project1": str(pkg1_path) if pkg1_path.exists() else None,
            "file_project2": str(pkg2_path) if pkg2_path.exists() else None,
            "total_project1": len(deps1),
            "total_project2": len(deps2),
            "shared": shared,
            "unique_to_project1": unique_to_p1,
            "unique_to_project2": unique_to_p2,
            "conflicts": conflicts
        }

        logger.info("node_dependencies_analyzed",
                   shared=len(shared),
                   unique_to_p1=len(unique_to_p1),
                   unique_to_p2=len(unique_to_p2),
                   conflicts=len(conflicts))

        return result

    def analyze_all_dependencies(self) -> Dict[str, Any]:
        """
        Анализирует все типы зависимостей в обоих проектах.

        Returns:
            Словарь с результатами анализа всех типов зависимостей
        """
        logger.info("analyzing_all_dependencies")

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project1": str(self.project1_path),
            "project2": str(self.project2_path),
            "python": None,
            "node": None
        }

        # Анализируем Python зависимости
        python_result = self.analyze_python_dependencies()
        if python_result["total_project1"] > 0 or python_result["total_project2"] > 0:
            results["python"] = python_result

        # Анализируем Node.js зависимости
        node_result = self.analyze_node_dependencies()
        if node_result["total_project1"] > 0 or node_result["total_project2"] > 0:
            results["node"] = node_result

        logger.info("all_dependencies_analyzed")

        return results

    def assess_version(self) -> Dict[str, Any]:
        """
        Оценивает, какой проект является более новым/полным на основе:
        - Времени модификации файлов
        - Версий зависимостей
        - Полноты файлов (количество уникальных файлов)

        Returns:
            Словарь с результатами оценки версии и рекомендациями
        """
        logger.info("starting_version_assessment")

        # Инициализируем результат
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project1": str(self.project1_path),
            "project2": str(self.project2_path),
            "file_timestamps": {},
            "dependency_freshness": {},
            "file_completeness": {},
            "recommendation": None,
            "confidence": "unknown",
            "reasoning": []
        }

        # 1. Анализ времени модификации файлов
        if not self.overlapping_files:
            self.discover_projects()
            self.categorize_files()

        newer_in_p1 = 0
        newer_in_p2 = 0
        identical_time = 0

        for file1, file2 in self.overlapping_files:
            try:
                mtime1 = file1.stat().st_mtime
                mtime2 = file2.stat().st_mtime

                if mtime1 > mtime2:
                    newer_in_p1 += 1
                elif mtime2 > mtime1:
                    newer_in_p2 += 1
                else:
                    identical_time += 1
            except Exception as e:
                logger.warning("timestamp_comparison_error", file=str(file1), error=str(e))

        result["file_timestamps"] = {
            "overlapping_files_count": len(self.overlapping_files),
            "newer_in_project1": newer_in_p1,
            "newer_in_project2": newer_in_p2,
            "identical_timestamp": identical_time,
            "recency_score_project1": newer_in_p1,
            "recency_score_project2": newer_in_p2
        }

        # 2. Анализ свежести зависимостей
        python_deps = self.analyze_python_dependencies()
        node_deps = self.analyze_node_dependencies()

        # Подсчитываем уникальные зависимости как индикатор более полного проекта
        python_unique_p1 = len(python_deps.get("unique_to_project1", []))
        python_unique_p2 = len(python_deps.get("unique_to_project2", []))
        node_unique_p1 = len(node_deps.get("unique_to_project1", []))
        node_unique_p2 = len(node_deps.get("unique_to_project2", []))

        result["dependency_freshness"] = {
            "python": {
                "unique_to_project1": python_unique_p1,
                "unique_to_project2": python_unique_p2,
                "conflicts": len(python_deps.get("conflicts", []))
            },
            "node": {
                "unique_to_project1": node_unique_p1,
                "unique_to_project2": node_unique_p2,
                "conflicts": len(node_deps.get("conflicts", []))
            },
            "dependency_score_project1": python_unique_p1 + node_unique_p1,
            "dependency_score_project2": python_unique_p2 + node_unique_p2
        }

        # 3. Анализ полноты файлов
        total_p1 = len(self.project1_files)
        total_p2 = len(self.project2_files)
        unique_p1 = len(self.unique_to_project1)
        unique_p2 = len(self.unique_to_project2)

        result["file_completeness"] = {
            "total_files_project1": total_p1,
            "total_files_project2": total_p2,
            "unique_files_project1": unique_p1,
            "unique_files_project2": unique_p2,
            "completeness_score_project1": unique_p1,
            "completeness_score_project2": unique_p2
        }

        # 4. Формирование рекомендации
        reasoning = []
        p1_score = 0
        p2_score = 0

        # Критерий 1: Время модификации (вес 30%)
        if newer_in_p1 > newer_in_p2:
            p1_score += 30
            reasoning.append(f"Проект 1 имеет {newer_in_p1} более свежих файлов против {newer_in_p2} в проекте 2")
        elif newer_in_p2 > newer_in_p1:
            p2_score += 30
            reasoning.append(f"Проект 2 имеет {newer_in_p2} более свежих файлов против {newer_in_p1} в проекте 1")
        else:
            reasoning.append("Файлы имеют одинаковое время модификации")

        # Критерий 2: Полнота файлов (вес 40%)
        if unique_p1 > unique_p2:
            p1_score += 40
            reasoning.append(f"Проект 1 имеет {unique_p1} уникальных файлов против {unique_p2} в проекте 2")
        elif unique_p2 > unique_p1:
            p2_score += 40
            reasoning.append(f"Проект 2 имеет {unique_p2} уникальных файлов против {unique_p1} в проекте 1")
        else:
            reasoning.append("Оба проекта имеют одинаковое количество уникальных файлов")

        # Критерий 3: Зависимости (вес 30%)
        total_deps_p1 = python_unique_p1 + node_unique_p1
        total_deps_p2 = python_unique_p2 + node_unique_p2

        if total_deps_p1 > total_deps_p2:
            p1_score += 30
            reasoning.append(f"Проект 1 имеет {total_deps_p1} уникальных зависимостей против {total_deps_p2} в проекте 2")
        elif total_deps_p2 > total_deps_p1:
            p2_score += 30
            reasoning.append(f"Проект 2 имеет {total_deps_p2} уникальных зависимостей против {total_deps_p1} в проекте 1")
        else:
            reasoning.append("Оба проекта имеют одинаковое количество уникальных зависимостей")

        # Определяем рекомендацию и уверенность
        score_diff = abs(p1_score - p2_score)

        if p1_score > p2_score:
            result["recommendation"] = "project1"
            result["recommendation_name"] = self.project1_name
        elif p2_score > p1_score:
            result["recommendation"] = "project2"
            result["recommendation_name"] = self.project2_name
        else:
            result["recommendation"] = "equal"
            result["recommendation_name"] = "Оба проекта равнозначны"

        # Уровень уверенности
        if score_diff >= 60:
            result["confidence"] = "high"
        elif score_diff >= 30:
            result["confidence"] = "medium"
        else:
            result["confidence"] = "low"

        result["scores"] = {
            "project1_score": p1_score,
            "project2_score": p2_score,
            "difference": score_diff
        }
        result["reasoning"] = reasoning

        logger.info("version_assessment_complete",
                   recommendation=result["recommendation"],
                   confidence=result["confidence"],
                   p1_score=p1_score,
                   p2_score=p2_score)

        return result

    def print_version_assessment(self, assessment: Dict[str, Any]):
        """
        Выводит результаты оценки версии в читаемом формате.

        Args:
            assessment: Результаты оценки версии
        """
        print("\n" + "=" * 70)
        print(f"Оценка версии: {self.project1_name} vs {self.project2_name}")
        print("=" * 70)
        print()

        # Статистика по времени модификации
        ts = assessment["file_timestamps"]
        print("Анализ времени модификации файлов:")
        print("-" * 70)
        print(f"Пересекающихся файлов: {ts['overlapping_files_count']}")
        print(f"Новее в {self.project1_name}: {ts['newer_in_project1']}")
        print(f"Новее в {self.project2_name}: {ts['newer_in_project2']}")
        print(f"Одинаковое время: {ts['identical_timestamp']}")
        print()

        # Полнота файлов
        fc = assessment["file_completeness"]
        print("Анализ полноты файлов:")
        print("-" * 70)
        print(f"Всего файлов в {self.project1_name}: {fc['total_files_project1']}")
        print(f"Всего файлов в {self.project2_name}: {fc['total_files_project2']}")
        print(f"Уникальных для {self.project1_name}: {fc['unique_files_project1']}")
        print(f"Уникальных для {self.project2_name}: {fc['unique_files_project2']}")
        print()

        # Зависимости
        df = assessment["dependency_freshness"]
        print("Анализ зависимостей:")
        print("-" * 70)
        if df["python"]["unique_to_project1"] or df["python"]["unique_to_project2"]:
            print(f"Python - уникальные для {self.project1_name}: {df['python']['unique_to_project1']}")
            print(f"Python - уникальные для {self.project2_name}: {df['python']['unique_to_project2']}")
            print(f"Python - конфликтов: {df['python']['conflicts']}")
        if df["node"]["unique_to_project1"] or df["node"]["unique_to_project2"]:
            print(f"Node.js - уникальные для {self.project1_name}: {df['node']['unique_to_project1']}")
            print(f"Node.js - уникальные для {self.project2_name}: {df['node']['unique_to_project2']}")
            print(f"Node.js - конфликтов: {df['node']['conflicts']}")
        print()

        # Рекомендация
        print("РЕКОМЕНДАЦИЯ:")
        print("=" * 70)
        scores = assessment["scores"]
        print(f"Оценка {self.project1_name}: {scores['project1_score']}/100")
        print(f"Оценка {self.project2_name}: {scores['project2_score']}/100")
        print()

        confidence_labels = {
            "high": "Высокая",
            "medium": "Средняя",
            "low": "Низкая"
        }
        confidence_str = confidence_labels.get(assessment["confidence"], assessment["confidence"])

        if assessment["recommendation"] == "equal":
            print(f"Результат: Проекты равнозначны (уверенность: {confidence_str})")
            print("Рекомендуется ручной анализ для выбора базового проекта")
        else:
            rec_name = assessment["recommendation_name"]
            print(f"Рекомендуется использовать {rec_name} как базу для слияния")
            print(f"Уверенность: {confidence_str}")

        print()
        print("Обоснование:")
        for reason in assessment["reasoning"]:
            print(f"  - {reason}")

        print()
        print("=" * 70)

    def print_dependency_analysis(self, analysis: Dict[str, Any]):
        """
        Выводит результаты анализа зависимостей в читаемом формате.

        Args:
            analysis: Результаты анализа зависимостей
        """
        print("\n" + "=" * 70)
        print(f"Анализ зависимостей: {self.project1_name} vs {self.project2_name}")
        print("=" * 70)
        print()

        # Python зависимости
        if analysis.get("python"):
            python = analysis["python"]
            print("Python зависимости (requirements.txt):")
            print("-" * 70)
            print(f"Проект 1: {python['total_project1']} пакетов")
            print(f"Проект 2: {python['total_project2']} пакетов")
            print()

            if python["shared"]:
                print(f"Общие зависимости ({len(python['shared'])}):")
                for dep in python["shared"][:10]:  # Показываем первые 10
                    version = dep['version'] or 'any'
                    print(f"  - {dep['package']}: {version}")
                if len(python["shared"]) > 10:
                    print(f"  ... и ещё {len(python['shared']) - 10}")
                print()

            if python["conflicts"]:
                print(f"Конфликтующие зависимости ({len(python['conflicts'])}):")
                for dep in python["conflicts"]:
                    v1 = dep['version_project1'] or 'any'
                    v2 = dep['version_project2'] or 'any'
                    print(f"  - {dep['package']}: {v1} vs {v2}")
                print()

            if python["unique_to_project1"]:
                print(f"Уникальные для {self.project1_name} ({len(python['unique_to_project1'])}):")
                for dep in python["unique_to_project1"][:5]:  # Показываем первые 5
                    version = dep['version'] or 'any'
                    print(f"  - {dep['package']}: {version}")
                if len(python["unique_to_project1"]) > 5:
                    print(f"  ... и ещё {len(python['unique_to_project1']) - 5}")
                print()

            if python["unique_to_project2"]:
                print(f"Уникальные для {self.project2_name} ({len(python['unique_to_project2'])}):")
                for dep in python["unique_to_project2"][:5]:  # Показываем первые 5
                    version = dep['version'] or 'any'
                    print(f"  - {dep['package']}: {version}")
                if len(python["unique_to_project2"]) > 5:
                    print(f"  ... и ещё {len(python['unique_to_project2']) - 5}")
                print()

        # Node.js зависимости
        if analysis.get("node"):
            node = analysis["node"]
            print("Node.js зависимости (package.json):")
            print("-" * 70)
            print(f"Проект 1: {node['total_project1']} пакетов")
            print(f"Проект 2: {node['total_project2']} пакетов")
            print()

            if node["shared"]:
                print(f"Общие зависимости ({len(node['shared'])}):")
                for dep in node["shared"][:10]:  # Показываем первые 10
                    print(f"  - {dep['package']}: {dep['version']}")
                if len(node["shared"]) > 10:
                    print(f"  ... и ещё {len(node['shared']) - 10}")
                print()

            if node["conflicts"]:
                print(f"Конфликтующие зависимости ({len(node['conflicts'])}):")
                for dep in node["conflicts"]:
                    print(f"  - {dep['package']}: {dep['version_project1']} vs {dep['version_project2']}")
                print()

            if node["unique_to_project1"]:
                print(f"Уникальные для {self.project1_name} ({len(node['unique_to_project1'])}):")
                for dep in node["unique_to_project1"][:5]:  # Показываем первые 5
                    print(f"  - {dep['package']}: {dep['version']}")
                if len(node["unique_to_project1"]) > 5:
                    print(f"  ... и ещё {len(node['unique_to_project1']) - 5}")
                print()

            if node["unique_to_project2"]:
                print(f"Уникальные для {self.project2_name} ({len(node['unique_to_project2'])}):")
                for dep in node["unique_to_project2"][:5]:  # Показываем первые 5
                    print(f"  - {dep['package']}: {dep['version']}")
                if len(node["unique_to_project2"]) > 5:
                    print(f"  ... и ещё {len(node['unique_to_project2']) - 5}")
                print()

        if not analysis.get("python") and not analysis.get("node"):
            print("Файлы зависимостей не найдены в обоих проектах.")
            print()

        print("=" * 70)

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

    def generate_markdown_report(self) -> str:
        """
        Генерирует markdown отчет о сравнении проектов.

        Returns:
            Строка с markdown-форматированным отчетом
        """
        logger.info("generating_markdown_report")

        # Выполняем необходимые анализы, если они еще не выполнены
        if not self.project1_files:
            self.discover_projects()
            self.categorize_files()

        dependency_analysis = self.analyze_all_dependencies()
        version_assessment = self.assess_version()

        # Начинаем формирование отчета
        lines = []
        lines.append("# Отчет о сравнении проектов")
        lines.append("")
        lines.append(f"**Дата:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append("")
        lines.append(f"**Проект 1:** `{self.project1_name}` ({self.project1_path})")
        lines.append(f"**Проект 2:** `{self.project2_name}` ({self.project2_path})")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Сводка
        lines.append("## Общая сводка")
        lines.append("")
        summary = self.results["summary"]
        lines.append(f"- **Всего файлов в {self.project1_name}:** {summary['project1_total_files']}")
        lines.append(f"- **Всего файлов в {self.project2_name}:** {summary['project2_total_files']}")
        lines.append(f"- **Уникальных для {self.project1_name}:** {summary['unique_to_project1']}")
        lines.append(f"- **Уникальных для {self.project2_name}:** {summary['unique_to_project2']}")
        lines.append(f"- **Пересекающихся файлов:** {summary['overlapping']}")
        lines.append("")

        # Рекомендация
        lines.append("## Рекомендация по слиянию")
        lines.append("")
        rec_name = version_assessment.get("recommendation_name", "Не определено")
        confidence = version_assessment.get("confidence", "unknown")
        confidence_labels = {
            "high": "Высокая",
            "medium": "Средняя",
            "low": "Низкая"
        }
        confidence_str = confidence_labels.get(confidence, confidence)

        scores = version_assessment.get("scores", {})
        p1_score = scores.get("project1_score", 0)
        p2_score = scores.get("project2_score", 0)

        lines.append(f"**Рекомендуемая база:** {rec_name}")
        lines.append(f"**Уверенность:** {confidence_str}")
        lines.append("")
        lines.append(f"- Оценка {self.project1_name}: {p1_score}/100")
        lines.append(f"- Оценка {self.project2_name}: {p2_score}/100")
        lines.append("")
        lines.append("**Обоснование:**")
        for reason in version_assessment.get("reasoning", []):
            lines.append(f"- {reason}")
        lines.append("")

        # Анализ времени модификации
        lines.append("## Анализ времени модификации файлов")
        lines.append("")
        ts = version_assessment.get("file_timestamps", {})
        lines.append(f"- **Пересекающихся файлов:** {ts.get('overlapping_files_count', 0)}")
        lines.append(f"- **Новее в {self.project1_name}:** {ts.get('newer_in_project1', 0)}")
        lines.append(f"- **Новее в {self.project2_name}:** {ts.get('newer_in_project2', 0)}")
        lines.append(f"- **Одинаковое время:** {ts.get('identical_timestamp', 0)}")
        lines.append("")

        # Анализ полноты файлов
        lines.append("## Анализ полноты файлов")
        lines.append("")
        fc = version_assessment.get("file_completeness", {})
        lines.append(f"- **Всего файлов в {self.project1_name}:** {fc.get('total_files_project1', 0)}")
        lines.append(f"- **Всего файлов в {self.project2_name}:** {fc.get('total_files_project2', 0)}")
        lines.append(f"- **Уникальных для {self.project1_name}:** {fc.get('unique_files_project1', 0)}")
        lines.append(f"- **Уникальных для {self.project2_name}:** {fc.get('unique_files_project2', 0)}")
        lines.append("")

        # Анализ зависимостей
        lines.append("## Анализ зависимостей")
        lines.append("")

        # Python зависимости
        if dependency_analysis.get("python"):
            python = dependency_analysis["python"]
            lines.append("### Python (requirements.txt)")
            lines.append("")
            lines.append(f"- **Всего в {self.project1_name}:** {python['total_project1']} пакетов")
            lines.append(f"- **Всего в {self.project2_name}:** {python['total_project2']} пакетов")
            lines.append(f"- **Общих зависимостей:** {len(python.get('shared', []))}")
            lines.append(f"- **Конфликтов версий:** {len(python.get('conflicts', []))}")
            lines.append(f"- **Уникальных для {self.project1_name}:** {len(python.get('unique_to_project1', []))}")
            lines.append(f"- **Уникальных для {self.project2_name}:** {len(python.get('unique_to_project2', []))}")
            lines.append("")

            if python.get("conflicts"):
                lines.append("#### Конфликтующие Python зависимости")
                lines.append("")
                lines.append("| Пакет | Версия в проекте 1 | Версия в проекте 2 |")
                lines.append("|-------|-------------------|-------------------|")
                for dep in python["conflicts"]:
                    v1 = dep.get('version_project1') or 'any'
                    v2 = dep.get('version_project2') or 'any'
                    lines.append(f"| {dep['package']} | {v1} | {v2} |")
                lines.append("")

        # Node.js зависимости
        if dependency_analysis.get("node"):
            node = dependency_analysis["node"]
            lines.append("### Node.js (package.json)")
            lines.append("")
            lines.append(f"- **Всего в {self.project1_name}:** {node['total_project1']} пакетов")
            lines.append(f"- **Всего в {self.project2_name}:** {node['total_project2']} пакетов")
            lines.append(f"- **Общих зависимостей:** {len(node.get('shared', []))}")
            lines.append(f"- **Конфликтов версий:** {len(node.get('conflicts', []))}")
            lines.append(f"- **Уникальных для {self.project1_name}:** {len(node.get('unique_to_project1', []))}")
            lines.append(f"- **Уникальных для {self.project2_name}:** {len(node.get('unique_to_project2', []))}")
            lines.append("")

            if node.get("conflicts"):
                lines.append("#### Конфликтующие Node.js зависимости")
                lines.append("")
                lines.append("| Пакет | Версия в проекте 1 | Версия в проекте 2 |")
                lines.append("|-------|-------------------|-------------------|")
                for dep in node["conflicts"]:
                    v1 = dep.get('version_project1') or 'any'
                    v2 = dep.get('version_project2') or 'any'
                    lines.append(f"| {dep['package']} | {v1} | {v2} |")
                lines.append("")

        if not dependency_analysis.get("python") and not dependency_analysis.get("node"):
            lines.append("*Файлы зависимостей не найдены в обоих проектах.*")
            lines.append("")

        # Уникальные файлы
        lines.append("## Уникальные файлы")
        lines.append("")

        lines.append(f"### Уникальные для {self.project1_name}")
        lines.append("")
        if self.unique_to_project1:
            # Группируем по расширениям
            by_ext = {}
            for file_path in self.unique_to_project1:
                rel_path = self.get_relative_path(file_path, self.project1_path)
                ext = rel_path.suffix or 'no extension'
                by_ext.setdefault(ext, []).append(str(rel_path))

            for ext in sorted(by_ext.keys()):
                files = by_ext[ext]
                lines.append(f"**{ext}** ({len(files)} файлов):")
                lines.append("")
                for file_name in sorted(files)[:10]:
                    lines.append(f"- `{file_name}`")
                if len(files) > 10:
                    lines.append(f"- *...и ещё {len(files) - 10} файлов*")
                lines.append("")
        else:
            lines.append("*Нет уникальных файлов*")
            lines.append("")

        lines.append(f"### Уникальные для {self.project2_name}")
        lines.append("")
        if self.unique_to_project2:
            # Группируем по расширениям
            by_ext = {}
            for file_path in self.unique_to_project2:
                rel_path = self.get_relative_path(file_path, self.project2_path)
                ext = rel_path.suffix or 'no extension'
                by_ext.setdefault(ext, []).append(str(rel_path))

            for ext in sorted(by_ext.keys()):
                files = by_ext[ext]
                lines.append(f"**{ext}** ({len(files)} файлов):")
                lines.append("")
                for file_name in sorted(files)[:10]:
                    lines.append(f"- `{file_name}`")
                if len(files) > 10:
                    lines.append(f"- *...и ещё {len(files) - 10} файлов*")
                lines.append("")
        else:
            lines.append("*Нет уникальных файлов*")
            lines.append("")

        # Стратегия слияния
        lines.append("---")
        lines.append("")
        merge_strategy_lines = self.generate_merge_strategy(version_assessment, dependency_analysis)
        lines.extend(merge_strategy_lines)

        report = "\n".join(lines)
        logger.info("markdown_report_generated", size=len(report))
        return report

    def generate_merge_strategy(self, version_assessment: Dict[str, Any],
                               dependency_analysis: Dict[str, Any]) -> List[str]:
        """
        Генерирует подробную стратегию слияния проектов.

        Args:
            version_assessment: Результаты оценки версий
            dependency_analysis: Результаты анализа зависимостей

        Returns:
            Список строк markdown с рекомендациями по слиянию
        """
        logger.info("generating_merge_strategy")

        lines = []
        lines.append("## Стратегия слияния")
        lines.append("")

        # Определяем направление слияния
        recommendation = version_assessment.get("recommendation")
        confidence = version_assessment.get("confidence", "unknown")

        if recommendation == "project1":
            base_project = self.project1_name
            merge_from = self.project2_name
            base_path = self.project1_path
            merge_path = self.project2_path
            unique_in_base = len(self.unique_to_project1)
            unique_to_merge = len(self.unique_to_project2)
        elif recommendation == "project2":
            base_project = self.project2_name
            merge_from = self.project1_name
            base_path = self.project2_path
            merge_path = self.project1_path
            unique_in_base = len(self.unique_to_project2)
            unique_to_merge = len(self.unique_to_project1)
        else:
            # Если проекты равнозначны, выбираем более полный
            if len(self.unique_to_project2) >= len(self.unique_to_project1):
                base_project = self.project2_name
                merge_from = self.project1_name
                base_path = self.project2_path
                merge_path = self.project1_path
                unique_in_base = len(self.unique_to_project2)
                unique_to_merge = len(self.unique_to_project1)
            else:
                base_project = self.project1_name
                merge_from = self.project2_name
                base_path = self.project1_path
                merge_path = self.project2_path
                unique_in_base = len(self.unique_to_project1)
                unique_to_merge = len(self.unique_to_project2)

        lines.append("### Рекомендуемое направление слияния")
        lines.append("")
        lines.append(f"**База (целевой проект):** `{base_project}`")
        lines.append(f"**Источник (откуда переносим):** `{merge_from}`")
        lines.append("")
        lines.append(f"*Обоснование:* Проект `{base_project}` выбран как база для слияния "
                    f"на основе анализа времени модификации файлов, полноты реализации и версий зависимостей.")
        lines.append("")

        # Пошаговый план слияния
        lines.append("### Пошаговый план слияния")
        lines.append("")

        step = 1

        # Шаг: Резервное копирование
        lines.append(f"#### Шаг {step}: Резервное копирование")
        step += 1
        lines.append("")
        lines.append("**Важно:** Создайте резервные копии обоих проектов перед началом слияния.")
        lines.append("")
        lines.append("```bash")
        lines.append(f"# Создайте резервную копию базового проекта")
        lines.append(f"cp -r \"{base_path}\" \"{base_path}.backup\"")
        lines.append("")
        lines.append(f"# Создайте резервную копию исходного проекта")
        lines.append(f"cp -r \"{merge_path}\" \"{merge_path}.backup\"")
        lines.append("```")
        lines.append("")

        # Шаг: Инициализация Git (если не инициализирован)
        lines.append(f"#### Шаг {step}: Проверка системы контроля версий")
        step += 1
        lines.append("")
        lines.append("Убедитесь, что базовый проект находится под контролем версий Git:")
        lines.append("")
        lines.append("```bash")
        lines.append(f"cd \"{base_path}\"")
        lines.append("git status")
        lines.append("# Если репозиторий не инициализирован:")
        lines.append("# git init")
        lines.append("# git add .")
        lines.append("# git commit -m \"Initial commit before merge\"")
        lines.append("```")
        lines.append("")

        # Шаг: Разрешение конфликтов зависимостей
        python_deps = dependency_analysis.get("python") or {}
        node_deps = dependency_analysis.get("node") or {}
        python_conflicts = python_deps.get("conflicts", [])
        node_conflicts = node_deps.get("conflicts", [])

        if python_conflicts or node_conflicts:
            lines.append(f"#### Шаг {step}: Разрешение конфликтов зависимостей")
            step += 1
            lines.append("")
            lines.append("Перед переносом файлов необходимо разрешить конфликты версий зависимостей:")
            lines.append("")

            if python_conflicts:
                lines.append("**Python зависимости:**")
                lines.append("")
                lines.append("| Пакет | Версия в базе | Версия в источнике | Рекомендация |")
                lines.append("|-------|---------------|-------------------|--------------|")
                for dep in python_conflicts:
                    pkg = dep['package']
                    if recommendation == "project1":
                        v_base = dep.get('version_project1') or 'any'
                        v_merge = dep.get('version_project2') or 'any'
                    else:
                        v_base = dep.get('version_project2') or 'any'
                        v_merge = dep.get('version_project1') or 'any'
                    lines.append(f"| {pkg} | {v_base} | {v_merge} | Проверить совместимость, выбрать новейшую стабильную версию |")
                lines.append("")

            if node_conflicts:
                lines.append("**Node.js зависимости:**")
                lines.append("")
                lines.append("| Пакет | Версия в базе | Версия в источнике | Рекомендация |")
                lines.append("|-------|---------------|-------------------|--------------|")
                for dep in node_conflicts:
                    pkg = dep['package']
                    if recommendation == "project1":
                        v_base = dep.get('version_project1') or 'any'
                        v_merge = dep.get('version_project2') or 'any'
                    else:
                        v_base = dep.get('version_project2') or 'any'
                        v_merge = dep.get('version_project1') or 'any'
                    lines.append(f"| {pkg} | {v_base} | {v_merge} | Проверить совместимость, выбрать новейшую стабильную версию |")
                lines.append("")

            lines.append("**Действия:**")
            lines.append("1. Проанализируйте breaking changes между версиями")
            lines.append("2. Обновите requirements.txt или package.json в базовом проекте")
            lines.append("3. Установите обновленные зависимости и запустите тесты")
            lines.append("")

        # Шаг: Перенос уникальных файлов
        if unique_to_merge > 0:
            lines.append(f"#### Шаг {step}: Перенос уникальных файлов из {merge_from}")
            step += 1
            lines.append("")
            lines.append(f"В проекте `{merge_from}` найдено {unique_to_merge} уникальных файлов, "
                        f"которых нет в `{base_project}`. Эти файлы необходимо перенести:")
            lines.append("")
            lines.append("**Рекомендуемый подход:**")
            lines.append("")
            lines.append("1. **Автоматический перенос** (для файлов с низким риском):")
            lines.append("```bash")
            lines.append(f"# Перенести все уникальные файлы, сохраняя структуру директорий")
            lines.append(f"rsync -av --relative \\")
            lines.append(f"  --files-from=<(список_уникальных_файлов) \\")
            lines.append(f"  \"{merge_path}/\" \"{base_path}/\"")
            lines.append("```")
            lines.append("")
            lines.append("2. **Ручной анализ** (рекомендуется для конфигурационных файлов):")
            lines.append("   - `.env` файлы - объедините настройки вручную")
            lines.append("   - Конфигурации баз данных")
            lines.append("   - Файлы с секретами и ключами")
            lines.append("")

        # Шаг: Анализ пересекающихся файлов
        overlapping_count = len(self.overlapping_files)
        if overlapping_count > 0:
            lines.append(f"#### Шаг {step}: Обработка пересекающихся файлов")
            step += 1
            lines.append("")
            lines.append(f"Обнаружено {overlapping_count} пересекающихся файлов. "
                        f"Необходимо определить стратегию для каждого:")
            lines.append("")
            lines.append("**Категории файлов:**")
            lines.append("")
            lines.append("1. **Идентичные файлы** - никаких действий не требуется")
            lines.append("2. **Файлы с различиями** - требуется анализ:")
            lines.append("   - Используйте `git diff` или инструменты сравнения")
            lines.append("   - Для кода: объедините улучшения из обоих проектов")
            lines.append("   - Для конфигов: выберите наиболее полную версию")
            lines.append("")
            lines.append("**Команда для анализа:**")
            lines.append("```bash")
            lines.append(f"# Сравнить конкретный файл")
            lines.append(f"diff -u \"{base_path}/путь/к/файлу\" \"{merge_path}/путь/к/файлу\"")
            lines.append("")
            lines.append("# Или использовать графический инструмент")
            lines.append(f"meld \"{base_path}\" \"{merge_path}\"")
            lines.append("```")
            lines.append("")

        # Шаг: Обновление зависимостей
        lines.append(f"#### Шаг {step}: Объединение зависимостей")
        step += 1
        lines.append("")

        python_unique = (python_deps.get("unique_to_project1", [])
                        if recommendation == "project2"
                        else python_deps.get("unique_to_project2", []))
        node_unique = (node_deps.get("unique_to_project1", [])
                      if recommendation == "project2"
                      else node_deps.get("unique_to_project2", []))

        if python_unique or node_unique:
            lines.append(f"Добавьте уникальные зависимости из `{merge_from}` в базовый проект:")
            lines.append("")

            if python_unique:
                lines.append("**Python зависимости для добавления:**")
                lines.append("```")
                for dep in python_unique[:10]:
                    version = dep.get('version') or ''
                    lines.append(f"{dep['package']}{version}")
                if len(python_unique) > 10:
                    lines.append(f"# ...и ещё {len(python_unique) - 10} пакетов")
                lines.append("```")
                lines.append("")

            if node_unique:
                lines.append("**Node.js зависимости для добавления:**")
                lines.append("```bash")
                for dep in node_unique[:10]:
                    lines.append(f"npm install {dep['package']}@{dep.get('version', 'latest')}")
                if len(node_unique) > 10:
                    lines.append(f"# ...и ещё {len(node_unique) - 10} пакетов")
                lines.append("```")
                lines.append("")
        else:
            lines.append("Все необходимые зависимости уже присутствуют в базовом проекте.")
            lines.append("")

        # Шаг: Тестирование
        lines.append(f"#### Шаг {step}: Тестирование объединенного проекта")
        step += 1
        lines.append("")
        lines.append("После завершения слияния проведите всестороннее тестирование:")
        lines.append("")
        lines.append("```bash")
        lines.append("# Установите/обновите зависимости")
        if python_deps:
            lines.append("pip install -r requirements.txt")
        if node_deps:
            lines.append("npm install")
        lines.append("")
        lines.append("# Запустите тесты")
        lines.append("pytest  # для Python")
        lines.append("npm test  # для Node.js")
        lines.append("")
        lines.append("# Запустите приложение")
        lines.append("# Проверьте основные функции вручную")
        lines.append("```")
        lines.append("")

        # Шаг: Фиксация изменений
        lines.append(f"#### Шаг {step}: Фиксация результата слияния")
        step += 1
        lines.append("")
        lines.append("После успешного тестирования зафиксируйте результаты:")
        lines.append("")
        lines.append("```bash")
        lines.append("git add .")
        lines.append(f"git commit -m \"Merge {merge_from} into {base_project}\"")
        lines.append("```")
        lines.append("")

        # Оценка рисков
        lines.append("### Оценка рисков")
        lines.append("")

        risks = []
        mitigations = []

        if confidence == "low":
            risks.append("**Низкая уверенность в рекомендации** - проекты могут быть равнозначны или данных недостаточно")
            mitigations.append("Проведите дополнительный ручной анализ перед принятием решения")

        if python_conflicts or node_conflicts:
            conflict_count = len(python_conflicts) + len(node_conflicts)
            risks.append(f"**Конфликты зависимостей** - обнаружено {conflict_count} конфликтующих версий пакетов")
            mitigations.append("Тщательно тестируйте после обновления зависимостей, проверьте breaking changes")

        if overlapping_count > 5:
            risks.append(f"**Большое количество пересекающихся файлов** - {overlapping_count} файлов требуют анализа")
            mitigations.append("Используйте инструменты трёхстороннего слияния (3-way merge), анализируйте изменения порциями")

        if unique_to_merge > 50:
            risks.append(f"**Большое количество уникальных файлов** - {unique_to_merge} файлов для переноса")
            mitigations.append("Переносите файлы категориями (по директориям/типам), тестируйте после каждой категории")

        if not risks:
            risks.append("**Риски минимальны** - структура проектов позволяет относительно безопасное слияние")
            mitigations.append("Следуйте стандартным процедурам тестирования после слияния")

        lines.append("#### Выявленные риски:")
        lines.append("")
        for risk in risks:
            lines.append(f"- {risk}")
        lines.append("")

        lines.append("#### Меры по снижению рисков:")
        lines.append("")
        for i, mitigation in enumerate(mitigations, 1):
            lines.append(f"{i}. {mitigation}")
        lines.append("")

        # Рекомендации по приоритетам
        lines.append("### Рекомендации по приоритетам")
        lines.append("")
        lines.append("**Высокий приоритет:**")
        lines.append("1. Резервное копирование обоих проектов")
        lines.append("2. Разрешение конфликтов зависимостей")
        lines.append("3. Перенос критичных конфигурационных файлов")
        lines.append("")
        lines.append("**Средний приоритет:**")
        lines.append("4. Перенос уникальных файлов кода")
        lines.append("5. Анализ и слияние пересекающихся файлов")
        lines.append("")
        lines.append("**Низкий приоритет:**")
        lines.append("6. Обновление документации")
        lines.append("7. Очистка устаревших файлов")
        lines.append("8. Оптимизация структуры директорий")
        lines.append("")

        logger.info("merge_strategy_generated", steps=step-1, risks=len(risks))

        return lines

    def save_markdown_report(self, output_path: Path):
        """
        Сохраняет markdown отчет в файл.

        Args:
            output_path: Путь к файлу для сохранения
        """
        report = self.generate_markdown_report()

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

        logger.info("markdown_report_saved", path=str(output_path))


def main():
    """Основная функция для тестирования."""
    import argparse

    parser = argparse.ArgumentParser(description="Сравнение двух проектов")
    parser.add_argument(
        "--mode",
        choices=["discovery", "categorize", "full", "diff", "dependencies", "assess", "report"],
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Предпросмотр отчета в stdout вместо сохранения в файл (используется с --mode=report)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("comparison_report.md"),
        help="Путь для сохранения отчета (используется с --mode=report)"
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

    if args.mode == "dependencies":
        analysis = comparator.analyze_all_dependencies()
        comparator.print_dependency_analysis(analysis)
        return

    if args.mode == "assess":
        assessment = comparator.assess_version()
        comparator.print_version_assessment(assessment)
        return

    if args.mode == "report":
        if args.dry_run:
            report = comparator.generate_markdown_report()
            print(report)
        else:
            comparator.save_markdown_report(args.output)
            print(f"Отчет сохранен в: {args.output}")
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
