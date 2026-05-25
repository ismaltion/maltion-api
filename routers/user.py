from fastapi import APIRouter, Body, Depends, HTTPException, Response, Cookie, UploadFile, File, Request, Form
from fastapi.responses import JSONResponse
from models import ChangeFieldRequest, ChangeDateRequest, ChangePasswordRequest, reportAbuse, createGuestProfile, recoverAcc, verifyRecoverAcc, verifyUnlockAcc
from auth import get_current_user_id, hash_password, check_password, create_session, validate_session, hash_ip, remove_session, remove_session_by_user_id, check_mclient_password
from db import get_connection, get_dict_connection
from utils import get_user_information, send_notification, send_email, generate_verification_code, validate_verification_code, generate_unblock_email, generate_recovery_email, get_email_users, is_email, get_user_information_by_username, generate_verification_email
from typing import Optional, List
from datetime import date, datetime, timedelta
from config import UPLOAD_FOLDER, MAX_FILE_SIZE
from ratelimit import limiter
import os, json, re, traceback, math, asyncio, random

USERNAME_REGEX = r'^[a-zA-Z0-9_-]+$'
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

router = APIRouter()

@router.post("/ping")
async def router_ping():
    return {"message": "Maltion API is working correctly."}

@router.post("/register")
@limiter.limit("5/minute")
async def register_user(
    request: Request,
    username: str = Body(...),
    password: str = Body(...),
    email: str = Body(...),
    displayName: Optional[str] = Body(None),
    birthday: date = Body(...),
    biography: Optional[str] = Body("No biography added."),
    country: Optional[str] = Body("Antarctica"),
    invited_by: Optional[str] = Body("System"),
):
    client_ip = (
    request.headers.get("x-real-ip")
    or request.headers.get("X-Forwarded-For")
    or request.client.host
    )

    if not displayName:
        displayName = username

    now = datetime.utcnow()

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
    if len(country) > 32:
        raise HTTPException(status_code=400, detail="Country must be between 3 and 32 characters long.")
    if len(invited_by) > 20:
        invited_by = "System"
    # end of extensive checks    

    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            result = await cursor.fetchone()
            if result:
                raise HTTPException(status_code=400, detail="Username already taken")

            hashed = hash_password(password)
            stored_ip = hash_ip(client_ip)

            await cursor.execute("INSERT INTO users (username, password, email, displayName, birthday, createdOn, biography, loginAttempts, lastInteraction, last_mnetwork_interaction, country, IP_address, invited_by, unlock_time) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s)", (username, hashed, email, displayName, birthday, now, biography, now, now, country, stored_ip, invited_by, now))
            await conn.commit()

            await generate_verification_email(username)

    return {"message": "User registered"}

@router.post("/create-guest-profile")
async def create_guest_profile(request: Request, payload: createGuestProfile):
    nickname = payload.nickname
    client_ip = (request.headers.get("x-real-ip") or request.headers.get("X-Forwarded-For") or request.client.host)

    if len(nickname) < 4 or len(nickname) > 20 or " " in nickname:
        raise HTTPException(status_code=400, detail="Nickname must be between 4 and 20 characters long, with no spaces.")
    
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            hashed_ip = hash_ip(client_ip)
            await cursor.execute("SELECT id FROM guests WHERE ip_address = %s", (hashed_ip,))
            result = await cursor.fetchone()
            if result:
                raise HTTPException(status_code=400, detail="You have already created a guest profile.")

            dt = datetime(year=2000, month=1, day=1, hour=0, minute=0, second=0)
            now = datetime.utcnow()
            await cursor.execute("INSERT INTO guests (nickname, ip_address, timestamp, last_activity) VALUES (%s, %s, %s, %s)", (nickname, hashed_ip, now, dt))
            await conn.commit()

@router.post("/mclient-migration")
async def mclient_migration(
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
    if len(username) < 3 or len(username) > 60:
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
    async with get_dict_connection("mclient") as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                result = await cursor.fetchone()
                if not result:
                    return JSONResponse(status_code=404, content={"detail": "MClient account not found."})
                
                login_attempts = result["loginattempts"]
                if login_attempts > 5:
                    return JSONResponse(status_code=403, content={"detail": "This account has been temporarily disabled for multiple failed attempts."})

                mclient_hash = result["password"]
                if not check_mclient_password(password, mclient_hash):
                    await cursor.execute("UPDATE users SET loginattempts = %s WHERE username = %s", (login_attempts + 1, username))
                    await conn.commit()
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

    async with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            try:
                await cursor.execute("SELECT id, mclient_reserved FROM users WHERE username = %s", (username,))
                result = await cursor.fetchone()
                hashed = hash_password(password)
                if result:
                    mclient_reserved = result["mclient_reserved"]
                    new_account_id = result["id"]
                    if mclient_reserved == 1:
                        await cursor.execute("UPDATE users SET password = %s, email = %s, displayName = %s, birthday = %s, createdOn = NOW(), biography = %s, loginAttempts = 0, lastInteraction = NOW(), country = %s WHERE username = %s", (hashed, email, displayName, birthday, biography, country, username))
                    else:
                        return JSONResponse(status_code=401, content={"detail": "There's an already registered account with your username which isn't yours. You will need to change your username to migrate your account, which requires the assistance of support."})
                else:
                    await cursor.execute("INSERT INTO users (username, password, email, displayName, birthday, createdOn, biography, loginAttempts, lastInteraction, country) VALUES (%s, %s, %s, %s, %s, NOW(), %s, 0, NOW(), %s)", (username, hashed, email, displayName, birthday, biography, country))
                    new_account_id = cursor.lastrowid

                await conn.commit()
            except Exception as e:
                await conn.rollback()
                return JSONResponse(status_code=500, content={"detail": f"Internal server error. Details: Failed on step 2/4 (Transferring account): {e} {traceback.format_exc()}"})
    
    if new_account_id:
         async with get_connection("mnetwork") as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute("UPDATE posts SET author_id = %s WHERE author_name = %s", (new_account_id, username))
                    await cursor.execute("UPDATE threads SET author_id = %s WHERE author_name = %s", (new_account_id, username))
                    await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    return JSONResponse(status_code=500, content={"detail": f"Internal server error. Details: Failed on step 3/4 (Migrating MNetwork ownerships - Your account was migrated, though, but you can try to migrate it again to solve this issue.): {e} {traceback.format_exc()}"})

    async with get_connection("mclient") as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute("UNLOCK TABLES")
                await cursor.execute("UPDATE users SET migrated = 1 WHERE username = %s", (username,))
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                return JSONResponse(status_code=500, content={"detail": f"Internal server error. Details: {e}"})
    
    return {"message": "User migrated successfully."}

@router.post("/login")
async def route_login_user(username: str = Body(...), password: str = Body(...)):
    LOCK_MESSAGE = "This account has been temporarily blocked for multiple failed login attempts. Please try again later, or unblock it using the link sent to your email address."

    async def lock_account(cursor, username, lock_amount, utcnow):
        lock_factor = math.ceil(5 ** (lock_amount + 1)) # exponential growth of time to wait
        later = utcnow + timedelta(minutes=int(lock_factor))
        await cursor.execute("UPDATE users SET unlock_time = %s, lock_amount = lock_amount + 1 WHERE username = %s", (later, username))
        await generate_unblock_email(username)

    await asyncio.sleep(random.randint(5, 10) * 0.1) # timing variator

    async with get_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id, password, loginAttempts, unlock_time, lock_amount FROM users WHERE username = %s", (username,))
            user = await cursor.fetchone()
            utcnow = datetime.utcnow()

            if not user:
                raise HTTPException(status_code=401, detail="Incorrect username.")

            user_id, hashed, loginAttempts, unlock_time, lock_amount = user
            if not unlock_time:
                unlock_time = utcnow

            if unlock_time > utcnow:
                raise HTTPException(status_code=403, detail=LOCK_MESSAGE)

            if not check_password(password, hashed):
                if loginAttempts >= 3:
                    await lock_account(cursor, username, lock_amount, utcnow)
                    await conn.commit()

                await cursor.execute("UPDATE users SET loginAttempts = loginAttempts + 1 WHERE username = %s", (username,))
                await conn.commit()
                raise HTTPException(status_code=401, detail="Incorrect password.")

            session_token, expires_at = await create_session(conn, user_id)

            await cursor.execute("UPDATE users SET loginAttempts = 0, lock_amount = 0 WHERE username = %s", (username,))
            await conn.commit()
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
async def route_logoff_user(session_token: str = Cookie(None)):
    if not session_token:
        raise HTTPException(status_code=400, detail="Session token missing")

    async with get_connection() as conn:
        await remove_session(conn, session_token)

    response = Response(content='{"message": "Logoff successful"}', media_type="application/json")
    response.delete_cookie("session_token")
    return response

@router.get("/get-user-info")
async def route_getUserInfo(user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)

    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    return {"userinfo": user_info}

@router.get("/get-username")
async def route_getUsername(user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)

        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")

        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM bans WHERE user_id = %s AND module = %s", (user_id, "MNetwork"))
            result = await cursor.fetchone()
            banned = False
            if result:
                banned = True

            return {"username": user_info["username"], "trust": user_info["trust"], "banned": banned}

@router.get("/check-login")
async def route_check_login(user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)

    if not user_info:
        return "false"

    return "true"

@router.get("/get-settings")
async def route_getSettings(user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")

        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT settings FROM users WHERE username = %s''', (user_info["username"],))
            result = await cursor.fetchone()

            if result:
                return json.loads(result["settings"])
            else:
                raise HTTPException(status_code=404, detail="Settings not found")

@router.post("/update-settings")
async def route_updateSettings(user_id: int = Depends(get_current_user_id), settings: dict = Body(...)): # settings are supposed to be a json object
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        settings_json = json.dumps(settings)
        async with conn.cursor() as cursor:
            await cursor.execute('''UPDATE users SET settings = %s WHERE username = %s''', (settings_json, user_info["username"]))
            await conn.commit()
    
    return Response(status_code=200)

@router.post("/change-username")
async def route_changeUsername(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")

        oldUsername = user_info["username"]
        
        newUsername = str(newValue)
        if len(newUsername) < 4 or len(newUsername) > 20 or " " in newUsername:
            raise HTTPException(status_code=400, detail="Invalid username. Must be between 4 and 20 characters long with no spaces")
        
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id FROM users WHERE username = %s", (newUsername,))
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="Username already taken")
            await cursor.execute("UPDATE users SET username = %s WHERE id = %s", (newUsername, user_id))
            await cursor.execute("UPDATE friends SET author = %s WHERE author_id = %s", (newUsername, user_id))
            await conn.commit()

        oldFilename = "../uploads/pfp/" + user_info["username"] + ".jpg"
        newFilename = "../uploads/pfp/" + newUsername + ".jpg"
        if os.path.exists(oldFilename):
            os.rename(oldFilename, newFilename)

    async with get_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE posts SET author_name = %s WHERE author_id = %s", (newUsername, user_id))
            await cursor.execute("UPDATE threads SET author_name = %s WHERE author_id = %s", (newUsername, user_id))
            await cursor.execute("UPDATE communities SET author_name = %s WHERE author_id = %s", (newUsername, user_id))
            await cursor.execute("UPDATE chat SET author_name = %s WHERE author_id = %s", (newUsername, user_id))
            await conn.commit()

    return Response(status_code=200)

@router.post("/change-nickname")
async def route_changeNickname(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newNickname = str(newValue)
        if len(newNickname) < 4 or len(newNickname) > 20:
            raise HTTPException(status_code=400, detail="Invalid display name. Must be between 4 and 20 characters long.")
        
        async with conn.cursor() as cursor:
            await cursor.execute('''UPDATE users SET displayName = %s WHERE id = %s''', (newNickname, user_id))
            await conn.commit()
    
    return Response(status_code=200)

@router.post("/change-country")
async def route_changeCountry(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newCountry = str(newValue)
        if len(newCountry) < 3 or len(newCountry) > 32:
            raise HTTPException(status_code=400, detail="Invalid country. Must be between 3 and 32 characters.")
        
        async with conn.cursor() as cursor:
            await cursor.execute('''UPDATE users SET country = %s WHERE id = %s''', (newCountry, user_id))
            await conn.commit()
    
    return Response(status_code=200)

@router.post("/change-birthday")
async def route_changeBirthday(payload: ChangeDateRequest, user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newBirthday = newValue
        
        async with conn.cursor() as cursor:
            await cursor.execute('''UPDATE users SET birthday = %s WHERE id = %s''', (newBirthday, user_id))
            await conn.commit()
    
    return Response(status_code=200)

@router.post("/change-email")
async def route_changeEmail(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newEmail = str(newValue)
        if len(newEmail) < 5 or len(newEmail) > 320 or " " in newEmail or not "@" in newEmail or not "." in newEmail:
            raise HTTPException(status_code=400, detail="Invalid email address.")
        
        async with conn.cursor() as cursor:
            await cursor.execute('''UPDATE users SET email = %s, trust = 0 WHERE id = %s''', (newValue, user_id))
            await generate_verification_email(user_id)
            await conn.commit()
    
    return Response(status_code=200)

@router.post("/verify-email")
async def route_verifyEmail(user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        if user_info["trust"] > 0:
            raise HTTPException(status_code=400, detail="Email already verified.")
        
        await generate_verification_email(user_id)

    return Response(status_code=200)

@router.post("/confirm-email")
async def route_confirmEmail(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        verification_code = str(newValue)
        if user_info["trust"] > 0:
            raise HTTPException(status_code=400, detail="Email already verified.")
        
        if not await validate_verification_code(user_id, "verify", verification_code):
            raise HTTPException(status_code=400, detail="Invalid verification code.")
        
        async with conn.cursor() as cursor:
            await cursor.execute('''UPDATE users SET trust = 1 WHERE id = %s''', (user_id,))
            await conn.commit()
    
    return Response(status_code=200)

@router.post("/recover-acc")
async def route_recoverAccount(payload: recoverAcc):
    username = payload.username
    print(username)
    async with get_dict_connection() as conn:
        user_info = await get_user_information_by_username(username, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        await generate_recovery_email(username)

    return Response(status_code=200)

@router.post("/verify-recover-acc")
async def route_verifyRecoveredAccount(payload: verifyRecoverAcc):
    username = payload.username
    verification_code = payload.verification_code
    password = payload.password

    if len(password) < 6 or len(password) > 64:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long with a limit of 64 characters.")
    
    async with get_dict_connection() as conn:
        user_info = await get_user_information_by_username(username)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        user_id = user_info["id"]
        if await validate_verification_code(user_id, "recovery", verification_code):
            hashed = hash_password(password)

            async with conn.cursor() as cursor:
                await cursor.execute('''UPDATE users SET password = %s WHERE id = %s''', (hashed, user_id))
                await conn.commit()

            session_token, expires_at = await create_session(conn, user_id)

            response = Response(content='{"message": "Login successful"}', media_type="application/json")
            response.set_cookie(
                key="session_token",
                value=session_token,
                httponly=True,
                samesite="lax",
                max_age=7*24*3600
            )
            return response
        else:
            raise HTTPException(status_code=401, detail="Invalid code.")
        
@router.post("/verify-unlock-acc")
async def route_verifyUnlockedAccount(payload: verifyUnlockAcc):
    username = payload.username
    verification_code = payload.verification_code
    
    async with get_dict_connection() as conn:
        user_info = await get_user_information_by_username(username)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        user_id = user_info["id"]
        if await validate_verification_code(user_id, "unblock", verification_code):
            session_token, expires_at = await create_session(conn, user_id)

            response = Response(content='{"message": "Login successful"}', media_type="application/json")
            response.set_cookie(
                key="session_token",
                value=session_token,
                httponly=True,
                samesite="lax",
                max_age=7*24*3600
            )
            return response
        else:
            raise HTTPException(status_code=401, detail="Invalid code.")

@router.post("/change-biography")
async def route_changeBiography(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        newValue = payload.value
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")
        
        newBiography = str(newValue)
        if len(newBiography) < 5 or len(newBiography) > 1000:
            raise HTTPException(status_code=400, detail="Too long biography")
        
        async with conn.cursor() as cursor:
            await cursor.execute('''UPDATE users SET biography = %s WHERE id = %s''', (newValue, user_id))
            await conn.commit()
    
    return Response(status_code=200)

@router.post("/change-password")
async def route_changePassword(payload: ChangePasswordRequest, user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        async with conn.cursor() as cursor:
            user_info = await get_user_information(user_id, conn)
            oldValue = payload.oldValue
            newValue = payload.newValue
            if not user_info:
                raise HTTPException(status_code=404, detail="User not found - You need to login first.")

            oldPassword = str(oldValue)

            await cursor.execute('''SELECT password FROM users WHERE id = %s''', (user_id,))
            result = await cursor.fetchone()
            hashed = result["password"]
            if not check_password(oldPassword, hashed):
                raise HTTPException(status_code=401, detail="Invalid credentials")

            newPassword = hash_password(newValue)
            if len(newPassword) < 6 or len(newPassword) > 64:
                raise HTTPException(status_code=400, detail="Invalid password. Must be at least 6 characters long.")
            
            await cursor.execute('''UPDATE users SET password = %s WHERE id = %s''', (newPassword, user_id))
            await conn.commit()
    return Response(status_code=200)

@router.post("/delete-account")
async def route_deleteAccount(payload: ChangeFieldRequest, user_id: int = Depends(get_current_user_id)):
    async with get_dict_connection() as conn:
        async with conn.cursor() as cursor:
            user_info = await get_user_information(user_id, conn)
            currentPassword = payload.value
            if not user_info:
                raise HTTPException(status_code=404, detail="User not found - You need to login first.")

            password = str(currentPassword)

            await cursor.execute('''SELECT password FROM users WHERE id = %s''', (user_id,))
            result = await cursor.fetchone()
            hashed = result["password"]
            if not check_password(password, hashed):
                raise HTTPException(status_code=401, detail="Invalid credentials")
            
            await cursor.execute('''DELETE FROM users WHERE id = %s''', (user_id,))
            await conn.commit()

        await remove_session_by_user_id(conn, user_id)

    response = Response(content='{"message": "Account deletion successful"}', media_type="application/json")
    response.delete_cookie("session_token")
    return Response(status_code=200)

@router.post("/upload-pfp")
async def route_upload_image(user_id: int = Depends(get_current_user_id), file: UploadFile = File(...)):
    user_info = None
    async with get_dict_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found - You need to login first.")

    premium = user_info["premium"]
    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max size is 50 KB.")

    filename_lower = file.filename.lower()
    if contents[:6] in (b"GIF87a", b"GIF89a"):
        if premium != 1:
            raise HTTPException(status_code=403, detail="GIF uploads are only allowed for premium users.")
        file_location = os.path.join(UPLOAD_FOLDER, f"{user_info['username']}.gif")
    else:
        file_location = os.path.join(UPLOAD_FOLDER, f"{user_info['username']}.jpg")

    with open(file_location, "wb") as buffer:
        buffer.write(contents)

    return {"filename": file.filename, "message": "Image uploaded successfully"}

@router.post("/report")
async def report_abuse(payload: reportAbuse, user_id = Depends(get_current_user_id)):
    module = payload.module
    reason = payload.reason
    content_type = payload.type
    content_id = payload.id
    details = payload.detail
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("INSERT INTO reports (parent_id, parent_module, parent_type, author_id, type, content) VALUES (%s, %s, %s, %s, %s, %s)", (content_id, module, content_type, user_id, reason, details))
            await conn.commit()
            return { "message": "Success" }
        
@router.get("/notifications")
async def get_notifications(user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY timestamp DESC LIMIT 50", (user_id,))
            result = await cursor.fetchall()

            await cursor.execute("UPDATE notifications SET is_read = 1 WHERE user_id = %s", (user_id,))
            await conn.commit()

            return { "notifications": result }
        
@router.get("/notifications-preview")
async def get_notifications_preview(user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id = %s AND is_read = 0", (user_id,))
            result = await cursor.fetchone()
            
            notification_count = result["cnt"]

            return { "notifications": notification_count }
        
@router.post("/accept-admin")
async def accept_admin(user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE users SET trust = 10 WHERE id = %s AND trust = 9", (user_id,))

            if cursor.rowcount == 0:
                raise HTTPException(status_code=403, detail="You are not invited to become an administrator.")

            await conn.commit()

            return { "message": "You are now an administrator" }
        
@router.get("/get-ban")
async def router_get_ban(user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM bans WHERE user_id = %s LIMIT 1", (user_id,))
            result = await cursor.fetchone()

            return {"ban": result or None}
