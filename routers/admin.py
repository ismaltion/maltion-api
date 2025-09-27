from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from auth import get_current_user_id
from db import get_connection, get_dict_connection
from utils import get_user_information, get_user_information_by_username, notification, send_notification, get_setting, set_setting
from models import banning, unbanning, sendNotification, addBadge
import json

router = APIRouter()

@router.get("/admin/reports")
async def router_reports(user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    async with get_dict_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        trust = int(user_info.get("trust", 0))

        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")

        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM reports ORDER BY timestamp DESC LIMIT 50")
            result = await cursor.fetchall()

            return { "reports": result }
        
@router.get("/admin/get-report")
async def router_get_report(id: int, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    async with get_dict_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        trust = int(user_info.get("trust", 0))

        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")
        
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM reports WHERE id = %s LIMIT 1", (id,))
            result = await cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Report not found.")

            content_result = None
            parent_id = result["parent_id"]
            parent_module = result["parent_module"]
            parent_type = result["parent_type"]
            author_id = result["author_id"]

            await cursor.execute("SELECT username FROM users WHERE id = %s LIMIT 1", (author_id,))
            result_2 = await cursor.fetchone()
            if result_2:
                result["author_name"] = result_2["username"]
            
            if parent_module == "mnetwork":
                async with get_dict_connection("mnetwork") as mnetwork_conn:
                    async with mnetwork_conn.cursor() as mnetwork_cursor:
                        parent_type_query = "posts"
                        table_map = {
                            "post": "posts",
                            "thread": "threads",
                            "community": "communities"
                        }
                
                        parent_type_query = table_map[parent_type]
                        await mnetwork_cursor.execute(f"SELECT * FROM {parent_type_query} WHERE id = {parent_id} LIMIT 1")
                        content_result = await mnetwork_cursor.fetchone()
            
            return { "report_detail": result, "report_content": content_result }
        
@router.post("/admin/ban")
async def router_reports(payload: banning, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    banned_username = payload.username
    module = payload.module
    reason = payload.reason
    
    async with get_dict_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        trust = user_info["trust"]
        print(trust)
        trust = int(trust)
        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")
        
        banned_info = await get_user_information_by_username(banned_username, conn)
        if not banned_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        banned_id = int(banned_info["id"])
        async with conn.cursor() as cursor:
            await cursor.execute("INSERT INTO bans (user_id, author_id, module, reason) VALUES (%s, %s, %s, %s)", (banned_id, user_id, module, reason))
            await conn.commit()

            return { "reports": "User banned successfully." }
        
@router.post("/admin/unban")
async def router_reports(payload: unbanning, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    banned_username = payload.username

    async with get_dict_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        trust = int(user_info.get("trust", 0))

        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")
        
        banned_info = await get_user_information_by_username(banned_username, conn)
        if not banned_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        banned_id = int(banned_info["id"])
        async with conn.cursor() as cursor:
            await cursor.execute("DELETE FROM bans WHERE user_id = %s", (banned_id,))
            await conn.commit()
            
            return { "reports": "User unbanned successfully." }
        
@router.post("/admin/send-notification")
async def router_reports(payload: sendNotification, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    notified_username = payload.username
    notified_content = payload.content
    
    async with get_dict_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        trust = user_info["trust"]
        print(trust)
        trust = int(trust)
        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")
        
        notified_info = await get_user_information_by_username(notified_username, conn)
        if not notified_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        notified_id = int(notified_info["id"])
        
        notify = await notification("mnetwork", notified_content, 0, "admin_warning")
        await send_notification(notified_id, notify)

        return { "reports": "Notification sent successfully." }
    
@router.post("/admin/add-badge")
async def add_badge(payload: addBadge, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    subject_username = payload.username
    new_badge = payload.badge

    async with get_dict_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        trust = int(user_info["trust"])
        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")
        if trust < 20:
            raise HTTPException(status_code=403, detail="You need higher permissions to do this")
        
        subject_info = await get_user_information_by_username(subject_username, conn)
        if not subject_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        subject_id = int(subject_info["id"])

        existing_badges = await get_setting(subject_id, "Badges")
        try:
            subject_badges = json.loads(existing_badges) if existing_badges else []
        except json.JSONDecodeError:
            subject_badges = []

        if new_badge not in subject_badges:
            subject_badges.append(new_badge)

        await set_setting(subject_id, "Badges", json.dumps(subject_badges))

        return {"detail": f"Badge '{new_badge}' added to {subject_username}"}
