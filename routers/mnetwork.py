from fastapi import APIRouter, Body, Depends, HTTPException, Response, Cookie, UploadFile, File
from fastapi.responses import JSONResponse
from models import mnetwork_create_community, mnetwork_create_thread, mnetwork_create_post, like
from auth import get_current_user_id
from db import get_connection, get_dict_connection
from utils import get_user_information
import json

router = APIRouter()
noAccMsg = "You need to login with a Maltion account to do this action."

@router.post("/mnetwork/create-community")
def router_create_community(payload: mnetwork_create_community, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail=noAccMsg)
    
    name = payload.name
    description = payload.description

    with get_connection("mnetwork") as conn:
        user_info = get_user_information(user_id)
               
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
        user_info = get_user_information(user_id)

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
        user_info = get_user_information(user_id)

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
    
@router.get("/mnetwork/get-community")
def router_get_community(community: int):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM communities WHERE id = %s''', (community,))
            result = cursor.fetchone()
        return result
    
@router.get("/mnetwork/get-thread")
def router_get_community(thread: int):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM threads WHERE id = %s''', (thread,))
            result = cursor.fetchone()
        return result

@router.get("/mnetwork/get-community-threads")
def router_get_community_threads(community: int):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM threads WHERE community_id = %s LIMIT 50''', (community,))
            result = cursor.fetchall()
            return result

@router.get("/mnetwork/get-thread-posts")
def router_get_thread_posts(thread: int):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM posts WHERE thread_id = %s LIMIT 50''', (thread,))
            result = cursor.fetchall()
            return result

@router.get("/mnetwork/search-community")
def router_search_community(query: str):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM communities WHERE name LIKE %s OR description LIKE %s ORDER BY last_activity DESC LIMIT 50''', (f"%{query}%", f"%{query}%"))
            result = cursor.fetchall()
            return result
        
@router.get("/mnetwork/my-communities")
def router_search_community(user_id = Depends(get_current_user_id)):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM communities WHERE author_id = %s LIMIT 50''', (user_id,))
            result = cursor.fetchall()
            return result
        
@router.post("/mnetwork/like-post")
def router_mnetwork_like_post(payload: like, user_id = Depends(get_current_user_id)):
    with get_dict_connection("mnetwork") as conn:
        post = payload.id
        with conn.cursor() as cursor:
            cursor.execute('''SELECT likes FROM posts WHERE id = %s''', (post,))
            result1 = cursor.fetchone()
            if result1:
                cursor.execute('''SELECT id FROM post_likes WHERE post_id = %s AND author_id = %s''', (post, user_id))
                result2 = cursor.fetchone()
                if result2:
                    raise HTTPException(status_code=400, detail="You already liked this post.")
                else:
                    cursor.execute('''INSERT INTO post_likes (post_id, author_id) VALUES (%s, %s)''', (post, user_id))
                    cursor.execute('''SELECT COUNT(*) FROM post_likes WHERE post_id = %s''', (post,))
                    result3 = cursor.fetchone()
                    likes = result3[0]
                    cursor.execute('''UPDATE posts SET likes = %s WHERE id = %s''', (likes, post))
                    conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like added successfully."})
            else:
                raise HTTPException(status_code=404, detail="The post you attempted to like was not found.")
            
@router.post("/mnetwork/like-thread")
def router_mnetwork_like_thread(payload: like, user_id = Depends(get_current_user_id)):
    with get_dict_connection("mnetwork") as conn:
        thread = payload.id
        with conn.cursor() as cursor:
            cursor.execute('''SELECT likes FROM threads WHERE id = %s''', (thread,))
            result1 = cursor.fetchone()
            if result1:
                cursor.execute('''SELECT id FROM thread_likes WHERE thread_id = %s AND author_id = %s''', (thread, user_id))
                result2 = cursor.fetchone()
                if result2:
                    raise HTTPException(status_code=400, detail="You already liked this thread.")
                else:
                    cursor.execute('''INSERT INTO thread_likes (thread_id, author_id) VALUES (%s, %s)''', (thread, user_id))
                    cursor.execute('''SELECT COUNT(*) FROM thread_likes WHERE thread_id = %s''', (thread,))
                    result3 = cursor.fetchone()
                    likes = result3[0]
                    cursor.execute('''UPDATE threads SET likes = %s WHERE id = %s''', (likes, thread))
                    conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like added successfully."})
            else:
                raise HTTPException(status_code=404, detail="The thread you attempted to like was not found.")
            
@router.post("/mnetwork/unlike-post")
def router_mnetwork_unlike_post(payload: like, user_id = Depends(get_current_user_id)):
    with get_dict_connection("mnetwork") as conn:
        post = payload.id
        with conn.cursor() as cursor:
            cursor.execute('''SELECT likes FROM posts WHERE id = %s''', (post,))
            result1 = cursor.fetchone()
            if result1:
                cursor.execute('''SELECT id FROM post_likes WHERE post_id = %s AND author_id = %s''', (post, user_id))
                result2 = cursor.fetchone()
                if result2:
                    cursor.execute('''DELETE FROM post_likes WHERE post_id = %s AND author_id = %s''', (post, user_id))
                    cursor.execute('''SELECT COUNT(*) FROM post_likes WHERE post_id = %s''', (post,))
                    result3 = cursor.fetchone()
                    likes = result3[0]
                    cursor.execute('''UPDATE posts SET likes = %s WHERE id = %s''', (likes, post))
                    conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like removed successfully."})
                else:
                    raise HTTPException(status_code=400, detail="You didn't like this post yet.")
            else:
                raise HTTPException(status_code=404, detail="The post you attempted to remove your like from was not found.")
            
@router.post("/mnetwork/unlike-thread")
def router_mnetwork_unlike_thread(payload: like, user_id = Depends(get_current_user_id)):
    with get_dict_connection("mnetwork") as conn:
        thread = payload.id
        with conn.cursor() as cursor:
            cursor.execute('''SELECT likes FROM threads WHERE id = %s''', (thread,))
            result1 = cursor.fetchone()
            if result1:
                cursor.execute('''SELECT id FROM thread_likes WHERE thread_id = %s AND author_id = %s''', (thread, user_id))
                result2 = cursor.fetchone()
                if result2:
                    cursor.execute('''DELETE FROM thread_likes WHERE thread_id = %s AND author_id = %s''', (thread, user_id))
                    cursor.execute('''SELECT COUNT(*) FROM thread_likes WHERE thread_id = %s''', (thread,))
                    result3 = cursor.fetchone()
                    likes = result3[0]
                    cursor.execute('''UPDATE threads SET likes = %s WHERE id = %s''', (likes, thread))
                    conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like removed successfully."})
                else:
                    raise HTTPException(status_code=400, detail="You didn't like this thread yet.")
            else:
                raise HTTPException(status_code=404, detail="The thread you attempted to remove your like from was not found.")