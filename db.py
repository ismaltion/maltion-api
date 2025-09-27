from dotenv import load_dotenv
from models import WrongDatabase
from contextlib import asynccontextmanager
import asyncmy
import os

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD") # did you really think i was going to place the password in the code lmao
DB_MAIN_NAME = os.getenv("DB_MAIN_NAME")
DB_MNETWORK_NAME = os.getenv("DB_MNETWORK_NAME")
DB_MCLIENT_NAME = os.getenv("DB_MCLIENT_NAME")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


@asynccontextmanager
async def get_connection(database: str = "main"):
    if database == "main":
        conn = await asyncmy.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MAIN_NAME,
            cursorclass=asyncmy.cursors.Cursor,
        )
    elif database == "mnetwork":
        conn = await asyncmy.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MNETWORK_NAME,
            cursorclass=asyncmy.cursors.Cursor,
        )
    elif database == "mclient":
        conn = await asyncmy.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MCLIENT_NAME,
            cursorclass=asyncmy.cursors.Cursor,
        )
    else:
        raise WrongDatabase
    try:
        yield conn
    finally:
        await conn.ensure_closed()


@asynccontextmanager
async def get_dict_connection(database: str = "main"):
    if database == "main":
        conn = await asyncmy.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MAIN_NAME,
            cursorclass=asyncmy.cursors.DictCursor,
        )
    elif database == "mnetwork":
        conn = await asyncmy.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MNETWORK_NAME,
            cursorclass=asyncmy.cursors.DictCursor,
        )
    elif database == "mclient":
        conn = await asyncmy.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_MCLIENT_NAME,
            cursorclass=asyncmy.cursors.DictCursor,
        )
    else:
        raise WrongDatabase

    try:
        yield conn
    finally:
        await conn.ensure_closed()


def get_google_api_key():
    return GOOGLE_API_KEY