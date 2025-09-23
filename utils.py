from db import get_connection, get_dict_connection
from datetime import datetime, timedelta
from fastapi import HTTPException
import pymysql
import json

def get_user_information(user_id, conn=None):
    autoclose = False
    if not conn:
        conn = get_dict_connection("main")
        autoclose = True
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
        SELECT username, email, displayName, birthday, createdOn, trust, banned, biography, 
               loginAttempts, lastInteraction, country, friends, premium
        FROM users WHERE id = %s
    """, (user_id,))
        row = cursor.fetchone()

    if not row:
        return None

    user_info = row
    
    if user_info["friends"]:
        user_info["friends"] = user_info["friends"].split(",")
    else:
        user_info["friends"] = []
    if autoclose:
        conn.close()
    return user_info

def get_user_information_by_username(username, conn=None):
    autoclose = False
    if not conn:
        conn = get_dict_connection("main")
        autoclose = True
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
        SELECT id, username, email, displayName, birthday, createdOn, trust, banned, biography, 
               loginAttempts, lastInteraction, country, friends, premium
        FROM users WHERE username = %s
    """, (username,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        user_info = row
    
        if user_info["friends"]:
            user_info["friends"] = user_info["friends"].split(",")
        else:
            user_info["friends"] = []
        if autoclose:
            conn.close()
        return user_info
    
def send_notification(user_id, notification, conn = None):
    autoclose = False
    if not conn:
        conn = get_connection("main")
        autoclose = True
    
    with conn.cursor() as cursor:
        cursor.execute("INSERT INTO notifications (user_id, type, content, reference_id, reference_type) VALUES (%s, %s, %s, %s, %s)", (user_id, notification.get("type"), notification.get("content"), notification.get("reference_id"), notification.get("reference_type")))
        conn.commit()

    if autoclose:
        conn.close()

def notification(type, content, reference_id, reference_type):
    return { "type": type, "content": content, "reference_id": reference_id, "reference_type": reference_type}

def rate_limiter(user_id):
    with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT last_mnetwork_interaction FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()

            if not result:
                raise Exception(f"User not found: ID{user_id}")
            
            last_interaction = result["last_mnetwork_interaction"]

            utcnow = datetime.utcnow()

            if utcnow > last_interaction:
                later = utcnow + timedelta(seconds=10)
                cursor.execute("UPDATE users SET last_mnetwork_interaction = %s WHERE id = %s", (later, user_id,))
                conn.commit()
                return True
            else:
                return False
            
def check_ban(user_id, module="main"):
    with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM bans WHERE user_id = %s AND module = %s", (user_id, module))
            result = cursor.fetchone()

            if result:
                raise HTTPException(status_code=403, detail="You are banned.")
            
def get_setting(user_id, setting, conn=None):
    autoclose = False
    if not conn:
        autoclose = True
        conn = get_connection("main")

    try:
        result = None
        with conn.cursor() as cursor:
            cursor.execute("SELECT setting_value FROM user_settings WHERE user_id = %s AND setting_key = %s", (user_id, setting))
            result = cursor.fetchone()

        if result:
            return result[0]
        else:
            return None
    finally:
        if autoclose:
            conn.close()
    
            
def set_setting(user_id, setting, value, conn=None, commit=True):
    autoclose = False
    if not conn:
        autoclose = True
        conn = get_connection("main")

    try:
        with conn.cursor() as cursor:
            if value is None or value == "":
                cursor.execute(
                    "DELETE FROM user_settings WHERE user_id = %s AND setting_key = %s",
                    (user_id, setting),
                )
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM user_settings WHERE user_id = %s AND setting_key = %s",
                    (user_id, setting),
                )
                exists = cursor.fetchone()[0] > 0

                if exists:
                    cursor.execute(
                        "UPDATE user_settings SET setting_value = %s, last_updated = NOW() WHERE user_id = %s AND setting_key = %s",
                        (value, user_id, setting),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO user_settings (user_id, setting_key, setting_value, last_updated) VALUES (%s, %s, %s, NOW())",
                        (user_id, setting, value),
                    )

        if commit:
            conn.commit()
    finally:
        if autoclose:
            conn.close()


def get_json_settings(type, id):
    with get_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT extra_info FROM %s WHERE id = %s", (type, id))
            result = cursor.fetchone()

            return json.loads(result[0]) if result else None

def set_json_settings(type, id, new_value):
    with get_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE extra_info SET %s = %s WHERE id = %s", (type, json.dumps(new_value), id))
            conn.commit()