import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email_alert(violations) -> bool:
    """
    Send an email alert with schema drift violations.
    Configuration is read from environment variables.
    
    Returns True if email was sent successfully, False otherwise.
    """
    enabled = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    if not enabled:
        return False

    # SMTP settings
    host = os.getenv("EMAIL_HOST", "localhost")
    port = int(os.getenv("EMAIL_PORT", "587"))
    user = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")
    from_addr = os.getenv("EMAIL_FROM", user)
    to_addr = os.getenv("EMAIL_TO")
    subject = os.getenv("EMAIL_SUBJECT", "Schema Drift Alert")

    if not user or not password or not to_addr:
        # --- Fix #11: Print to stderr, not stdout ---
        print("[alerter] Email not fully configured (missing EMAIL_USER, EMAIL_PASSWORD, or EMAIL_TO). Skipping.", file=sys.stderr)
        return False

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
        return True
    except Exception as e:
        # --- Fix #11: Print to stderr instead of stdout ---
        print(f"[alerter] Failed to send email: {e}", file=sys.stderr, flush=True)
        return False