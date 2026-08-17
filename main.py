from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS

from routers import (
    user,
    websocket,
    stats,
    friends,
    mnetwork,
    rdmedics,
    cheatgpt,
    admin,
)

from db import (
    get_dict_connection,
    init_db_pools,
    close_db_pools,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from utils import send_daily_digest

from contextlib import asynccontextmanager

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


# --------------------------------------------------
# Rate limiter
# --------------------------------------------------

limiter = Limiter(key_func=get_remote_address)


# --------------------------------------------------
# Transfer users from mclient -> main
# --------------------------------------------------

async def transfer_mclient_users():
    async with get_dict_connection("mclient") as conn_src, \
               get_dict_connection("main") as conn_dest:

        async with conn_src.cursor() as cursor_src, \
                   conn_dest.cursor() as cursor_dest:

            await cursor_src.execute(
                """
                SELECT username, email, description
                FROM users
                """
            )

            batch_size = 100

            while True:
                rows = await cursor_src.fetchmany(batch_size)

                if not rows:
                    break

                for row in rows:
                    username = row["username"]

                    # Skip invalid usernames
                    if not username:
                        continue

                    if " " in username:
                        continue

                    if len(username) > 32:
                        continue

                    # Check whether username already exists
                    await cursor_dest.execute(
                        """
                        SELECT 1
                        FROM users
                        WHERE username = %s
                        LIMIT 1
                        """,
                        (username,),
                    )

                    existing_user = await cursor_dest.fetchone()

                    if existing_user:
                        continue

                    try:
                        await cursor_dest.execute(
                            """
                            INSERT INTO users (
                                username,
                                email,
                                biography,
                                mclient_reserved
                            )
                            VALUES (%s, %s, %s, 1)
                            """,
                            (
                                username,
                                row["email"],
                                row["description"],
                            ),
                        )

                    except Exception as e:
                        # Don't crash the whole server
                        # because of one bad user
                        print(
                            f"Could not transfer user "
                            f"{username}: {e}"
                        )

                        # Roll back failed SQL transaction
                        await conn_dest.rollback()

                        continue

                await conn_dest.commit()


# --------------------------------------------------
# App lifespan
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None

    try:
        # Start database pools
        await init_db_pools(app)

        # ------------------------------------------
        # Scheduler
        # ------------------------------------------

        scheduler = AsyncIOScheduler()

        scheduler.add_job(
            send_daily_digest,
            "cron",
            hour=18,
            minute=0,
            id="daily_digest",
            replace_existing=True,
        )

        scheduler.start()

        app.state.scheduler = scheduler

        # ------------------------------------------
        # Transfer mclient users
        # ------------------------------------------

        await transfer_mclient_users()

        print("Server started.")

        # Server runs here
        yield

    finally:

        # ------------------------------------------
        # Stop scheduler
        # ------------------------------------------

        if scheduler is not None:
            try:
                scheduler.shutdown(wait=False)
            except Exception as e:
                print(f"Scheduler shutdown error: {e}")

        # ------------------------------------------
        # Close DB pools
        # ------------------------------------------

        try:
            await close_db_pools(app)
        except Exception as e:
            print(f"Database shutdown error: {e}")

        print("Server stopped.")


# --------------------------------------------------
# FastAPI app
# --------------------------------------------------

app = FastAPI(
    lifespan=lifespan
)


# --------------------------------------------------
# SlowAPI
# --------------------------------------------------

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)

app.add_middleware(
    SlowAPIMiddleware
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Routers
# --------------------------------------------------

app.include_router(user.router)
app.include_router(websocket.router)
app.include_router(stats.router)
app.include_router(friends.router)
app.include_router(mnetwork.router)

# This was missing before
app.include_router(rdmedics.router)

app.include_router(cheatgpt.router)
app.include_router(admin.router)


# --------------------------------------------------
# Thread ID mapping
# --------------------------------------------------

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
    12: 17,

    # IDs 10, 11, and 13 intentionally ignored
}
