import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


logger = logging.getLogger("app.email")


def send_account_email(to_email: str, subject: str, text: str) -> bool:
    settings = get_settings()
    if not settings.email_delivery_enabled:
        logger.warning("Account email skipped: SMTP is not configured (recipient=%s)", to_email)
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return True
    except Exception:
        logger.exception("Could not deliver account email to %s", to_email)
        return False


def send_verification_email(to_email: str, display_name: str, link: str) -> bool:
    return send_account_email(
        to_email,
        "Kawaui ID: подтвердите email / Verify your email",
        f"Здравствуйте, {display_name or 'игрок'}!\n\nПодтвердите email Kawaui ID:\n{link}\n\n"
        "Ссылка действует ограниченное время. Если это были не вы, проигнорируйте письмо.\n\n"
        "Verify your Kawaui ID email using the link above. If you did not request this, ignore this email.",
    )


def send_password_reset_email(to_email: str, display_name: str, link: str) -> bool:
    return send_account_email(
        to_email,
        "Kawaui ID: восстановление пароля / Password reset",
        f"Здравствуйте, {display_name or 'игрок'}!\n\nСоздайте новый пароль:\n{link}\n\n"
        "Ссылка одноразовая. Если это были не вы, ничего делать не нужно.\n\n"
        "Use the one-time link above to create a new password.",
    )


def send_new_login_email(to_email: str, device: str, occurred_at: str) -> bool:
    return send_account_email(
        to_email,
        "Kawaui ID: новый вход / New sign-in",
        f"Зафиксирован новый вход в Kawaui ID.\nУстройство: {device}\nВремя UTC: {occurred_at}\n\n"
        "Если это были не вы, смените пароль и завершите остальные сессии в профиле.\n\n"
        "If this was not you, change your password and revoke other sessions from your profile.",
    )
