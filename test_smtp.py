import os
from dotenv import load_dotenv
import smtplib
from email.message import EmailMessage

load_dotenv()

host = os.getenv('EMAIL_HOST', 'mail.ethioace.com')
port = int(os.getenv('EMAIL_PORT', 465))
user = os.getenv('EMAIL_HOST_USER', 'loonkoo@ethioace.com')
password = os.getenv('EMAIL_HOST_PASSWORD', '')

print(f"Connecting to {host}:{port} with user {user} and password {password}")
try:
    if port == 465:
        server = smtplib.SMTP_SSL(host, port)
    else:
        server = smtplib.SMTP(host, port)
        server.starttls()
    server.login(user, password)
    print("SMTP login successful!")
    server.quit()
except Exception as e:
    print(f"SMTP failed: {e}")
