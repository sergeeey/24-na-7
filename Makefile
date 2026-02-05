.PHONY: help test test-asr-latency test-asr-accuracy test-asr-offline test-all lint format install audit-checklist

help:
	@echo "Reflexio 24/7 — Available commands:"
	@echo "  make test              - Run all tests"
	@echo "  make test-asr-latency - Test ASR latency"
	@echo "  make test-asr-accuracy - Test ASR accuracy (WER)"
	@echo "  make test-asr-offline - Test offline transcription (≥ 30 min)"
	@echo "  make test-all         - Run all tests with coverage"
	@echo "  make lint             - Run linters"
	@echo "  make format           - Format code"
	@echo "  make install          - Install dependencies"
	@echo "  make audit-checklist  - Validate sprint checklist"
	@echo "  make update-metrics   - Update metrics from test reports"
	@echo "  make update-metrics-dry-run - Check what metrics would be updated"
	@echo "  make measure-metrics  - Run tests and measure metrics directly"

test:
	pytest tests/ -v

test-asr-latency:
	pytest tests/test_asr_latency.py -v

test-asr-accuracy:
	pytest tests/test_asr_accuracy.py -v

test-asr-offline:
	@echo "Running ASR Offline Tests..."
	pytest tests/test_asr_offline.py -v --test-offline

test-all:
	pytest tests/ -v --cov=src --cov-report=html

lint:
	ruff check src tests
	mypy src --ignore-missing-imports

format:
	ruff format src tests
	black src tests

install:
	pip install -e ".[dev]"

audit-checklist:
	@echo "Validating sprint checklist..."
	python scripts/validate_checklist.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --output docs/history/sprint_checklist_audit.json
	@echo ""
	@echo "Checklist audit complete. Report: docs/history/sprint_checklist_audit.json"

update-metrics:
	@echo "Updating metrics from test reports..."
	python scripts/auto_measure.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --report tests/.report.json
	@echo ""
	@echo "Metrics updated. Run 'make audit-checklist' to verify."

update-metrics-dry-run:
	@echo "Dry-run: Checking what metrics would be updated..."
	python scripts/auto_measure.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --report tests/.report.json --dry-run

measure-metrics:
	@echo "Running tests and measuring metrics directly..."
	python scripts/measure_metrics.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml --metric all
