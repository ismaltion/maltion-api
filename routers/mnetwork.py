from fastapi import APIRouter, Body, Depends, HTTPException, Response, Cookie, UploadFile, File
from fastapi.responses import JSONResponse
from models import mnetwork_create_community, mnetwork_create_thread, mnetwork_create_post, like, transferCommunityOwnership, deleteCommunity, updateCommunitySettings
from auth import get_current_user_id, check_password
from db import get_connection, get_dict_connection
from utils import get_user_information
from typing import Optional
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
    
# should work even if not logged in
@router.get("/mnetwork/get-community")
def router_get_community(community: int, user_id = Depends(get_current_user_id)):
    liked = False
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT author_id, author_name, name, description, locked, can_add, timestamp, last_activity, follows FROM communities WHERE id = %s LIMIT 1''', (community,))
            result1 = cursor.fetchone()
            if result1:
                if user_id:
                    # return if user is following this community
                    cursor.execute('''SELECT id FROM community_follows WHERE community_id = %s AND author_id = %s LIMIT 1''', (community, user_id))
                    result2 = cursor.fetchone()

                    liked = bool(result2)
            else:
                raise HTTPException(status_code=404, detail="Community not found.")
            
            locked = result1["locked"]
            can_add = result1["can_add"]
            settings = { "locked": locked, "can_add": can_add }

    return {"community": result1, "liked": liked, "settings": settings }

@router.post("/mnetwork/update-community-settings")
def router_update_community_settings(payload: updateCommunitySettings, user_id = Depends(get_current_user_id)):

    community_id = payload.community_id
    locked = payload.locked
    can_add = payload.can_add

    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT author_id FROM communities WHERE id = %s", (community_id,))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Community not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the community to do this operation.")
            
            cursor.execute("UPDATE communities SET locked = %s, can_add = %s WHERE id = %s", (locked, can_add, community_id))
            conn.commit()
            return { "message": "Settings updated successfully" }
    
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
                    cursor.execute('''SELECT COUNT(*) AS cnt FROM post_likes WHERE post_id = %s''', (post,))
                    result3 = cursor.fetchone()
                    likes = result3["cnt"]
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
                    cursor.execute('''SELECT COUNT(*) AS cnt FROM thread_likes WHERE thread_id = %s''', (thread,))
                    result3 = cursor.fetchone()
                    likes = result3["cnt"]
                    cursor.execute('''UPDATE threads SET likes = %s WHERE id = %s''', (likes, thread))
                    conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like added successfully."})
            else:
                raise HTTPException(status_code=404, detail="The thread you attempted to like was not found.")
            
@router.post("/mnetwork/follow-community")
def router_mnetwork_follow_community(payload: like, user_id = Depends(get_current_user_id)):
    with get_dict_connection("mnetwork") as conn:
        community = payload.id
        with conn.cursor() as cursor:
            cursor.execute('''SELECT follows FROM communities WHERE id = %s''', (community,))
            result1 = cursor.fetchone()
            if result1:
                cursor.execute('''SELECT id FROM community_follows WHERE community_id = %s AND author_id = %s''', (community, user_id))
                result2 = cursor.fetchone()
                if result2:
                    raise HTTPException(status_code=400, detail="You already liked this community.")
                else:
                    cursor.execute('''INSERT INTO community_follows (community_id, author_id) VALUES (%s, %s)''', (community, user_id))
                    cursor.execute('''SELECT COUNT(*) AS cnt FROM community_follows WHERE community_id = %s''', (community,))
                    result3 = cursor.fetchone()
                    likes = result3["cnt"]
                    cursor.execute('''UPDATE communities SET follows = %s WHERE id = %s''', (likes, community))
                    conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Follow added successfully."})
            else:
                raise HTTPException(status_code=404, detail="The community you attempted to follow was not found.")
            
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
                    cursor.execute('''SELECT COUNT(*) AS cnt FROM post_likes WHERE post_id = %s''', (post,))
                    result3 = cursor.fetchone()
                    likes = result3["cnt"]
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
                    cursor.execute('''SELECT COUNT(*) AS cnt FROM thread_likes WHERE thread_id = %s''', (thread,))
                    result3 = cursor.fetchone()
                    likes = result3["cnt"]
                    cursor.execute('''UPDATE threads SET likes = %s WHERE id = %s''', (likes, thread))
                    conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like removed successfully."})
                else:
                    raise HTTPException(status_code=400, detail="You didn't like this thread yet.")
            else:
                raise HTTPException(status_code=404, detail="The thread you attempted to remove your like from was not found.")
                    
@router.get("/mnetwork/get-feed")
def router_mnetwork_get_feed(user_id = Depends(get_current_user_id)):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                '''SELECT community_id FROM community_follows WHERE author_id = %s''',
                (user_id,)
            )
            followed_communities = [row['community_id'] for row in cursor.fetchall()]
            
            if followed_communities:
                format_strings = ",".join(['%s'] * len(followed_communities))
                query = f'''
                    SELECT * FROM threads
                    WHERE community_id IN ({format_strings})
                    ORDER BY timestamp DESC
                    LIMIT 30
                '''
                cursor.execute(query, tuple(followed_communities))
                threads = cursor.fetchall()
            else:
                cursor.execute(
                    "SELECT * FROM threads WHERE community_id = 1 ORDER BY timestamp DESC LIMIT 30"
                )
                threads = cursor.fetchall()
            
            return threads

@router.post("/mnetwork/transfer-community-ownership")
def transfer_community_ownership(payload: transferCommunityOwnership, user_id = Depends(get_current_user_id)):

    community_id = payload.community_id
    new_owner = payload.new_owner
    password = payload.password

    with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            with conn.cursor() as cursor:
                if user_id:
                    cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (community_id,))
                    result = cursor.fetchone()
                    if result:
                        author = result["author_id"]

                        if author == user_id:
                            cursor.execute("SELECT password FROM users WHERE id = %s", (user_id,))
                            credentials = cursor.fetchone()

                            if not credentials:
                                return JSONResponse(status_code=500, detail="Unexpected error occurred: Missing user information. Contact support to fix this.")

                            hashed_password = credentials["password"]

                            if not check_password(password, hashed_password):
                                return JSONResponse(status_code=401, detail="Incorrect password.")

                            cursor.execute("SELECT id, username FROM users WHERE username = %s", (new_owner,))
                            result_2 = cursor.fetchone()
                            if result_2:
                                new_owner_id = result_2["id"]
                                new_owner_username = result_2["username"] # to match database's username since it's not case sensitive

                                cursor.execute("UPDATE communities SET author_id = %s, author_name = %s WHERE id = %s", (new_owner_id, new_owner_username, community_id))
                                conn.commit()
                                return {"message": "Ownership successfully transferred."}
                            else:
                                return JSONResponse(status_code=404, detail="New owner not found. Make sure you wrote their username right.")
                        else:
                            return JSONResponse(status_code=403, detail="You need to be the owner of this community to do this action.")
                    else:
                        return JSONResponse(status_code=404, detail="Community not found.")
                else:
                    return JSONResponse(status_code=401, detail="Login required.")
        except Exception as e:
            conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")

@router.post("/mnetwork/delete-community")
def delete_community(payload: deleteCommunity, user_id=Depends(get_current_user_id)):
    community_id = payload.community_id
    password = payload.password

    with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            with conn.cursor() as cursor:
                if not user_id:
                    return JSONResponse(status_code=401, content={"detail": "Login required."})

                cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (community_id,))
                result = cursor.fetchone()

                if not result:
                    return JSONResponse(status_code=404, content={"detail": "Community not found."})

                author = result["author_id"]

                if author != user_id:
                    return JSONResponse(status_code=403, content={"detail": "You must be the owner of this community to delete it."})
                
                with get_dict_connection("main") as main_conn:
                    with main_conn.cursor() as main_cursor:
                        main_cursor.execute("SELECT password FROM users WHERE id = %s", (user_id,))
                        credentials = main_cursor.fetchone()

                        if not credentials:
                            return JSONResponse(
                                status_code=500,
                                content={"detail": "Unexpected error occurred: Missing user information. Contact support to fix this."}
                            )

                hashed_password = credentials["password"]
                if not check_password(password, hashed_password):
                    return JSONResponse(status_code=401, content={"detail": "Incorrect password."})

                cursor.execute("DELETE FROM communities WHERE id = %s", (community_id,))
                conn.commit()

                return {"message": "Community successfully deleted."}

        except Exception as e:
            conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")