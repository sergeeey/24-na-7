"""
CEB-E Report Generator v1.0

Генерирует эталонный markdown отчёт на основе audit_report.json.
"""
import json
import argparse
import re
from pathlib import Path
from datetime import datetime


def render_template(template_path: Path, data: dict) -> str:
    """Рендеринг шаблона с заменой переменных и условных блоков."""
    template = template_path.read_text(encoding="utf-8")
    
    # Заменяем простые переменные {{var}}
    for key, value in data.items():
        if isinstance(value, (str, int, float, bool)):
            template = template.replace(f"{{{{{key}}}}}", str(value))
    
    # Компоненты для детального отчёта
    component_names = {
        "rules_engine": "Rules Engine",
        "memory_bank": "Memory Bank 2.0",
        "mcp_gateway": "MCP Gateway",
        "hooks_system": "Hooks System",
        "validation_framework": "Validation Framework (SAFE+CoVe)",
        "observability": "Observability",
        "governance_loop": "Governance Loop",
        "playbooks_suite": "Playbooks Suite",
        "multi_agent": "Multi-Agent System",
    }
    
    # Формируем сводную таблицу компонентов
    if "components" in data:
        table_rows = []
        for comp_key, comp_data in data["components"].items():
            name = component_names.get(comp_key, comp_key)
            score = comp_data.get("score", 0)
            exists = comp_data.get("exists", False)
            status = "✅" if exists else "❌"
            
            # Формируем summary
            details = comp_data.get("details", [])
            summary = details[0] if details else ("Настроен" if exists else "Отсутствует")
            
            max_score = {
                "rules_engine": 15,
                "memory_bank": 10,
                "mcp_gateway": 10,
                "hooks_system": 10,
                "validation_framework": 15,
                "observability": 10,
                "governance_loop": 10,
                "playbooks_suite": 10,
                "multi_agent": 10,
            }.get(comp_key, 10)
            
            table_rows.append(f"| {name} | {score} / {max_score} | {status} | {summary} |")
        
        # Заменяем таблицу
        table_pattern = r"\| № \| Компонент.*?\| {{.*?}} \|"
        table_header = "| № | Компонент | Балл | Статус | Детали |\n|---|-----------|------|--------|--------|"
        table_content = "\n".join([f"| {i+1} | {row}" for i, row in enumerate(table_rows)])
        full_table = table_header + "\n" + table_content
        
        template = re.sub(
            r"\| № \| Компонент.*?\| {{.*?}} \|.*?\n",
            full_table + "\n",
            template,
            flags=re.DOTALL,
        )
    
    # Обрабатываем рекомендации
    recommendations = data.get("recommendations", [])
    if recommendations:
        rec_text = "\n".join([f"- {r}" for r in recommendations])
        template = re.sub(r"\{\{#recommendations\}\}.*?\{\{/recommendations\}\}", rec_text, template, flags=re.DOTALL)
        template = re.sub(r"\{\{^recommendations\}\}.*?\{\{/recommendations\}\}", "", template, flags=re.DOTALL)
    else:
        template = re.sub(r"\{\{#recommendations\}\}.*?\{\{/recommendations\}\}", "", template, flags=re.DOTALL)
        template = re.sub(r"\{\{^recommendations\}\}.*?\{\{/recommendations\}\}", "", template, flags=re.DOTALL)
    
    # Обрабатываем уровень
    level = data.get("level", 0)
    is_level_5 = level >= 5
    if is_level_5:
        template = re.sub(r"\{\{#is_level_5\}\}(.*?)\{\{/is_level_5\}\}", r"\1", template, flags=re.DOTALL)
        template = re.sub(r"\{\{^is_level_5\}\}(.*?)\{\{/is_level_5\}\}", "", template, flags=re.DOTALL)
    else:
        template = re.sub(r"\{\{#is_level_5\}\}(.*?)\{\{/is_level_5\}\}", "", template, flags=re.DOTALL)
        template = re.sub(r"\{\{^is_level_5\}\}(.*?)\{\{/is_level_5\}\}", r"\1", template, flags=re.DOTALL)
    
    # Формируем summary
    score = data.get("score", 0)
    max_score = data.get("max_score", 100)
    if score >= 90:
        summary = "Полное соответствие CEB-E v1.0"
    elif score >= 70:
        summary = "Хорошее соответствие с незначительными недочётами"
    elif score >= 50:
        summary = "Базовое соответствие, требуется доработка"
    elif score >= 30:
        summary = "Частичное соответствие, значительная доработка"
    else:
        summary = "Требуется существенная настройка"
    
    template = template.replace("{{summary}}", summary)
    
    # Формируем детальный анализ компонентов
    components_detailed = []
    if "components" in data:
        for comp_key, comp_data in data["components"].items():
            name = component_names.get(comp_key, comp_key)
            score_val = comp_data.get("score", 0)
            exists = comp_data.get("exists", False)
            status = "✅ Соответствует эталону" if exists and score_val > 0 else "❌ Не соответствует"
            
            max_score = {
                "rules_engine": 15,
                "memory_bank": 10,
                "mcp_gateway": 10,
                "hooks_system": 10,
                "validation_framework": 15,
                "observability": 10,
                "governance_loop": 10,
                "playbooks_suite": 10,
                "multi_agent": 10,
            }.get(comp_key, 10)
            
            description = {
                "rules_engine": "Проверка структуры правил, наличия frontmatter и типов активации.",
                "memory_bank": "Проверка актуальности контекста и автообновления Memory Bank.",
                "mcp_gateway": "Валидность и работоспособность MCP интеграций.",
                "hooks_system": "Наличие и работоспособность реактивной автоматизации.",
                "validation_framework": "Проверка SAFE и CoVe валидаторов.",
                "observability": "Сбор и отправка метрик, интеграция с системами мониторинга.",
                "governance_loop": "Анализ аудита и автопереключение профиля.",
                "playbooks_suite": "Наличие и валидность ключевых плейбуков.",
                "multi_agent": "Корректная работа нескольких агентов, изоляция через worktrees.",
            }.get(comp_key, "Проверка компонента.")
            
            checks = []
            details = comp_data.get("details", [])
            for detail in details:
                checks.append(f"✅ {detail}")
            
            issues = comp_data.get("issues", [])
            
            components_detailed.append({
                "name": name,
                "status": status,
                "score": f"{score_val} / {max_score}",
                "description": description,
                "checks": checks,
                "issues": issues,
            })
    
    # Заменяем детальный анализ
    if components_detailed:
        detailed_section = "\n\n".join([
            f"### {comp['name']}\n\n"
            f"**Статус:** {comp['status']}\n"
            f"**Балл:** {comp['score']}\n\n"
            f"{comp['description']}\n\n"
            f"**Детали проверки:**\n" + "\n".join(comp['checks']) + "\n\n"
            f"**Выявленные проблемы:**\n" + 
            ("\n".join([f"- ⚠️ {issue}" for issue in comp['issues']]) if comp['issues'] else "- ✅ Проблем не обнаружено")
            for comp in components_detailed
        ])
        
        template = re.sub(
            r"\{\{#components_detailed\}\}.*?\{\{/components_detailed\}\}",
            detailed_section,
            template,
            flags=re.DOTALL,
        )
    
    return template


def main():
    parser = argparse.ArgumentParser(description="CEB-E Report Generator v1.0")
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(".cursor/audit/audit_report_template.md"),
        help="Путь к шаблону отчёта",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".cursor/audit/audit_report.md"),
        help="Путь для сохранения отчёта",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=Path(".cursor/audit/audit_report.json"),
        help="Путь к JSON с данными аудита",
    )
    
    args = parser.parse_args()
    
    # Загружаем данные аудита
    if not args.json.exists():
        print(f"Ошибка: файл {args.json} не найден. Сначала запустите run_audit.py")
        return 1
    
    data = json.loads(args.json.read_text(encoding="utf-8"))
    
    # Загружаем шаблон
    if not args.template.exists():
        print(f"Ошибка: шаблон {args.template} не найден")
        return 1
    
    # Генерируем отчёт
    report = render_template(args.template, data)
    
    # Сохраняем
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    
    print(f"✅ Эталонный отчёт CEB-E v1.0 сгенерирован: {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
