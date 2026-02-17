"""
Drift Monitoring — мониторинг дрифта моделей LLM/ASR.

Отслеживает изменения в производительности моделей со временем.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from pathlib import Path
import json

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("monitor.drift")
except Exception:
    import logging
    logger = logging.getLogger("monitor.drift")


class DriftMonitor:
    """Мониторинг дрифта моделей."""
    
    def __init__(self, metrics_dir: Optional[Path] = None):
        """
        Инициализация мониторинга дрифта.
        
        Args:
            metrics_dir: Директория для хранения метрик дрифта
        """
        if metrics_dir is None:
            metrics_dir = Path("logs/drift")
        self.metrics_dir = metrics_dir
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        # Baseline метрики
        self.baseline_file = self.metrics_dir / "baseline.json"
        self.baseline = self._load_baseline()
    
    def _load_baseline(self) -> Dict[str, Any]:
        """Загружает baseline метрики."""
        if not self.baseline_file.exists():
            return {}
        
        try:
            with open(self.baseline_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("failed_to_load_baseline", error=str(e))
            return {}
    
    def _save_baseline(self, baseline: Dict[str, Any]):
        """Сохраняет baseline метрики."""
        try:
            with open(self.baseline_file, "w", encoding="utf-8") as f:
                json.dump(baseline, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("failed_to_save_baseline", error=str(e))
    
    def record_metric(
        self,
        metric_name: str,
        value: float,
        model: str,
        provider: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Записывает метрику для мониторинга дрифта.
        
        Args:
            metric_name: Название метрики (например, "wer", "latency", "confidence")
            value: Значение метрики
            model: Название модели
            provider: Провайдер (openai, anthropic, local)
            metadata: Дополнительные метаданные
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        metric_record = {
            "metric_name": metric_name,
            "value": value,
            "model": model,
            "provider": provider,
            "timestamp": timestamp,
            "metadata": metadata or {},
        }
        
        # Сохраняем в файл метрик
        metric_file = self.metrics_dir / f"{metric_name}_{model}_{provider}.jsonl"
        try:
            with open(metric_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(metric_record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("failed_to_record_metric", error=str(e))
        
        # Проверяем дрифт
        drift_status = self.check_drift(metric_name, value, model, provider)
        
        if drift_status["has_drift"]:
            logger.warning(
                "drift_detected",
                metric_name=metric_name,
                model=model,
                provider=provider,
                current_value=value,
                baseline_value=drift_status.get("baseline_value"),
                drift_percentage=drift_status.get("drift_percentage"),
                threshold=drift_status.get("threshold"),
            )
        
        return drift_status
    
    def check_drift(
        self,
        metric_name: str,
        current_value: float,
        model: str,
        provider: str = "unknown",
        threshold_percentage: float = 0.15  # 15% отклонение считается дрифтом
    ) -> Dict[str, Any]:
        """
        Проверяет наличие дрифта метрики.
        
        Args:
            metric_name: Название метрики
            current_value: Текущее значение
            model: Название модели
            provider: Провайдер
            threshold_percentage: Порог отклонения (в процентах)
            
        Returns:
            Словарь с информацией о дрифте
        """
        baseline_key = f"{metric_name}_{model}_{provider}"
        baseline_value = self.baseline.get(baseline_key)
        
        if baseline_value is None:
            # Устанавливаем baseline, если его нет
            self.baseline[baseline_key] = current_value
            self._save_baseline(self.baseline)
            
            logger.info(
                "baseline_set",
                metric_name=metric_name,
                model=model,
                provider=provider,
                baseline_value=current_value,
            )
            
            return {
                "has_drift": False,
                "baseline_value": current_value,
                "current_value": current_value,
                "drift_percentage": 0.0,
                "threshold": threshold_percentage,
            }
        
        # Вычисляем процент отклонения
        if baseline_value == 0:
            drift_percentage = float("inf") if current_value != 0 else 0.0
        else:
            drift_percentage = abs((current_value - baseline_value) / baseline_value) * 100
        
        has_drift = drift_percentage > (threshold_percentage * 100)
        
        return {
            "has_drift": has_drift,
            "baseline_value": baseline_value,
            "current_value": current_value,
            "drift_percentage": drift_percentage,
            "threshold": threshold_percentage * 100,
        }
    
    def get_drift_history(
        self,
        metric_name: str,
        model: str,
        provider: str = "unknown",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Получает историю метрики для анализа тренда.
        
        Args:
            metric_name: Название метрики
            model: Название модели
            provider: Провайдер
            limit: Максимальное количество записей
            
        Returns:
            Список записей метрик
        """
        metric_file = self.metrics_dir / f"{metric_name}_{model}_{provider}.jsonl"
        
        if not metric_file.exists():
            return []
        
        try:
            records = []
            with open(metric_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-limit:]:  # Последние N записей
                    try:
                        records.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
            
            return records
        except Exception as e:
            logger.error("failed_to_get_drift_history", error=str(e))
            return []
    
    def update_baseline(
        self,
        metric_name: str,
        model: str,
        provider: str = "unknown",
        new_baseline: Optional[float] = None
    ):
        """
        Обновляет baseline метрики.
        
        Args:
            metric_name: Название метрики
            model: Название модели
            provider: Провайдер
            new_baseline: Новое значение baseline (если None, вычисляется из истории)
        """
        baseline_key = f"{metric_name}_{model}_{provider}"
        
        if new_baseline is None:
            # Вычисляем среднее из последних 100 записей
            history = self.get_drift_history(metric_name, model, provider, limit=100)
            if history:
                values = [r["value"] for r in history]
                new_baseline = sum(values) / len(values)
            else:
                logger.warning("no_history_to_compute_baseline", metric_name=metric_name, model=model)
                return
        
        self.baseline[baseline_key] = new_baseline
        self._save_baseline(self.baseline)
        
        logger.info(
            "baseline_updated",
            metric_name=metric_name,
            model=model,
            provider=provider,
            new_baseline=new_baseline,
        )


# Глобальный экземпляр мониторинга дрифта
_drift_monitor: Optional[DriftMonitor] = None


def get_drift_monitor() -> DriftMonitor:
    """Получает глобальный экземпляр мониторинга дрифта."""
    global _drift_monitor
    if _drift_monitor is None:
        _drift_monitor = DriftMonitor()
    return _drift_monitor

