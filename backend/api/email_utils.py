import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "False").lower() == "true"

SMTP_SERVER = os.getenv("MAIL_SERVER")
SMTP_PORT = int(os.getenv("MAIL_PORT", 587))
EMAIL_USER = os.getenv("MAIL_USER")
EMAIL_PASS = os.getenv("MAIL_PASS")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def send_email(email: str, token: str, purpose: str = "verify"):
    """
    purpose:
    - 'verify' -> email verification
    - 'reset'  -> forgot password
    """

    if not EMAIL_ENABLED:
        print("Email disabled (dev mode)")
        print("Purpose:", purpose)
        print("Token:", token)
        return

    if purpose == "reset":
        link = f"{FRONTEND_URL}/reset-password?token={token}"
        subject = "Reset your password"
        body = f"Click the link below to reset your password:\n\n{link}"
    else:
        link = f"{FRONTEND_URL}/verify?token={token}"
        subject = "Verify your email"
        body = f"Click the link below to verify your email:\n\n{link}"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = email

    try:
        with smtplib.SMTP("mailserver", 25) as server:
            server.sendmail("noreply@slicerconnect.from-delhi.net", email, msg.as_string())
    except Exception as e:
        print("Email sending failed:", e)
