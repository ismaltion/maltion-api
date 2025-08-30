from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import ALLOWED_ORIGINS
from routers import user, websocket, stats, friends, mnetwork, rdmedics
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user.router)
app.include_router(websocket.router)
app.include_router(stats.router)
app.include_router(friends.router)
app.include_router(mnetwork.router)

@app.on_event("startup")
async def start_bot():
    asyncio.create_task(rdmedics.run_bot())

print("Server started.")
