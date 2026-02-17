"""Alerting utilities для Reflexio 24/7 v4.1.

Поддержка:
- Slack webhooks
- Email (SMTP)
- Alert deduplication (rate limiting)
"""
import json
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum

import requests

from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("monitoring.alerting")


class AlertSeverity(str, Enum):
    """Уровни severity для alerts."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Alert:
    """Структура alert."""

    def __init__(
        self,
        name: str,
        severity: AlertSeverity,
        message: str,
        details: Optional[Dict] = None,
    ):
        """Инициализация.

        Args:
            name: Имя alert (e.g., "HighHallucinationRate")
            severity: Уровень severity
            message: Краткое описание проблемы
            details: Дополнительные метаданные (dict)
        """
        self.name = name
        self.severity = severity
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict:
        """Конвертация в dict."""
        return {
            "name": self.name,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class AlertManager:
    """Менеджер для отправки alerts."""

    def __init__(
        self,
        slack_webhook_url: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_username: Optional[str] = None,
        smtp_password: Optional[str] = None,
        email_from: Optional[str] = None,
        email_to: Optional[List[str]] = None,
    ):
        """Инициализация.

        Args:
            slack_webhook_url: Slack webhook URL
            smtp_host: SMTP server host
            smtp_port: SMTP server port (default: 587 для TLS)
            smtp_username: SMTP username
            smtp_password: SMTP password
            email_from: Email sender
            email_to: Email recipients (list)
        """
        self.slack_webhook_url = slack_webhook_url or getattr(
            settings, "SLACK_WEBHOOK_URL", None
        )
        self.smtp_host = smtp_host or getattr(settings, "SMTP_HOST", None)
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username or getattr(settings, "SMTP_USERNAME", None)
        self.smtp_password = smtp_password or getattr(settings, "SMTP_PASSWORD", None)
        self.email_from = email_from or getattr(settings, "EMAIL_FROM", None)
        self.email_to = email_to or getattr(settings, "EMAIL_TO", "").split(",")

        # Rate limiting для deduplication
        self._alert_history: Dict[str, datetime] = {}
        self._rate_limit_minutes = 15  # Не чаще чем раз в 15 минут для каждого alert

    def send_alert(
        self,
        alert: Alert,
        send_slack: bool = True,
        send_email: bool = True,
    ) -> bool:
        """Отправить alert.

        Args:
            alert: Alert объект
            send_slack: Отправить в Slack
            send_email: Отправить по email

        Returns:
            True если успешно отправлен хотя бы одним способом
        """
        # Rate limiting check
        if not self._should_send_alert(alert):
            logger.info(
                f"alert_rate_limited: name={alert.name}, "
                f"last_sent={self._alert_history.get(alert.name)}"
            )
            return False

        success = False

        if send_slack and self.slack_webhook_url:
            try:
                self._send_slack(alert)
                success = True
                logger.info(f"alert_sent_to_slack: name={alert.name}")
            except Exception as e:
                logger.error(f"slack_alert_failed: name={alert.name}, error={e}")

        if send_email and self._email_configured():
            try:
                self._send_email(alert)
                success = True
                logger.info(f"alert_sent_to_email: name={alert.name}")
            except Exception as e:
                logger.error(f"email_alert_failed: name={alert.name}, error={e}")

        if success:
            self._record_alert(alert)

        return success

    def _should_send_alert(self, alert: Alert) -> bool:
        """Проверка rate limiting.

        Args:
            alert: Alert объект

        Returns:
            True если можно отправить (не rate limited)
        """
        last_sent = self._alert_history.get(alert.name)

        if last_sent is None:
            return True

        time_since_last = datetime.now() - last_sent
        return time_since_last >= timedelta(minutes=self._rate_limit_minutes)

    def _record_alert(self, alert: Alert):
        """Записать alert в историю для rate limiting."""
        self._alert_history[alert.name] = alert.timestamp

    def _send_slack(self, alert: Alert):
        """Отправить alert в Slack.

        Args:
            alert: Alert объект

        Raises:
            Exception: При ошибке отправки
        """
        if not self.slack_webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL not configured")

        # Slack emoji по severity
        emoji_map = {
            AlertSeverity.CRITICAL: ":rotating_light:",
            AlertSeverity.WARNING: ":warning:",
            AlertSeverity.INFO: ":information_source:",
        }
        emoji = emoji_map.get(alert.severity, ":bell:")

        # Color по severity
        color_map = {
            AlertSeverity.CRITICAL: "#FF0000",  # Red
            AlertSeverity.WARNING: "#FFA500",   # Orange
            AlertSeverity.INFO: "#0000FF",      # Blue
        }
        color = color_map.get(alert.severity, "#808080")

        # Slack attachment format
        payload = {
            "text": f"{emoji} *[Reflexio Alert] {alert.severity.value.upper()}*",
            "attachments": [
                {
                    "color": color,
                    "title": alert.name,
                    "text": alert.message,
                    "fields": [
                        {
                            "title": key,
                            "value": str(value),
                            "short": True,
                        }
                        for key, value in alert.details.items()
                    ],
                    "footer": "Reflexio 24/7 Monitoring",
                    "ts": int(alert.timestamp.timestamp()),
                }
            ],
        }

        response = requests.post(
            self.slack_webhook_url,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()

    def _send_email(self, alert: Alert):
        """Отправить alert по email.

        Args:
            alert: Alert объект

        Raises:
            Exception: При ошибке отправки
        """
        if not self._email_configured():
            raise ValueError("Email not configured (SMTP_HOST, EMAIL_FROM, EMAIL_TO)")

        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Reflexio Alert] {alert.severity.value.upper()} - {alert.name}"
        msg["From"] = self.email_from
        msg["To"] = ", ".join(self.email_to)

        # Plain text version
        text_body = f"""
Reflexio 24/7 Alert

Name: {alert.name}
Severity: {alert.severity.value.upper()}
Timestamp: {alert.timestamp.isoformat()}

Message:
{alert.message}

Details:
{json.dumps(alert.details, indent=2)}

---
Reflexio 24/7 Monitoring System
"""

        # HTML version
        html_body = f"""
<html>
  <head></head>
  <body>
    <h2>Reflexio 24/7 Alert</h2>
    <table border="1" cellpadding="5">
      <tr><td><b>Name</b></td><td>{alert.name}</td></tr>
      <tr><td><b>Severity</b></td><td style="color: {'red' if alert.severity == AlertSeverity.CRITICAL else 'orange'}"><b>{alert.severity.value.upper()}</b></td></tr>
      <tr><td><b>Timestamp</b></td><td>{alert.timestamp.isoformat()}</td></tr>
    </table>

    <h3>Message</h3>
    <p>{alert.message}</p>

    <h3>Details</h3>
    <pre>{json.dumps(alert.details, indent=2)}</pre>

    <hr>
    <small>Reflexio 24/7 Monitoring System</small>
  </body>
</html>
"""

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Send via SMTP
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)

    def _email_configured(self) -> bool:
        """Проверка конфигурации email."""
        return all([
            self.smtp_host,
            self.email_from,
            self.email_to,
        ])


# Convenience function для простых alerts
def send_alert(
    name: str,
    severity: AlertSeverity,
    message: str,
    details: Optional[Dict] = None,
    send_slack: bool = True,
    send_email: bool = True,
) -> bool:
    """Отправить alert (convenience function).

    Args:
        name: Имя alert
        severity: Уровень severity
        message: Краткое описание
        details: Дополнительные метаданные
        send_slack: Отправить в Slack
        send_email: Отправить по email

    Returns:
        True если успешно отправлен

    Example:
        >>> send_alert(
        ...     name="HighHallucinationRate",
        ...     severity=AlertSeverity.CRITICAL,
        ...     message="Hallucination rate 1.2% exceeds threshold of 0.5%",
        ...     details={"current_rate": 0.012, "threshold": 0.005},
        ... )
    """
    alert = Alert(name=name, severity=severity, message=message, details=details)
    manager = AlertManager()
    return manager.send_alert(alert, send_slack=send_slack, send_email=send_email)
