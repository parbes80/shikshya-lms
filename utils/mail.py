import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template

logger = logging.getLogger(__name__)


def send_email(to_email, subject, text_body, html_body=None):
    config = current_app.config
    server = config.get('MAIL_SERVER', '')
    port = config.get('MAIL_PORT', 587)
    use_tls = config.get('MAIL_USE_TLS', True)
    username = config.get('MAIL_USERNAME', '')
    password = config.get('MAIL_PASSWORD', '')
    sender = config.get('MAIL_DEFAULT_SENDER', username)

    if not server or not username:
        logger.warning(f"Mail not configured. Would send to {to_email}: {subject}")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to_email

    msg.attach(MIMEText(text_body, 'plain'))
    if html_body:
        msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(server, port) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls()
                smtp.ehlo()
            if username and password:
                smtp.login(username, password)
            smtp.sendmail(sender, [to_email], msg.as_string())
        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_password_reset_email(user, reset_link):
    subject = f"{current_app.config['SITE_NAME']} — Password Reset"
    text_body = (
        f"Hello {user.username},\n\n"
        f"You requested a password reset.\n\n"
        f"Click the link below to set a new password (valid for 24 hours):\n"
        f"{reset_link}\n\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"— {current_app.config['SITE_NAME']} Team"
    )
    html_body = render_template('emails/password_reset.html',
                                 username=user.username,
                                 reset_link=reset_link,
                                 site_name=current_app.config['SITE_NAME'])
    return send_email(user.email, subject, text_body, html_body)


def send_notification_email(user, title, message):
    subject = f"{current_app.config['SITE_NAME']} — {title}"
    text_body = (
        f"Hello {user.username},\n\n"
        f"{message}\n\n"
        f"— {current_app.config['SITE_NAME']} Team"
    )
    return send_email(user.email, subject, text_body)
