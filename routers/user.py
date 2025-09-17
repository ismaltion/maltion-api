from fastapi import APIRouter, Body, Depends, HTTPException, Response, Cookie, UploadFile, File
from fastapi.responses import JSONResponse
from models import ChangeFieldRequest, ChangeDateRequest, ChangePasswordRequest, reportAbuse
from auth import get_current_user_id, hash_password, check_password, create_session, validate_session, remove_session, remove_session_by_user_id, check_mclient_password
from db import get_connection, get_dict_connection
from utils import get_user_information, send_notification
from typing import Optional, List
from datetime import date, datetime
from config import UPLOAD_FOLDER, MAX_FILE_SIZE
import os
import json
import re
import traceback

USERNAME_REGEX = r'^[a-zA-Z0-9_-]+$'
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

router = APIRouter()

@router.post("/register")
def register_user(
    username: str = Body(...),
    password: str = Body(...),
    email: str = Body(...),
    displayName: Optional[str] = Body(None),
    birthday: date = Body(...),
    biography: Optional[str] = Body("No biography added."),
    country: Optional[str] = Body("Antarctica")
    ):

    if not displayName:
        displayName = username

    # start of extensive checks
    if len(username) < 4 or len(username) > 20 or " " in username:
        raise HTTPException(status_code=400, detail="Username must be between 4 and 20 characters long, with no spaces.")
    if "'" in username or '"' in username or "`" in username or "´" in username or "," in username:
        raise HTTPException(status_code=400, detail="Invalid username: Please remove quotes or commas. Quotes could cause a lot of damage to your account.")
    if len(password) < 6 or len(password) > 64:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long with a limit of 64 characters.")
    if len(email) < 5 or len(email) > 320 or " " in email or not "@" in email or not "." in email:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    if len(displayName) < 4 or len(displayName) > 20:
        raise HTTPException(status_code=400, detail="Display name must be between 4 and 20 characters long.")
    if len(country) < 3 or len(country) > 32:
        raise HTTPException(status_code=400, detail="Country must be between 3 and 32 characters long.")
    # end of extensive checks    

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Username already taken")

    hashed = hash_password(password)
    cursor.execute("INSERT INTO users (username, password, email, displayName, birthday, createdOn, biography, loginAttempts, lastInteraction, country) VALUES (%s, %s, %s, %s, %s, NOW(), %s, 0, NOW(), %s)", (username, hashed, email, displayName, birthday, biography, country))
    conn.commit()
    cursor.close()
    conn.close()

    return {"message": "User registered"}

@router.post("/mclient-migration")
def mclient_migration(
    username: str = Body(...),
    password: str = Body(...),
    displayName: Optional[str] = Body(None),
    birthday: date = Body(...),
    country: Optional[str] = Body("Antarctica")
    ):

    email = None
    biography = None
    new_account_id = None
    issue_flag = False

    # start of extensive checks
    if len(username) < 32 or len(username) > 60:
        return JSONResponse(status_code=400, content={"detail": "Username must be between 3 and 60 characters long."})
    if not re.match(USERNAME_REGEX, username, re.IGNORECASE):
        return JSONResponse(status_code=400, content={"detail": "Invalid username. Only letters, numbers and hyphens are allowed."})
    if len(password) < 6 or len(password) > 64:
        return JSONResponse(status_code=400, content={"detail": "Password must be between 6 and 64 characters long."})
    if len(displayName) < 4 or len(displayName) > 20:
        displayName = username
    if len(country) < 3 or len(country) > 32:
        return JSONResponse(status_code=400, content={"detail": "Country must be between 3 and 32 characters long."})
    # end of extensive checks    

    # start of getting information from mclient database
    with get_dict_connection("mclient") as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                result = cursor.fetchone()
                if not result:
                    return JSONResponse(status_code=404, content={"detail": "MClient account not found."})
                
                login_attempts = result["loginattempts"]
                if login_attempts > 5:
                    return JSONResponse(status_code=403, content={"detail": "This account has been temporally disabled for multiple failed attempts."})

                mclient_hash = result["password"]
                if not check_mclient_password(password, mclient_hash):
                    cursor.execute("UPDATE users SET loginattempts = %s WHERE username = %s", (login_attempts + 1, username))
                    conn.commit()
                    return JSONResponse(status_code=403, content={"detail": "Incorrect password."})

                email = result["email"]
                biography = result["description"]
                migrated = result["migrated"]

                if biography == "":
                    biography = "No biography added."

                if not re.match(EMAIL_REGEX, email, re.IGNORECASE):
                    email = "null@null"
                    issue_flag = True
            except Exception as e:
                return JSONResponse(status_code=500, content={"detail": f"Internal server error. Details: Failed on step 1/4 (Checking information): {e}"})

    # end of getting information from mclient database

    with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT id, mclient_reserved FROM users WHERE username = %s", (username,))
                result = cursor.fetchone()
                hashed = hash_password(password)
                if result:
                    mclient_reserved = result["mclient_reserved"]
                    new_account_id = result["id"]
                    if mclient_reserved == 1:
                        cursor.execute("UPDATE users SET password = %s, email = %s, displayName = %s, birthday = %s, createdOn = NOW(), biography = %s, loginAttempts = 0, lastInteraction = NOW(), country = %s WHERE username = %s", (hashed, email, displayName, birthday, biography, country, username))
                    else:
                        return JSONResponse(status_code=401, content={"detail": "There's an already registered account with your username which isn't yours. You will need to change your username to migrate your account, which requires the assistance of support."})
                else:
                    cursor.execute("INSERT INTO users (username, password, email, displayName, birthday, createdOn, biography, loginAttempts, lastInteraction, country) VALUES (%s, %s, %s, %s, %s, NOW(), %s, 0, NOW(), %s)", (username, hashed, email, displayName, birthday, biography, country))
                    new_account_id = cursor.lastrowid

                conn.commit()
            except Exception as e:
                conn.rollback()
                return JSONResponse(status_code=500, content={"detail": f"Internal server error. Details: Failed on step 2/4 (Transferring account): {e} {traceback.format_exc()}"})
    
    if new_account_id:
         with get_connection("mnetwork") as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute("UPDATE posts SET author_id = %s WHERE author_name = %s", (new_account_id, username))
                    cursor.execute("UPDATE threads SET author_id = %s WHERE author_name = %s", (new_account_id, username))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    return JSONResponse(status_code=500, content={"detail": f"Internal server error. Details: Failed on step 3/4 (Migrating MNetwork ownerships - Your account was migrated, though, but you can try to migrate it again to solve this issue.): {e} {traceback.format_exc()}"})

    with get_connection("mclient") as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("UNLOCK TABLES")
                cursor.execute("UPDATE users SET migrated = 1 WHERE username = %s", (username,))
                conn.commit()
            except Exception as e:
                conn.rollback()
                return JSONResponse(status_code=500, content={"detail": f"Internal server error. Details: {e}"})
    
    return {"message": "User migrated successfully."}

@router.post("/login")
def route_login_user(username: str = Body(...), password: str = Body(...)):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, password, mclient_reserved FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if not user:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            user_id, hashed, mclient_reserved = user
            #if mclient_reserved == 1:
                #raise HTTPException(status_code=401, detail="This account is an MClient account. Please migrate it first through mclient.maltion.com to use it here.")
            
            if not check_password(password, hashed):
                raise HTTPException(status_code=401, detail="Invalid credentials")

            session_token, expires_at = create_session(conn, user_id)

    response = Response(content='{"message": "Login successful"}', media_type="application/json")
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=7*24*3600
    )
    return response

@router.post("/logoff")
def route_logoff_user(session_token: str = Cookie(None)):
    if not session_token:
        raise HTTPException(status_code=400, detail="Session token missing")

    with get_connection() as conn:
        remove_session(conn, session_token)

    response = Response(content='{"message": "Logoff successful"}', media_type="application/json")
    response.delete_cookie("session_token")
    return response

@router.get("/get-user-info")
def route_getUserInfo(user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    user_info = get_user_information(user_id, conn)
    conn.close()

    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    return {"userinfo": user_info}

@router.get("/get-username")
def route_getUsername(user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    user_info = get_user_information(user_id, conn)
    conn.close()

    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    return {"username": user_info["username"], "trust": user_info["trust"]}

@router.get("/check-login")
def route_check_login(user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)

    if not user_info:
        return "false"

    return "true"

@router.get("/get-settings")
def route_getSettings(user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")

        with conn.cursor() as cursor:
            cursor.execute('''SELECT settings FROM users WHERE username = %s''', (user_info["username"],))
            result = cursor.fetchone()

            if result:
                return json.loads(result[0])
            else:
                raise HTTPException(status_code=404, detail="Settings not found")

@router.post("/update-settings")
def route_updateSettings(user_id: int = Depends(get_current_user_id), settings: dict = Body(...)): # settings are supposed to be a json object
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        settings_json = json.dumps(settings)
        with conn.cursor() as cursor:
            cursor.execute('''UPDATE users SET settings = %s WHERE username = %s''', (settings_json, user_info["username"]))
            conn.commit()
    
    return Response(status_code=200)

@router.post("/change-username")
def route_changeUsername(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newUsername = str(newValue)
        if len(newUsername) < 4 or len(newUsername) > 20 or " " in newUsername:
            raise HTTPException(status_code=400, detail="Invalid username. Must be between 4 and 20 characters long with no spaces")
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username = %s", (newUsername,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Username already taken")
            cursor.execute('''UPDATE users SET username = %s WHERE id = %s''', (newUsername, user_id))
            conn.commit()

        oldFilename = "../uploads/pfp/" + user_info["username"] + ".jpg"
        newFilename = "../uploads/pfp/" + newUsername + ".jpg"
        if os.path.exists(oldFilename):
            os.rename(oldFilename, newFilename)

    return Response(status_code=200)

@router.post("/change-nickname")
def route_changeNickname(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newNickname = str(newValue)
        if len(newNickname) < 4 or len(newNickname) > 20:
            raise HTTPException(status_code=400, detail="Invalid display name. Must be between 4 and 20 characters long.")
        
        with conn.cursor() as cursor:
            cursor.execute('''UPDATE users SET displayName = %s WHERE id = %s''', (newNickname, user_id))
            conn.commit()
    
    return Response(status_code=200)

@router.post("/change-country")
def route_changeCountry(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newCountry = str(newValue)
        if len(newCountry) < 3 or len(newCountry) > 32:
            raise HTTPException(status_code=400, detail="Invalid country. Must be between 3 and 32 characters.")
        
        with conn.cursor() as cursor:
            cursor.execute('''UPDATE users SET country = %s WHERE id = %s''', (newCountry, user_id))
            conn.commit()
    
    return Response(status_code=200)

@router.post("/change-birthday")
def route_changeBirthday(payload: ChangeDateRequest, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newBirthday = newValue
        
        with conn.cursor() as cursor:
            cursor.execute('''UPDATE users SET birthday = %s WHERE id = %s''', (newBirthday, user_id))
            conn.commit()
    
    return Response(status_code=200)

@router.post("/change-email")
def route_changeEmail(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newEmail = str(newValue)
        if len(newEmail) < 5 or len(newEmail) > 320 or " " in newEmail or not "@" in newEmail or not "." in newEmail:
            raise HTTPException(status_code=400, detail="Invalid email address.")
        
        with conn.cursor() as cursor:
            cursor.execute('''UPDATE users SET email = %s WHERE id = %s''', (newValue, user_id))
            conn.commit()
    
    return Response(status_code=200)

@router.post("/change-biography")
def route_changeBiography(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newBiography = str(newValue)
        if len(newBiography) < 5 or len(newBiography) > 1000:
            raise HTTPException(status_code=400, detail="Too long biography")
        
        with conn.cursor() as cursor:
            cursor.execute('''UPDATE users SET biography = %s WHERE id = %s''', (newValue, user_id))
            conn.commit()
    
    return Response(status_code=200)

@router.post("/change-password")
def route_changePassword(payload: ChangePasswordRequest, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            user_info = get_user_information(user_id, conn)
            oldValue = payload.oldValue
            newValue = payload.newValue
            if not user_info:
                raise HTTPException(status_code=404, detail="User not found - You need to login first.")

            oldPassword = str(oldValue)

            cursor.execute('''SELECT password FROM users WHERE id = %s''', (user_id,))
            result = cursor.fetchone()
            hashed = result[0]
            if not check_password(oldPassword, hashed):
                raise HTTPException(status_code=401, detail="Invalid credentials")

            newPassword = hash_password(newValue)
            if len(newPassword) < 6 or len(newPassword) > 64:
                raise HTTPException(status_code=400, detail="Invalid password. Must be at least 6 characters long.")
            
            cursor.execute('''UPDATE users SET password = %s WHERE id = %s''', (newPassword, user_id))
            conn.commit()
    return Response(status_code=200)

@router.post("/delete-account")
def route_deleteAccount(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            user_info = get_user_information(user_id, conn)
            currentPassword = payload.value
            if not user_info:
                raise HTTPException(status_code=404, detail="User not found - You need to login first.")

            password = str(currentPassword)

            cursor.execute('''SELECT password FROM users WHERE id = %s''', (user_id,))
            result = cursor.fetchone()
            hashed = result[0]
            if not check_password(password, hashed):
                raise HTTPException(status_code=401, detail="Invalid credentials")
            
            cursor.execute('''DELETE FROM users WHERE id = %s''', (user_id,))
            conn.commit()

        remove_session_by_user_id(conn, user_id)

    response = Response(content='{"message": "Account deletion successful"}', media_type="application/json")
    response.delete_cookie("session_token")
    return Response(status_code=200)

@router.post("/upload-pfp")
async def route_upload_image(user_id: int = Depends(get_current_user_id), file: UploadFile = File(...)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max size is 30 KB.")
    
    file_location = os.path.join(UPLOAD_FOLDER, user_info["username"] + ".jpg")
    with open(file_location, "wb") as buffer:
        buffer.write(contents)

    return { "filename": file.filename, "message": "Image uploaded successfully" }

@router.post("/report")
def report_abuse(payload: reportAbuse, user_id = Depends(get_current_user_id)):
    module = payload.module
    reason = payload.reason
    content_type = payload.type
    content_id = payload.id
    details = payload.detail
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    with get_connection("main") as conn:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO reports (parent_id, parent_module, parent_type, author_id, type, content) VALUES (%s, %s, %s, %s, %s, %s)", (content_id, module, content_type, user_id, reason, details))
            conn.commit()
            return { "message": "Success" }
        
@router.get("/notifications")
def get_notifications(user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY timestamp DESC LIMIT 50", (user_id,))
            result = cursor.fetchall()

            cursor.execute("UPDATE notifications SET is_read = 1 WHERE user_id = %s", (user_id,))
            conn.commit()

            return { "notifications": result }
        
@router.get("/notifications-preview")
def get_notifications_preview(user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id = %s AND is_read = 0", (user_id,))
            result = cursor.fetchone()
            
            notification_count = result["cnt"]

            return { "notifications": notification_count }
        
@router.post("/accept-admin")
def accept_admin(user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET trust = 10 WHERE id = %s AND trust = 9", (user_id,))

            if cursor.rowcount == 0:
                raise HTTPException(status_code=403, detail="You are not invited to become an administrator.")

            conn.commit()

            return { "message": "You are now an administrator" }