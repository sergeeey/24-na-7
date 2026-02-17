# Prometheus & Grafana Setup для Reflexio 24/7

**Версия:** v4.1
**Дата:** 2026-02-17

---

## Обзор

Reflexio 24/7 v4.1 предоставляет comprehensive Prometheus metrics endpoint для мониторинга production системы.

### Доступные метрики

| Категория | Метрики | Описание |
|-----------|---------|----------|
| **Core** | `reflexio_transcriptions_total`, `reflexio_facts_total`, `reflexio_digests_total` | Базовые counters |
| **CoVe** | `reflexio_cove_enabled`, `reflexio_cove_avg_confidence_24h`, `reflexio_cove_avg_verification_rounds_24h` | Hallucination detection |
| **Fact Quality** | `reflexio_hallucination_rate_24h`, `reflexio_citation_coverage_24h`, `reflexio_atomicity_violations_24h` | Quality metrics |
| **Retention** | `reflexio_retention_operations_7d`, `reflexio_retention_deleted_records_7d`, `reflexio_retention_errors_7d` | Data retention |
| **ProcessLock** | `reflexio_active_locks`, `reflexio_stale_locks` | Process isolation |

---

## 1. Prometheus Configuration

### Установка Prometheus

**Docker Compose:**
```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: reflexio-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'

volumes:
  prometheus_data:
```

### Prometheus Config

**prometheus.yml:**
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'reflexio'
    static_configs:
      - targets: ['host.docker.internal:8000']  # Linux: 'localhost:8000'
    metrics_path: '/metrics/prometheus'
    scrape_interval: 30s
```

**Запуск:**
```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

**Проверка:**
- Prometheus UI: http://localhost:9090
- Targets: http://localhost:9090/targets (должен быть `reflexio` в состоянии UP)

---

## 2. Grafana Dashboard

### Установка Grafana

**Добавить в docker-compose.monitoring.yml:**
```yaml
services:
  # ... prometheus ...

  grafana:
    image: grafana/grafana:latest
    container_name: reflexio-grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    depends_on:
      - prometheus

volumes:
  prometheus_data:
  grafana_data:
```

**Запуск:**
```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

**Доступ:**
- Grafana UI: http://localhost:3000
- Login: `admin` / `admin` (сменить при первом входе)

### Добавление Prometheus Data Source

1. Открыть Grafana → Configuration → Data Sources
2. Add data source → Prometheus
3. URL: `http://prometheus:9090` (внутри Docker network)
4. Save & Test

### Импорт Dashboard

**Создать файл `grafana/dashboards/reflexio-v4.1.json`:**
```json
{
  "dashboard": {
    "title": "Reflexio 24/7 v4.1 Production Metrics",
    "uid": "reflexio-v41",
    "panels": [
      {
        "id": 1,
        "title": "Hallucination Rate (24h)",
        "type": "graph",
        "targets": [
          {
            "expr": "reflexio_hallucination_rate_24h",
            "legendFormat": "Hallucination Rate"
          }
        ],
        "alert": {
          "name": "High Hallucination Rate",
          "conditions": [
            {
              "evaluator": {
                "params": [0.005],
                "type": "gt"
              },
              "operator": {
                "type": "and"
              },
              "query": {
                "params": ["A", "5m", "now"]
              },
              "reducer": {
                "params": [],
                "type": "avg"
              },
              "type": "query"
            }
          ]
        }
      },
      {
        "id": 2,
        "title": "Citation Coverage (24h)",
        "type": "graph",
        "targets": [
          {
            "expr": "reflexio_citation_coverage_24h",
            "legendFormat": "Citation Coverage"
          }
        ]
      },
      {
        "id": 3,
        "title": "CoVe Confidence (24h)",
        "type": "graph",
        "targets": [
          {
            "expr": "reflexio_cove_avg_confidence_24h",
            "legendFormat": "Avg CoVe Confidence"
          }
        ]
      },
      {
        "id": 4,
        "title": "Retention Operations (7d)",
        "type": "stat",
        "targets": [
          {
            "expr": "reflexio_retention_operations_7d",
            "legendFormat": "Total Operations"
          }
        ]
      },
      {
        "id": 5,
        "title": "Retention Errors (7d)",
        "type": "stat",
        "targets": [
          {
            "expr": "reflexio_retention_errors_7d",
            "legendFormat": "Errors"
          }
        ]
      },
      {
        "id": 6,
        "title": "Active ProcessLocks",
        "type": "stat",
        "targets": [
          {
            "expr": "reflexio_active_locks",
            "legendFormat": "Active Locks"
          }
        ]
      }
    ]
  }
}
```

**Импорт:**
1. Grafana → Dashboards → Import
2. Paste JSON → Load
3. Select Prometheus data source → Import

---

## 3. Production Alerts

### Alert Rules (Prometheus)

**Создать `alerts/reflexio-rules.yml`:**
```yaml
groups:
  - name: reflexio_alerts
    interval: 1m
    rules:
      # High hallucination rate
      - alert: HighHallucinationRate
        expr: reflexio_hallucination_rate_24h > 0.005
        for: 5m
        labels:
          severity: critical
          service: reflexio
        annotations:
          summary: "High hallucination rate detected"
          description: "Hallucination rate is {{ $value | humanizePercentage }}, exceeds threshold of 0.5%"

      # Low citation coverage
      - alert: LowCitationCoverage
        expr: reflexio_citation_coverage_24h < 0.95
        for: 10m
        labels:
          severity: warning
          service: reflexio
        annotations:
          summary: "Low citation coverage"
          description: "Citation coverage is {{ $value | humanizePercentage }}, below target of 98%"

      # CoVe confidence drop
      - alert: LowCoVeConfidence
        expr: reflexio_cove_avg_confidence_24h < 0.70
        for: 10m
        labels:
          severity: warning
          service: reflexio
        annotations:
          summary: "Low CoVe confidence"
          description: "Average CoVe confidence is {{ $value }}, below threshold of 0.70"

      # Retention errors
      - alert: RetentionErrors
        expr: delta(reflexio_retention_errors_7d[1h]) > 0
        for: 1m
        labels:
          severity: warning
          service: reflexio
        annotations:
          summary: "Retention operation errors"
          description: "Retention errors detected in last hour"

      # Stale ProcessLocks
      - alert: StaleProcessLocks
        expr: reflexio_stale_locks > 0
        for: 5m
        labels:
          severity: warning
          service: reflexio
        annotations:
          summary: "Stale process locks detected"
          description: "{{ $value }} stale locks (>1h old)"
```

**Добавить в prometheus.yml:**
```yaml
rule_files:
  - 'alerts/reflexio-rules.yml'

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']  # Alertmanager
```

---

## 4. Alertmanager Integration

### Alertmanager для Slack/Email

**Установка:**
```yaml
# docker-compose.monitoring.yml
services:
  # ... prometheus, grafana ...

  alertmanager:
    image: prom/alertmanager:latest
    container_name: reflexio-alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
```

**alertmanager.yml:**
```yaml
global:
  slack_api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'

route:
  receiver: 'reflexio-alerts'
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 3h

receivers:
  - name: 'reflexio-alerts'
    slack_configs:
      - channel: '#reflexio-alerts'
        title: '{{ .GroupLabels.severity | toUpper }} - {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
    email_configs:
      - to: 'ops@example.com'
        from: 'alertmanager@reflexio.local'
        smarthost: 'smtp.gmail.com:587'
        auth_username: 'alerts@example.com'
        auth_password: 'YOUR_PASSWORD'
        headers:
          Subject: '[Reflexio] {{ .GroupLabels.alertname }}'
```

---

## 5. Быстрый старт

### Полный stack (Prometheus + Grafana + Alertmanager)

**1. Создать структуру:**
```bash
mkdir -p monitoring/{prometheus,grafana,alertmanager}
cd monitoring
```

**2. Скопировать конфиги:**
- `prometheus/prometheus.yml`
- `prometheus/alerts/reflexio-rules.yml`
- `grafana/dashboards/reflexio-v4.1.json`
- `alertmanager/alertmanager.yml`
- `docker-compose.monitoring.yml`

**3. Запустить stack:**
```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

**4. Проверить:**
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Alertmanager: http://localhost:9093

**5. Импортировать dashboard в Grafana**

---

## 6. Примеры запросов (PromQL)

### Hallucination Rate Trend
```promql
rate(reflexio_hallucination_rate_24h[1h])
```

### Citation Coverage по времени
```promql
avg_over_time(reflexio_citation_coverage_24h[6h])
```

### Retention Performance
```promql
sum(increase(reflexio_retention_deleted_records_7d[1d]))
```

### CoVe Effectiveness
```promql
histogram_quantile(0.95, reflexio_cove_avg_confidence_24h)
```

---

## 7. Production Recommendations

### SLA Targets

| Метрика | Target | Alert Threshold |
|---------|--------|-----------------|
| **Hallucination Rate** | ≤0.5% | >0.5% for 5min |
| **Citation Coverage** | ≥98% | <95% for 10min |
| **CoVe Confidence** | ≥0.70 | <0.70 for 10min |
| **Retention Errors** | 0 | >0 in 1h |
| **Stale Locks** | 0 | >0 for 5min |

### Retention

- **Prometheus TSDB:** 15 days (default)
- **Long-term storage:** Thanos, Cortex, Victoria Metrics
- **Grafana snapshots:** Backup dashboard JSON monthly

---

## 8. Troubleshooting

### Метрики не отображаются

**Проблема:** Prometheus не может scrape `/metrics/prometheus`

**Решение:**
```bash
# Проверить endpoint вручную
curl http://localhost:8000/metrics/prometheus

# Проверить Prometheus targets
curl http://localhost:9090/api/v1/targets
```

### Grafana показывает "No data"

**Проблема:** Неверный data source или query

**Решение:**
1. Grafana → Data Sources → Prometheus → Test
2. Проверить PromQL query в Explore

### Alertmanager не отправляет alerts

**Проблема:** Неверная конфигурация webhook/SMTP

**Решение:**
```bash
# Проверить логи
docker logs reflexio-alertmanager

# Тест webhook вручную
curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
  -H 'Content-Type: application/json' \
  -d '{"text": "Test alert"}'
```

---

**Готово! Reflexio 24/7 v4.1 теперь имеет production-grade monitoring.**
