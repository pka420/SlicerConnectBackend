import smtplib
from email.mime.text import MIMEText
import os

SMTP_SERVER = os.getenv("MAIL_SERVER")
SMTP_PORT = int(os.getenv("MAIL_PORT"))
EMAIL_USER = os.getenv("MAIL_USER")
EMAIL_PASS = os.getenv("MAIL_PASS")
FRONTEND_URL = os.getenv("FRONTEND_URL")

def send_verification_email(email, token):
    link = f"{FRONTEND_URL}/verify?token={token}"

    msg = MIMEText(f"Click to verify: {link}")
    msg["Subject"] = "Verify your email"
    msg["From"] = EMAIL_USER
    msg["To"] = email
    print(msg)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.sendmail(EMAIL_USER, email, msg.as_string())
