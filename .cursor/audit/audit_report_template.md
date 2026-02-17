# Cursor Enhancement Blueprint — Эталонный Аудит v1.0

**Дата:** {{date}}  
**Проект:** {{project_name}}  
**Аудитор:** {{auditor}}  
**Стандарт:** {{standard}}  
**Режим:** {{mode}}

---

## 1. Общая оценка

| Метрика | Значение |
|---------|----------|
| Уровень зрелости | {{level}} / 5 — **{{level_name}}** |
| Общий балл | {{score}} / {{max_score}} |
| AI Reliability Index | {{ai_reliability_index}} |
| Context Hit Rate | {{context_hit_rate}} |

---

## 2. Ключевые результаты

### Детальная проверка компонентов

{{#components}}

#### {{component_name}}

**Результат:** {{result}}  
**Балл:** {{score}} / {{max_score}}  

{{#details}}
- ✅ {{.}}
{{/details}}

{{#issues}}
- ⚠️ {{.}}
{{/issues}}

{{/components}}

---

### Сводная таблица

| № | Компонент | Балл | Статус | Детали |
|---|-----------|------|--------|--------|
| 1 | Rules Engine | {{rules_engine.score}} / 15 | {{rules_engine.result}} | {{rules_engine.details_summary}} |
| 2 | Memory Bank 2.0 | {{memory_bank.score}} / 10 | {{memory_bank.result}} | {{memory_bank.details_summary}} |
| 3 | MCP Gateway | {{mcp_gateway.score}} / 10 | {{mcp_gateway.result}} | {{mcp_gateway.details_summary}} |
| 4 | Hooks System | {{hooks_system.score}} / 10 | {{hooks_system.result}} | {{hooks_system.details_summary}} |
| 5 | Validation (SAFE+CoVe) | {{validation_framework.score}} / 15 | {{validation_framework.result}} | {{validation_framework.details_summary}} |
| 6 | Observability | {{observability.score}} / 10 | {{observability.result}} | {{observability.details_summary}} |
| 7 | Governance Loop | {{governance_loop.score}} / 10 | {{governance_loop.result}} | {{governance_loop.details_summary}} |
| 8 | Playbooks Suite | {{playbooks_suite.score}} / 10 | {{playbooks_suite.result}} | {{playbooks_suite.details_summary}} |
| 9 | Multi-Agent System | {{multi_agent.score}} / 10 | {{multi_agent.result}} | {{multi_agent.details_summary}} |

**Итог:** {{score}} / {{max_score}} — {{summary}}

---

## 3. Уровень зрелости: {{level}} / 5 — {{level_name}}

### Критерии уровней

- **5 (Self-Adaptive):** Все компоненты включены, Governance Loop активен, AI Reliability ≥ 0.95
- **4 (Automated):** Все модули включены, но профиль переключается вручную
- **3 (Pro):** Активны Rules, Playbooks, MCP и Validation
- **2 (Foundational):** Есть только Rules и Memory Bank
- **1-0 (Initial):** `.cursor/` отсутствует или структура нарушена

### Текущее состояние

**Ваш проект находится на уровне {{level_name}}.**

{{#is_level_5}}
✅ Проект соответствует эталонной архитектуре CEB-E v1.0 на максимальном уровне.
{{/is_level_5}}

{{^is_level_5}}
⚠️ Для достижения уровня Self-Adaptive требуется доработка компонентов.
{{/is_level_5}}

---

## 4. Рекомендации

{{#recommendations}}
- {{.}}
{{/recommendations}}

{{^recommendations}}
### Общие рекомендации

Проект соответствует высоким стандартам CEB-E v1.0. Рекомендуется:
- Подключить метрики latency в Prometheus/Grafana
- Добавить интеграцию с Slack через MCP
- Ввести еженедельный автоаудит в CI/CD
{{/recommendations}}

---

## 5. Детальный анализ компонентов

{{#components_detailed}}

### {{name}}

**Статус:** {{status}}  
**Балл:** {{score}} / {{max_score}}

{{description}}

**Детали проверки:**
{{#checks}}
- {{.}}
{{/checks}}

**Выявленные проблемы:**
{{#issues}}
- ⚠️ {{.}}
{{/issues}}

{{^issues}}
- ✅ Проблем не обнаружено
{{/issues}}

{{/components_detailed}}

---

## 6. Заключение

Проект **{{project_name}}** соответствует эталонной архитектуре Cursor Enhancement Blueprint Evaluation v1.0 на уровне **{{level_name}}**.

**AI Reliability Index:** {{ai_reliability_index}}  
**Context Hit Rate:** {{context_hit_rate}}

{{#is_level_5}}
Среда выполняет все требования самоадаптации и самоконтроля. Все компоненты CEB-E v1.0 активны и работают корректно.
{{/is_level_5}}

{{^is_level_5}}
Для достижения уровня Self-Adaptive рекомендуется выполнить рекомендации из раздела 4.
{{/is_level_5}}

---

*Отчёт сгенерирован автоматически системой CEB-E Audit Pack v1.0*
