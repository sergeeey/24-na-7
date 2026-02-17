# Multi-Agent System — Reflexio 24/7

Система параллельных агентов для распределённой обработки и анализа.

## Агенты

### audit_agent
Автоматически запускает CEB-E аудит по расписанию или при изменениях.

### metrics_agent
Собирает и агрегирует метрики системы, обновляет cursor-metrics.json.

### digest_agent
Генерирует ежедневные дайджесты и анализирует информационную плотность.

### validation_agent
Выполняет SAFE+CoVe проверки и отчёты о проблемах.

## Использование

Каждый агент работает независимо, изолирован через git worktrees или процессы.

```bash
# Запуск агента напрямую (без изоляции)
python .cursor/agents/audit_agent.py

# Запуск агента с изоляцией (рекомендуется)
python scripts/agents/spawn_isolated.py --agent audit --script .cursor/agents/audit_agent.py

# Запуск всех агентов с изоляцией
python scripts/agents/run_all_agents.py

# Запуск конкретных агентов
python scripts/agents/run_all_agents.py --agents audit metrics

# Параллельный запуск
python scripts/agents/run_all_agents.py --parallel

# Одноразовый запуск
python scripts/agents/run_all_agents.py --once
```

## Изоляция

Для параллельной работы агенты используют:
- Отдельные git worktrees (`.git/worktrees/agent-*/`)
- Локальные лог-файлы
- Изолированные директории для временных данных












