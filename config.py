from fastapi_mail import ConnectionConfig
from dotenv import load_dotenv
import os

load_dotenv()

UPLOAD_FOLDER = '../uploads/pfp'
IMAGE_UPLOAD_FOLDER = '../uploads/pictures'
MAX_FILE_SIZE = 50 * 1024  # 50 KB

ALLOWED_ORIGINS = [
    "https://www.maltion.com",
    "https://maltion.com",
    "https://mclient.maltion.com",
    "https://voxarc.maltion.com",
    "https://insidia.maltion.com",
    "https://network.maltion.com",
    "http://network.maltion.com",
    "https://rdmedics.maltion.com",
    "http://rdmedics.maltion.com",
    "https://cheatgpt.maltion.com",
    "http://cheatgpt.maltion.com",
    "https://cheat.maltion.com",
    "http://cheat.maltion.com",
    "https://accounts.maltion.com",
    "http://accounts.maltion.com",
]

EMAIL_CONFIG = ConnectionConfig(
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME"),
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD"),
    MAIL_FROM = os.environ.get("MAIL_USERNAME"),
    MAIL_PORT = os.environ.get("MAIL_PORT"),
    MAIL_SERVER = os.environ.get("MAIL_SERVER"),
    MAIL_STARTTLS = False,
    MAIL_SSL_TLS = True,
    USE_CREDENTIALS = True
)

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
