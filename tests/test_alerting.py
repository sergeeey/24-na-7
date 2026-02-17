"""Тесты для alerting (v4.1)."""
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
import requests

from src.monitoring.alerting import Alert, AlertManager, AlertSeverity, send_alert


class TestAlert:
    """Тесты для Alert класса."""

    def test_alert_creation(self):
        """Тест: создание Alert объекта."""
        alert = Alert(
            name="TestAlert",
            severity=AlertSeverity.WARNING,
            message="Test message",
            details={"key": "value"},
        )

        assert alert.name == "TestAlert"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.message == "Test message"
        assert alert.details == {"key": "value"}
        assert isinstance(alert.timestamp, datetime)

    def test_alert_to_dict(self):
        """Тест: конвертация Alert в dict."""
        alert = Alert(
            name="TestAlert",
            severity=AlertSeverity.CRITICAL,
            message="Critical issue",
        )

        alert_dict = alert.to_dict()

        assert alert_dict["name"] == "TestAlert"
        assert alert_dict["severity"] == "critical"
        assert alert_dict["message"] == "Critical issue"
        assert "timestamp" in alert_dict


class TestAlertManager:
    """Тесты для AlertManager."""

    def test_init_with_config(self):
        """Тест: инициализация с конфигурацией."""
        manager = AlertManager(
            slack_webhook_url="https://hooks.slack.com/test",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="test@example.com",
            smtp_password="password",
            email_from="alerts@reflexio.local",
            email_to=["ops@example.com"],
        )

        assert manager.slack_webhook_url == "https://hooks.slack.com/test"
        assert manager.smtp_host == "smtp.gmail.com"
        assert manager.email_from == "alerts@reflexio.local"
        assert manager.email_to == ["ops@example.com"]

    def test_rate_limiting(self):
        """Тест: rate limiting для alerts."""
        manager = AlertManager()
        manager._rate_limit_minutes = 1  # Для теста сократим до 1 минуты

        alert = Alert(
            name="TestAlert",
            severity=AlertSeverity.WARNING,
            message="Test",
        )

        # Первый раз — должен пройти
        assert manager._should_send_alert(alert) is True

        # Записываем в историю
        manager._record_alert(alert)

        # Сразу после — rate limited
        assert manager._should_send_alert(alert) is False

        # Искусственно меняем timestamp (как будто прошла 1 минута)
        manager._alert_history[alert.name] = datetime.now() - timedelta(minutes=2)

        # Теперь должен пройти
        assert manager._should_send_alert(alert) is True

    @patch("requests.post")
    def test_send_slack_success(self, mock_post):
        """Тест: успешная отправка в Slack."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        manager = AlertManager(
            slack_webhook_url="https://hooks.slack.com/test"
        )

        alert = Alert(
            name="HighHallucinationRate",
            severity=AlertSeverity.CRITICAL,
            message="Hallucination rate 1.2%",
            details={"current_rate": 0.012},
        )

        # Отправка
        manager._send_slack(alert)

        # Проверяем что POST был вызван
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Проверяем URL
        assert call_args[0][0] == "https://hooks.slack.com/test"

        # Проверяем payload
        payload = call_args[1]["json"]
        assert "Reflexio Alert" in payload["text"]
        assert payload["attachments"][0]["title"] == "HighHallucinationRate"

    @patch("smtplib.SMTP")
    def test_send_email_success(self, mock_smtp):
        """Тест: успешная отправка email."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        manager = AlertManager(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="test@example.com",
            smtp_password="password",
            email_from="alerts@reflexio.local",
            email_to=["ops@example.com"],
        )

        alert = Alert(
            name="LowCitationCoverage",
            severity=AlertSeverity.WARNING,
            message="Citation coverage 94%",
            details={"current": 0.94, "target": 0.98},
        )

        # Отправка
        manager._send_email(alert)

        # Проверяем что SMTP методы были вызваны
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@example.com", "password")
        mock_server.send_message.assert_called_once()

    @patch("requests.post")
    @patch("smtplib.SMTP")
    def test_send_alert_both_channels(self, mock_smtp, mock_post):
        """Тест: отправка alert по обоим каналам."""
        # Mock Slack
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Mock SMTP
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        manager = AlertManager(
            slack_webhook_url="https://hooks.slack.com/test",
            smtp_host="smtp.gmail.com",
            email_from="alerts@reflexio.local",
            email_to=["ops@example.com"],
        )

        alert = Alert(
            name="RetentionError",
            severity=AlertSeverity.WARNING,
            message="Retention operation failed",
        )

        # Отправка
        result = manager.send_alert(alert, send_slack=True, send_email=True)

        assert result is True
        mock_post.assert_called_once()
        mock_server.send_message.assert_called_once()

    def test_send_alert_rate_limited(self):
        """Тест: rate limited alert не отправляется."""
        manager = AlertManager(
            slack_webhook_url="https://hooks.slack.com/test"
        )
        manager._rate_limit_minutes = 1

        alert = Alert(
            name="TestAlert",
            severity=AlertSeverity.INFO,
            message="Test",
        )

        # Первый раз — успех
        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            result1 = manager.send_alert(alert, send_slack=True, send_email=False)
            assert result1 is True
            assert mock_post.call_count == 1

        # Сразу второй раз — rate limited
        with patch("requests.post") as mock_post:
            result2 = manager.send_alert(alert, send_slack=True, send_email=False)
            assert result2 is False
            assert mock_post.call_count == 0  # Не вызывался

    def test_email_not_configured(self):
        """Тест: email не отправляется если не сконфигурирован."""
        manager = AlertManager()  # Без SMTP config

        assert manager._email_configured() is False

        alert = Alert(
            name="TestAlert",
            severity=AlertSeverity.INFO,
            message="Test",
        )

        # Email не отправится (нет exception)
        result = manager.send_alert(alert, send_slack=False, send_email=True)
        assert result is False


class TestSendAlertConvenience:
    """Тесты для send_alert() convenience function."""

    @patch("requests.post")
    def test_send_alert_function(self, mock_post):
        """Тест: send_alert() convenience function."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Mock settings для Slack webhook
        with patch("src.monitoring.alerting.settings") as mock_settings:
            mock_settings.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

            result = send_alert(
                name="TestAlert",
                severity=AlertSeverity.WARNING,
                message="Test message",
                details={"key": "value"},
                send_slack=True,
                send_email=False,
            )

            assert result is True
            mock_post.assert_called_once()


class TestAlertSeverity:
    """Тесты для AlertSeverity enum."""

    def test_severity_values(self):
        """Тест: значения severity enum."""
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.INFO.value == "info"

    def test_severity_comparison(self):
        """Тест: сравнение severity levels."""
        critical = AlertSeverity.CRITICAL
        warning = AlertSeverity.WARNING
        info = AlertSeverity.INFO

        assert critical != warning
        assert warning != info
        assert critical == AlertSeverity.CRITICAL
