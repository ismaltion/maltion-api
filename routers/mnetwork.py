from fastapi import APIRouter, Body, Depends, HTTPException, Response, Cookie, UploadFile, File
from fastapi.responses import JSONResponse
from models import mnetwork_create_community, mnetwork_create_thread, mnetwork_create_post
from auth import get_current_user_id
from db import get_connection
from utils import get_user_information

router = APIRouter()
noAccMsg = "You need to login with a Maltion account to do this action."

@router.post("/mnetwork/create-community")
def router_create_community(payload: mnetwork_create_community, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail=noAccMsg)
    
    name = payload.name
    description = payload.description

    with get_connection("mnetwork") as conn:
        user_info = get_user_information(user_id, conn)
               
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        username = user_info.get("username")

        with conn.cursor() as cursor:
            cursor.execute('''INSERT INTO communities (author_id, author_name, name, description, locked) VALUES (%s, %s, %s, %s, 0)''', (user_id, username, name, description))
            conn.commit()
        return JSONResponse(status_code=201, content={"message": "Community created successfully."})
    
@router.post("/mnetwork/create-thread")
def router_create_thread(payload: mnetwork_create_thread, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail=noAccMsg)
    
    title = payload.title
    content = payload.content
    community_id = payload.community_id

    with get_connection("mnetwork") as conn:
        user_info = get_user_information(user_id, conn)

        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        username = user_info.get("username")

        with conn.cursor() as cursor:
            cursor.execute('''SELECT locked FROM communities WHERE id = %s''', (community_id,))
            result = cursor.fetchone()
            if result:
                if result[0] == 1:
                    raise HTTPException(status_code=401, detail="This community is locked.")
            else:
                raise HTTPException(status_code=404, detail="The community you tried to post this thread in was not found.")
            cursor.execute('''INSERT INTO threads (community_id, author_id, author_name, title, content, locked) VALUES (%s, %s, %s, %s, %s, 0)''', (community_id, user_id, username, title, content))
            conn.commit()
        return JSONResponse(status_code=201, content={"message": "Thread created successfully."})
    
@router.post("/mnetwork/create-post")
def router_create_post(payload: mnetwork_create_post, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail=noAccMsg)
    
    content = payload.content
    thread_id = payload.thread_id

    with get_connection("mnetwork") as conn:
        user_info = get_user_information(user_id, conn)

        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        username = user_info.get("username")

        with conn.cursor() as cursor:
            cursor.execute('''SELECT locked FROM threads WHERE id = %s''', (thread_id,))
            result = cursor.fetchone()
            if result:
                if result[0] == 1:
                    raise HTTPException(status_code=401, detail="This thread is locked.")
            else:
                raise HTTPException(status_code=404, detail="The thread you tried to post this in was not found.")
            cursor.execute('''INSERT INTO posts (thread_id, author_id, author_name, content) VALUES (%s, %s, %s, %s)''', (thread_id, user_id, username, content))
            conn.commit()
        return JSONResponse(status_code=201, content={"message": "Post created successfully."})