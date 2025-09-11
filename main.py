from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import ALLOWED_ORIGINS
from routers import user, websocket, stats, friends, mnetwork, rdmedics, cheatgpt
from db import get_dict_connection
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
app.include_router(cheatgpt.router)

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
def transfer_users():
    with get_dict_connection("mclient") as conn_src, \
         get_dict_connection("main") as conn_dest:
        
        with conn_src.cursor() as cursor_src, conn_dest.cursor() as cursor_dest:
            
            cursor_src.execute("SELECT username, email, description FROM users")
            
            batch_size = 100
            while True:
                rows = cursor_src.fetchmany(batch_size)
                if not rows:
                    break
                
                for row in rows:
                    username = row['username']
                    
                    if " " in username or len(username) > 32:
                        continue
                    
                    cursor_dest.execute("SELECT 1 FROM users WHERE username=%s", (username,))
                    if cursor_dest.fetchone():
                        continue
                    
                    cursor_dest.execute(
                        """
                        INSERT INTO users (username, email, biography, mclient_reserved)
                        VALUES (%s, %s, %s, 1)
                        """,
                        (username, row['email'], row['description'])
                    )
                conn_dest.commit()

    

print("Server started.")
