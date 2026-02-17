# Reflexio Methodology Core (RMC)

**Фундаментальная база правил, моделей и верификационных стандартов для Reflexio 24/7**

---

## 📚 Содержание

- **[Predictive Analytics Foundation](predictive_analytics_foundation.md)** — методологические принципы и стандарты
- **[Methodology Registry](methodology_registry.json)** — реестр методологий и версий
- **[Integrity Policy](integrity_policy.yaml)** — правила соответствия и контроля

---

## 🎯 Назначение

Reflexio Methodology Core определяет методологические стандарты для всех компонентов системы:

- **DeepConf Feedback Loop** — калибровка уверенности с Bayesian UQ
- **Adaptive Mission Scoring** — оценка миссий на основе метрик
- **Memory Curation Agent** — управление знаниями с DQ-метриками
- **Governance Loop** — самопроверка на соответствие методологии
- **OSINT KDS** — предиктивная аналитика с RAG

---

## 🔍 Проверка соответствия

### Быстрая проверка

```bash
python scripts/check_methodology_integrity.py
```

### Через playbook

```bash
@playbook audit
```

Проверка методологии автоматически включается в системный аудит.

---

## 📊 Уровни соответствия

### Required (Обязательные)
- DeepConf Bayesian UQ
- Memory Bank DQ Metrics
- Source Attribution
- Governance Methodology Check

### Recommended (Рекомендуемые)
- RAG Layer Activation
- Adaptive Mission Scoring
- Closed-Loop Learning

### Optional (Опциональные)
- Explainability SHAP/LIME
- Bayesian Neural Networks
- Automatic Explainability Reports

---

## 🔄 Интеграция

### Governance Profile

Методологическое соответствие отслеживается в:
`.cursor/governance/profile.yaml`

```yaml
methodology_compliance:
  active: true
  registry: docs/Reflexio_Methodology/methodology_registry.json
  policy: docs/Reflexio_Methodology/integrity_policy.yaml
  enforcement: audit
```

### Audit Reports

Результаты проверки включаются в:
`.cursor/audit/methodology_compliance_report.json`

---

## 📈 Метрики

- **Compliance Score** — общий балл соответствия (0-100%)
- **Required Rules** — обязательные правила (weight: 1.0)
- **Recommended Rules** — рекомендуемые правила (weight: 0.7)
- **Optional Rules** — опциональные правила (weight: 0.3)

---

## 🎯 Цель

Обеспечить методологически самопроверяющуюся систему, где:

- Каждый компонент соответствует стандартам
- Методологические требования проверяются автоматически
- Система адаптируется на основе compliance метрик

---

**Reflexio 24/7 — Methodologically Self-Checking System** 🎯✨













