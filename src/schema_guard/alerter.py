import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_alert(violations):
    """
    Send an email alert with schema drift violations.
    Configuration is read from environment variables.
    """
    enabled = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    if not enabled:
        return

    # SMTP settings
    host = os.getenv("EMAIL_HOST", "localhost")
    port = int(os.getenv("EMAIL_PORT", "587"))
    user = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")
    from_addr = os.getenv("EMAIL_FROM", user)
    to_addr = os.getenv("EMAIL_TO")
    subject = os.getenv("EMAIL_SUBJECT", "Schema Drift Alert")

    if not user or not password or not to_addr:
        # Silently skip if not fully configured
        return

    # Build message
    body = "The following schema drift violations were detected:\n\n"
    body += "\n".join(f"• {v}" for v in violations)

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Send via SMTP (TLS)
    try:
        server = smtplib.SMTP(host, port, timeout=10)
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, to_addr.split(","), msg.as_string())
        server.quit()
    except Exception as e:
        # Fail silently – alert failure shouldn't break the gate
        print(f"[alerter] Failed to send email: {e}", flush=True)