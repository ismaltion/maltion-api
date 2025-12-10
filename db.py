from dotenv import load_dotenv
from models import WrongDatabase
from contextlib import asynccontextmanager
import aiomysql
import aiomysql.cursors
import os
from typing import Dict, Any, Optional

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_MAIN_NAME = os.getenv("DB_MAIN_NAME")
DB_MNETWORK_NAME = os.getenv("DB_MNETWORK_NAME")
DB_MCLIENT_NAME = os.getenv("DB_MCLIENT_NAME")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

db_pools: Dict[str, aiomysql.Pool] = {}

def _get_db_name_str(database: str) -> str:
    if database == "main":
        return DB_MAIN_NAME
    elif database == "mnetwork":
        return DB_MNETWORK_NAME
    elif database == "mclient":
        return DB_MCLIENT_NAME
    else:
        raise WrongDatabase

async def init_db_pools(app: Any):
    global db_pools
    
    databases = {
        "main": DB_MAIN_NAME,
        "mnetwork": DB_MNETWORK_NAME,
        "mclient": DB_MCLIENT_NAME,
    }
    
    print("Initializing database connection pools...")
    
    for db_alias, db_name in databases.items():
        try:
            pool = await aiomysql.create_pool(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                db=db_name,
                minsize=5,
                maxsize=20,
                autocommit=True,
                echo=False,
            )
            db_pools[db_alias] = pool
        except Exception as e:
            print(f"Error creating pool for {db_alias}: {e}")
            
async def close_db_pools(app: Any):
    global db_pools
    for pool in db_pools.values():
        pool.close()
        await pool.wait_closed()
    db_pools = {}

@asynccontextmanager
async def _get_pooled_connection(database: str, cursor_type: Optional[Any] = None):
    db_alias = database
    if db_alias not in db_pools:
        raise RuntimeError(f"Database pool for '{db_alias}' is not initialized.")
        
    pool = db_pools[db_alias]

    async with pool.acquire() as conn:
        
        class PooledConnectionWrapper:
            def __init__(self, conn, cursor_class):
                self._conn = conn
                self._cursor_class = cursor_class

            def __getattr__(self, item):
                return getattr(self._conn, item)

            def cursor(self, *args, **kwargs):
                if self._cursor_class is not None:
                    return self._conn.cursor(self._cursor_class, *args, **kwargs)
                if args:
                    return self._conn.cursor(*args, **kwargs)
                
                return self._conn.cursor(**kwargs)

        wrapped = PooledConnectionWrapper(conn, cursor_type)
        
        yield wrapped

@asynccontextmanager
async def get_connection(database: str = "main"):
    async with _get_pooled_connection(database) as conn:
        yield conn

@asynccontextmanager
async def get_dict_connection(database: str = "main"):
    async with _get_pooled_connection(database, cursor_type=aiomysql.DictCursor) as conn:
        yield conn

def get_google_api_key():
    return GOOGLE_API_KEY