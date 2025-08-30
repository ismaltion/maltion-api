import os

UPLOAD_FOLDER = '../uploads/pfp'
MAX_FILE_SIZE = 30 * 1024  # 30 KB

ALLOWED_ORIGINS = [
    "https://www.maltion.com",
    "https://maltion.com",
    "https://mclient.maltion.com",
    "https://voxarc.maltion.com",
    "https://insidia.maltion.com",
    "https://network.maltion.com",
    "http://network.maltion.com",
    "https://rdmedics.maltion.com",
    "http://rdmedics.maltion.com"
]

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
