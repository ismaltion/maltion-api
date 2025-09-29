from dotenv import load_dotenv
from models import WrongDatabase
from contextlib import asynccontextmanager
import aiomysql
import os

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_MAIN_NAME = os.getenv("DB_MAIN_NAME")
DB_MNETWORK_NAME = os.getenv("DB_MNETWORK_NAME")
DB_MCLIENT_NAME = os.getenv("DB_MCLIENT_NAME")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


async def _connect_to_db(database: str):
    if database == "main":
        db_name = DB_MAIN_NAME
    elif database == "mnetwork":
        db_name = DB_MNETWORK_NAME
    elif database == "mclient":
        db_name = DB_MCLIENT_NAME
    else:
        raise WrongDatabase

    return await aiomysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        db=db_name,
    )


@asynccontextmanager
async def get_connection(database: str = "main"):
    conn = await _connect_to_db(database)
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def get_dict_connection(database: str = "main"):
    conn = await _connect_to_db(database)

    class DictConnectionWrapper:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, item):
            return getattr(self._conn, item)

        def cursor(self, *args, **kwargs):
            return self._conn.cursor(aiomysql.DictCursor, *args, **kwargs)

    wrapped = DictConnectionWrapper(conn)
    try:
        yield wrapped
    finally:
        conn.close()


def get_google_api_key():
    return GOOGLE_API_KEY
