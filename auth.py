from fastapi import Cookie, HTTPException, Depends
from db import get_connection
from datetime import datetime, timedelta
from dotenv import load_dotenv
import bcrypt
import secrets
import hashlib
import os

load_dotenv()

MCLIENT_SALT = os.getenv("MCLIENT_SALT")

# -------------------
# Session things
# -------------------

def get_current_session(session_token: str = Cookie(None)):
    if not session_token:
        raise HTTPException(status_code=401, detail="No session token")
    return session_token

async def get_current_user_id(session_token: str = Cookie(None)):
    try:
        if not session_token:
            return None
    
        async with get_connection() as conn:
            user_id = await validate_session(conn, session_token)

        if not user_id:
            return None
    
        return user_id
    except Exception as e:
        print(e)
        return None

# -------------------
# Passwords
# -------------------

ROUNDS = 13

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=ROUNDS)).decode()

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# -------------------
# Session management
# -------------------

async def create_session(conn, user_id, expiry_days=7):
    session_token = secrets.token_hex(32)
    expires_at = datetime.utcnow() + timedelta(days=expiry_days)

    async with conn.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO sessions (userId, sessionToken, createdAt, expiresAt)
            VALUES (%s, %s, NOW(), %s)
            """,
            (user_id, session_token, expires_at)
        )
        await conn.commit()

    return session_token, expires_at

async def validate_session(conn, session_token):
    async with conn.cursor() as cursor:
        await cursor.execute(
            '''
            SELECT userId, expiresAt FROM sessions
            WHERE sessionToken = %s
            ''',
            (session_token,)
        )
        session = await cursor.fetchone()

        if not session:
            return None

        user_id, expires_at = session
        if expires_at < datetime.utcnow():
            await cursor.execute('''DELETE FROM sessions WHERE sessionToken = %s''', (session_token,))
            await conn.commit()
            return None

    return user_id

async def remove_session(conn, session_token):
    async with conn.cursor() as cursor:
        await cursor.execute(
            "DELETE FROM sessions WHERE sessionToken = %s",
            (session_token,)
        )
        await conn.commit()

async def remove_session_by_user_id(conn, user_id):
    async with conn.cursor() as cursor:
        await cursor.execute(
            "DELETE FROM sessions WHERE userId = %s",
            (user_id,)
        )
        await conn.commit()

async def check_mclient_password(password, hash):
    saltedpassword = f"{MCLIENT_SALT}{password}"
    new_hash = hashlib.sha256(saltedpassword.encode()).hexdigest()

    return new_hash == hash

def hash_ip(ip_addr):
    return hashlib.sha512(ip_addr.encode()).hexdigest()