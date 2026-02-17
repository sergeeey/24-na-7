# 🔬 Автоматическое измерение метрик — Руководство

**Reflexio v2.1 — Surpass Smart Noter Sprint**

---

## 🎯 Обзор

Система автоматического измерения метрик позволяет:
- Собирать метрики из тестов автоматически
- Обновлять чеклист после прогонов
- Интегрироваться с CI/CD для непрерывного мониторинга

---

## 🛠️ Инструменты

### 1. `scripts/auto_measure.py` — Автоматическое обновление из JSON отчётов

**Назначение:** Парсит pytest JSON отчёт и обновляет метрики в чеклисте.

**Использование:**
```bash
# Сначала запустите тесты с JSON отчётом
pytest tests/ -v --json-report --json-report-file=tests/.report.json

# Затем обновите метрики
python scripts/auto_measure.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --report tests/.report.json

# Или через Makefile
make update-metrics
```

**Dry-run режим:**
```bash
python scripts/auto_measure.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --report tests/.report.json --dry-run
make update-metrics-dry-run
```

### 2. `scripts/measure_metrics.py` — Прямые измерения

**Назначение:** Запускает тесты напрямую и измеряет метрики в реальном времени.

**Использование:**
```bash
# Измерить все метрики
python scripts/measure_metrics.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --metric all

# Или конкретную метрику
python scripts/measure_metrics.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --metric wer
python scripts/measure_metrics.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --metric latency
python scripts/measure_metrics.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --metric offline

# Или через Makefile
make measure-metrics
```

---

## 📊 Поддерживаемые метрики

### ASR Layer (epic_i_asr)

| Метрика | Источник | Команда |
|---------|----------|---------|
| WER | `tests/test_asr_accuracy.py` | `make measure-metrics` или `--metric wer` |
| Latency | `tests/test_asr_latency.py` | `make measure-metrics` или `--metric latency` |
| Офлайн транскрипция | `tests/test_asr_offline.py` | `make measure-metrics` или `--metric offline` |

### LLM Layer (epic_ii_llm)

| Метрика | Источник | Статус |
|---------|----------|--------|
| Factual consistency | Тесты summarizer | Планируется |
| DeepConf score | Тесты critic | Планируется |
| Token entropy | Тесты summarizer | Планируется |

---

## 🔄 Интеграция с CI/CD

### GitHub Actions

Метрики автоматически обновляются после тестов:

```yaml
- name: Run tests
  run: |
    pytest tests/ -v --json-report --json-report-file=tests/.report.json

- name: Update metrics from tests
  if: always()
  run: |
    python scripts/auto_measure.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --report tests/.report.json --dry-run
```

**Примечание:** В CI используется `--dry-run` для проверки, но не для изменения чеклиста. Для реального обновления нужно запустить локально или через отдельный workflow.

---

## 📝 Формат метрик в чеклисте

Метрики обновляются в формате:

```yaml
metrics:
  - name: "WER"
    target: "≤ 10%"
    current: "8.5%"  # ← Автоматически обновляется
    status: "completed"
```

---

## 🧪 Примеры использования

### Локальная разработка

```bash
# 1. Запустить тесты
pytest tests/test_asr_accuracy.py -v

# 2. Обновить метрики из отчёта
make update-metrics

# 3. Проверить валидность чеклиста
make audit-checklist
```

### Перед коммитом

```bash
# 1. Запустить все тесты
make test-all

# 2. Обновить метрики
make update-metrics

# 3. Проверить чеклист
make audit-checklist

# 4. Создать снапшот
python scripts/snapshot_checklist.py
```

### После релиза

```bash
# 1. Измерить все метрики напрямую
make measure-metrics

# 2. Обновить чеклист
make update-metrics

# 3. Создать финальный снапшот
python scripts/snapshot_checklist.py

# 4. Проверить валидность
make audit-checklist
```

---

## 🔍 Отладка

### Проблема: Метрики не обновляются

**Решение:**
1. Проверьте, что тесты выводят метрики в stdout:
   ```bash
   pytest tests/test_asr_accuracy.py -v -s
   ```

2. Проверьте JSON отчёт:
   ```bash
   cat tests/.report.json | jq '.tests[].call.stdout'
   ```

3. Запустите в dry-run режиме:
   ```bash
   make update-metrics-dry-run
   ```

### Проблема: Неправильные значения

**Решение:**
1. Проверьте регулярные выражения в `scripts/auto_measure.py`
2. Убедитесь, что тесты выводят метрики в правильном формате
3. Используйте `scripts/measure_metrics.py` для прямых измерений

---

## 📈 Расширение системы

### Добавление новой метрики

1. Добавьте функцию извлечения в `scripts/auto_measure.py`:
   ```python
   def extract_new_metric_from_tests(report: Dict[str, Any]) -> Optional[str]:
       # Ваша логика
       return value
   ```

2. Добавьте в `metric_extractors`:
   ```python
   ("epic_key", "Metric Name"): extract_new_metric_from_tests,
   ```

3. Обновите документацию

---

## ✅ Best Practices

1. **Всегда используйте dry-run перед реальным обновлением**
   ```bash
   make update-metrics-dry-run
   ```

2. **Создавайте снапшоты перед обновлением метрик**
   ```bash
   python scripts/snapshot_checklist.py
   make update-metrics
   ```

3. **Проверяйте валидность после обновления**
   ```bash
   make audit-checklist
   ```

4. **Коммитьте обновлённый чеклист вместе с кодом**
   ```bash
   git add .cursor/tasks/surpass_smart_noter_checklist.yaml
   git commit -m "Update metrics from test results"
   ```

---

## 🎯 Вектор зрелости

- ✅ **Self-validated** — чеклист валидируется автоматически
- ✅ **Self-measured** — метрики обновляются из тестов
- 🔄 **Self-optimized** — следующий уровень (автоматическая оптимизация на основе метрик)

---

**Подробнее:**
- `scripts/auto_measure.py` — код автоматического обновления
- `scripts/measure_metrics.py` — код прямых измерений
- `docs/CHECKLIST_AUDIT_FIXES.md` — документация по валидации





