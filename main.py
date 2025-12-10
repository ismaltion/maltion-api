from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
from config import ALLOWED_ORIGINS
from routers import user, websocket, stats, friends, mnetwork, rdmedics, cheatgpt, admin
from db import get_dict_connection, init_db_pools, close_db_pools 
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from utils import send_mnetwork_digest, send_daily_digest
from contextlib import asynccontextmanager
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import asyncio, json

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pools(app) 
    yield
    await close_db_pools(app)

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SlowAPIMiddleware)

app.include_router(user.router)
app.include_router(websocket.router)
app.include_router(stats.router)
app.include_router(friends.router)
app.include_router(mnetwork.router)
app.include_router(cheatgpt.router)
app.include_router(admin.router)

THREAD_ID_MAP = {
    1: 6,
    2: 7,
    3: 8,
    4: 9,
    5: 10,
    6: 11,
    7: 12,
    8: 13,
    9: 14,
    12: 17
    # IDs 10, 11, 13 are ignored automatically
}

@app.on_event("startup")
async def startup_tasks():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: asyncio.create_task(send_daily_digest()), "cron", hour=18, minute=0)
    scheduler.start()

    # Automatically transfer users from mclient database
    async with get_dict_connection("mclient") as conn_src, \
         get_dict_connection("main") as conn_dest:
        
        async with conn_src.cursor() as cursor_src, conn_dest.cursor() as cursor_dest:
            
            await cursor_src.execute("SELECT username, email, description FROM users")
            
            batch_size = 100
            while True:
                rows = await cursor_src.fetchmany(batch_size)
                if not rows:
                    break
                
                for row in rows:
                    username = row['username']
                    
                    if " " in username or len(username) > 32:
                        continue
                    
                    await cursor_dest.execute("SELECT 1 FROM users WHERE username=%s", (username,))
                    if await cursor_dest.fetchone():
                        continue
                    
                    await cursor_dest.execute(
                        """
                        INSERT INTO users (username, email, biography, mclient_reserved)
                        VALUES (%s, %s, %s, 1)
                        """,
                        (username, row['email'], row['description'])
                    )
                await conn_dest.commit()

print("Server started.")
