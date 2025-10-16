from db import get_connection, get_dict_connection
from datetime import datetime, timedelta
from fastapi import HTTPException
from fastapi_mail import FastMail, MessageSchema
from config import EMAIL_CONFIG
from jinja2 import Environment, FileSystemLoader
from auth import hash_ip
import json, secrets, re

async def get_user_information(user_id, conn=None):
    if conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT username, email, displayName, birthday, createdOn, trust, banned, biography, 
                       loginAttempts, lastInteraction, country, friends, premium
                FROM users WHERE id = %s
            """, (user_id,))
            row = await cursor.fetchone()
    else:
        async with get_dict_connection("main") as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    SELECT username, email, displayName, birthday, createdOn, trust, banned, biography, 
                           loginAttempts, lastInteraction, country, friends, premium
                    FROM users WHERE id = %s
                """, (user_id,))
                row = await cursor.fetchone()

    if not row:
        return None

    user_info = row
    user_info["friends"] = user_info["friends"].split(",") if user_info["friends"] else []
    return user_info


async def get_user_information_by_username(username, conn=None):
    if conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT id, username, email, displayName, birthday, createdOn, trust, banned, biography, 
                       loginAttempts, lastInteraction, country, friends, premium
                FROM users WHERE username = %s
            """, (username,))
            row = await cursor.fetchone()
    else:
        async with get_dict_connection("main") as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    SELECT id, username, email, displayName, birthday, createdOn, trust, banned, biography, 
                           loginAttempts, lastInteraction, country, friends, premium
                    FROM users WHERE username = %s
                """, (username,))
                row = await cursor.fetchone()

    if not row:
        return None

    user_info = row
    user_info["friends"] = user_info["friends"].split(",") if user_info["friends"] else []
    return user_info


async def get_email_users(email, conn=None):
    if conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
            row = await cursor.fetchone()
    else:
        async with get_dict_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
                row = await cursor.fetchone()
    if not row:
        return None
    
    return row


def is_email(string):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, string) is not None


async def send_notification(user_id, notification, conn=None):
    if conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO notifications (user_id, type, content, reference_id, reference_type) VALUES (%s, %s, %s, %s, %s)",
                (user_id, notification.get("type"), notification.get("content"),
                 notification.get("reference_id"), notification.get("reference_type"))
            )
            await conn.commit()
    else:
        async with get_connection("main") as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO notifications (user_id, type, content, reference_id, reference_type) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, notification.get("type"), notification.get("content"),
                     notification.get("reference_id"), notification.get("reference_type"))
                )
                await conn.commit()


def notification(type, content, reference_id, reference_type):
    return {"type": type, "content": content, "reference_id": reference_id, "reference_type": reference_type}


async def rate_limiter(user_id):
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT last_mnetwork_interaction FROM users WHERE id = %s", (user_id,))
            result = await cursor.fetchone()
            if not result:
                raise Exception(f"User not found: ID{user_id}")

            last_interaction = result["last_mnetwork_interaction"]
            utcnow = datetime.utcnow()

            if utcnow > last_interaction:
                later = utcnow + timedelta(seconds=10)
                await cursor.execute("UPDATE users SET last_mnetwork_interaction = %s WHERE id = %s", (later, user_id))
                await conn.commit()
                return True
            else:
                return False

async def rate_limiter_guest_ip(ip_address):
    hashed_ip = hash_ip(ip_address)
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id, last_activity FROM guests WHERE ip_address = %s", (hashed_ip,))
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=400, detail="Choose a guest nickname first (or log in).")

            user_id = result["id"]
            last_interaction = result["last_activity"]
            utcnow = datetime.utcnow()

            if utcnow > last_interaction:
                later = utcnow + timedelta(seconds=60)
                await cursor.execute("UPDATE guests SET last_activity = %s WHERE id = %s", (later, user_id))
                await conn.commit()
                return True
            else:
                return False

async def check_ban(user_id, module="main"):
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM bans WHERE user_id = %s AND module = %s", (user_id, module))
            result = await cursor.fetchone()
            if result:
                raise HTTPException(status_code=403, detail="You are banned.")


async def get_setting(user_id, setting, conn=None):
    if conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT setting_value FROM user_settings WHERE user_id = %s AND setting_key = %s", (user_id, setting))
            result = await cursor.fetchone()
    else:
        async with get_connection("main") as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT setting_value FROM user_settings WHERE user_id = %s AND setting_key = %s", (user_id, setting))
                result = await cursor.fetchone()

    return result[0] if result else None


async def set_setting(user_id, setting, value, conn=None, commit=True):
    if conn:
        async with conn.cursor() as cursor:
            if not value:
                await cursor.execute("DELETE FROM user_settings WHERE user_id = %s AND setting_key = %s", (user_id, setting))
            else:
                await cursor.execute("SELECT COUNT(*) FROM user_settings WHERE user_id = %s AND setting_key = %s", (user_id, setting))
                exists = await cursor.fetchone()[0] > 0
                if exists:
                    await cursor.execute("UPDATE user_settings SET setting_value = %s, last_updated = NOW() WHERE user_id = %s AND setting_key = %s", (value, user_id, setting))
                else:
                    await cursor.execute("INSERT INTO user_settings (user_id, setting_key, setting_value, last_updated) VALUES (%s, %s, %s, NOW())", (user_id, setting, value))
        if commit:
            await conn.commit()
    else:
        async with get_connection("main") as conn:
            async with conn.cursor() as cursor:
                if not value:
                    await cursor.execute("DELETE FROM user_settings WHERE user_id = %s AND setting_key = %s", (user_id, setting))
                else:
                    await cursor.execute("SELECT COUNT(*) FROM user_settings WHERE user_id = %s AND setting_key = %s", (user_id, setting))
                    exists = await cursor.fetchone()[0] > 0
                    if exists:
                        await cursor.execute("UPDATE user_settings SET setting_value = %s, last_updated = NOW() WHERE user_id = %s AND setting_key = %s", (value, user_id, setting))
                    else:
                        await cursor.execute("INSERT INTO user_settings (user_id, setting_key, setting_value, last_updated) VALUES (%s, %s, %s, NOW())", (user_id, setting, value))
            if commit:
                await conn.commit()


async def get_json_settings(type_, id_):
    async with get_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT extra_info FROM {type_} WHERE id = %s", (id_,))
            result = await cursor.fetchone()
            return json.loads(result[0]) if result else None


async def set_json_settings(type_, id_, new_value):
    async with get_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f"UPDATE extra_info SET {type_} = %s WHERE id = %s", (json.dumps(new_value), id_))
            await conn.commit()


async def add_badge(user_id, new_badge):
    existing_badges = await get_setting(user_id, "Badges")
    try:
        badges = json.loads(existing_badges) if existing_badges else []
    except json.JSONDecodeError:
        badges = []
    if new_badge not in badges:
        badges.append(new_badge)
    await set_setting(user_id, "Badges", json.dumps(badges))

env = Environment(loader=FileSystemLoader("templates"))

async def send_email(subject, recipients, template_name, context: dict):
    template = env.get_template(template_name)
    html_content = template.render(context)
    print("---------- EMAIL SENT ----------")
    print(f"Subject: {subject}")
    print(f"Recipients: {len(recipients)}")
    print(f"Subtype: {template_name}")
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=html_content,
        subtype="html"
    )

    fm = FastMail(EMAIL_CONFIG)
    await fm.send_message(message)


async def generate_verification_code(user_id: int, code_type):
    code = "".join(secrets.choice("0123456789") for _ in range(8))
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM verification_codes WHERE user_id = %s AND type = %s", (user_id, code_type))
            result = await cursor.fetchone()
            if result:
                last_code_time = result["timestamp"]
                if last_code_time + timedelta(minutes=1) > datetime.utcnow():
                    raise HTTPException(status_code=401, detail="Please wait 1 minute before requesting another code.")
            await cursor.execute("DELETE FROM verification_codes WHERE user_id = %s AND type = %s", (user_id, code_type))
            await cursor.execute("INSERT INTO verification_codes (user_id, code, type, attempts, timestamp) VALUES (%s, %s, %s, %s, %s)", (user_id, code, code_type, 3, datetime.utcnow()))
            await conn.commit()
    return code

async def validate_verification_code(user_id: int, code_type, code):
    async with get_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM verification_codes WHERE user_id = %s AND type = %s ORDER BY timestamp DESC LIMIT 1", (user_id, code_type))
            result = await cursor.fetchone()
            if result:
                code_id, user_id, correct_code, code_type, attempts, timestamp = result
                expiration = timestamp + timedelta(hours=1)

                if attempts > 0 and expiration > datetime.utcnow():
                    if code == correct_code:
                        print(f"{code} is equal to {correct_code}")
                        await cursor.execute("DELETE FROM verification_codes WHERE user_id = %s AND type = %s", (user_id, code_type))
                        await conn.commit()
                        return True
                    else:
                        await cursor.execute("UPDATE verification_codes set attempts = attempts - 1 WHERE user_id = %s AND type = %s", (user_id, code_type))
                        await conn.commit()
                        return False
                else:
                    await cursor.execute("DELETE FROM verification_codes WHERE user_id = %s AND type = %s", (user_id, code_type))
                    await conn.commit()
                    return False
            else:
                return False
            
async def get_guest_info(ip_address):
    hashed_ip = hash_ip(ip_address)
    async with get_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id, nickname FROM guests WHERE ip_address = %s", (hashed_ip,))
            result = await cursor.fetchone()
            if result:
                return result[0], result[1]
            else:
                return None
            
async def generate_unblock_email(username):
    user_info = await get_user_information_by_username(username)
    user_id = user_info["id"]
    user_email = user_info["email"]
    verification_code = await generate_verification_code(user_id, "unblock")
    await send_email(
            subject="Unlock your account",
            recipients=[user_email],
            template_name="acc_unblock.html",
            context={"name": user_info["displayName"], "code": verification_code}
        )

async def generate_recovery_email(username):
    user_info = await get_user_information_by_username(username)
    user_id = user_info["id"]
    user_email = user_info["email"]
    verification_code = await generate_verification_code(user_id, "recovery")

    print(f"Requested recovery email for {username} with email: {user_email}")

    await send_email(
            subject="Recover your account",
            recipients=[user_email],
            template_name="acc_recovery.html",
            context={"name": user_info["displayName"], "code": verification_code}
        )
