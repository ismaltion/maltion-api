from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from auth import get_current_user_id
from db import get_connection, get_dict_connection
from utils import get_user_information, get_user_information_by_username
from models import banning, unbanning

router = APIRouter()

@router.get("/admin/reports")
def router_reports(user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    with get_dict_connection("main") as conn:
        user_info = get_user_information(user_id)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")
        trust = int(user_info.get("trust", 0))

        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")

        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM reports ORDER BY timestamp DESC LIMIT 50")
            result = cursor.fetchall()

            return { "reports": result }
        
@router.get("/admin/get-report")
def router_get_report(id: int, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    with get_dict_connection("main") as conn:
        user_info = get_user_information(user_id)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")
        trust = int(user_info.get("trust", 0))

        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM reports WHERE id = %s LIMIT 1", (id,))
            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Report not found")

            content_result = None
            parent_id = result["parent_id"]
            parent_module = result["parent_module"]
            parent_type = result["parent_type"]

            if parent_module == "mnetwork":
                with get_dict_connection("MNetwork") as mnetwork_conn:
                    with mnetwork_conn.cursor() as mnetwork_cursor:
                        parent_type_query = "posts"
                        if parent_type:
                            table_map = {
                                    "post": "posts",
                                    "thread": "threads",
                                    "community": "communities"
                            }
                
                            parent_type_query = str(table_map.get(parent_type, "posts"))
                        mnetwork_cursor.execute(f"SELECT * FROM {parent_type_query} WHERE id = %s LIMIT 1", (parent_id,))
                        content_result = mnetwork_cursor.fetchone()
            
            return { "report_detail": result, "report_content": content_result }
        
@router.post("/admin/ban")
def router_reports(payload: banning, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    banned_username = payload.username
    module = payload.module
    reason = payload.reason
    
    with get_dict_connection("main") as conn:
        user_info = get_user_information(user_id)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")
        
        trust = user_info["trust"]
        print(trust)
        trust = int(trust)
        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")
        
        banned_info = get_user_information_by_username(banned_username, conn)
        if not banned_info:
            raise HTTPException(status_code=404, detail="User not found")
        
        banned_id = int(banned_info["id"])
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO bans (user_id, author_id, module, reason) VALUES (%s, %s, %s, %s)", (banned_id, user_id, module, reason))
            conn.commit()

            return { "reports": "User banned successfully." }
        
@router.post("/admin/unban")
def router_reports(payload: unbanning, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You must log in to do this action.")
    
    banned_username = payload.username

    with get_dict_connection("main") as conn:
        user_info = get_user_information(user_id)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")
        trust = int(user_info.get("trust", 0))

        if trust < 10:
            raise HTTPException(status_code=403, detail="You are not an admin.")
        
        banned_info = get_user_information_by_username(banned_username, conn)
        if not banned_info:
            raise HTTPException(status_code=404, detail="User not found")
        
        banned_id = int(banned_info["id"])
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM bans WHERE user_id = %s", (banned_id,))
            conn.commit()
            
            return { "reports": "User unbanned successfully." }