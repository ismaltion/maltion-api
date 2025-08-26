from db import get_connection

def get_user_information(user_id, conn=None):
    autoclose = False
    if not conn:
        conn = get_connection("main")
        autoclose = True
    with conn.cursor() as cursor:
        cursor.execute("""
        SELECT username, email, displayName, birthday, createdOn, trust, banned, biography, 
               loginAttempts, lastInteraction, country, friends
        FROM users WHERE id = %s
    """, (user_id,))
        row = cursor.fetchone()

    if not row:
        return None

    keys = ["username", "email", "displayName", "birthday", "createdOn", "trust", 
            "banned", "biography", "loginAttempts", "lastInteraction", "country", "friends"]
    user_info = dict(zip(keys, row))
    
    if user_info["friends"]:
        user_info["friends"] = user_info["friends"].split(",")
    else:
        user_info["friends"] = []
    if autoclose:
        conn.close()
    return user_info

def get_user_information_by_username(username, conn):
    with conn.cursor() as cursor:
        cursor.execute("""
        SELECT username, email, displayName, birthday, createdOn, trust, banned, biography, 
               loginAttempts, lastInteraction, country, friends
        FROM users WHERE username = %s
    """, (username,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        keys = ["username", "email", "displayName", "birthday", "createdOn", "trust", 
                "banned", "biography", "loginAttempts", "lastInteraction", "country", "friends"]
        user_info = dict(zip(keys, row))
    
        if user_info["friends"]:
            user_info["friends"] = user_info["friends"].split(",")
        else:
            user_info["friends"] = []

        return user_info
