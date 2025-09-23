from fastapi import APIRouter, Body, Depends, HTTPException, Response, Cookie, UploadFile, File, UploadFile, Form, Request
from fastapi.responses import JSONResponse
from models import mnetwork_create_community, mnetwork_create_thread, mnetwork_create_post, editCommunity, editThread, threadOperation, like, follow, transferCommunityOwnership, deleteCommunity, updateCommunitySettings, deletePost, field_1
from auth import get_current_user_id, check_password, hash_ip
from db import get_connection, get_dict_connection
from utils import get_user_information, get_user_information_by_username, send_notification, notification, check_ban, set_setting, get_setting, add_badge
from typing import Optional
from config import IMAGE_UPLOAD_FOLDER
from PIL import Image
import re, os, io, json

MAX_UPLOAD_SIZE = 1024 * 1024 * 5
ALLOWED_IMAGE_TYPES = {"jpeg", "png", "gif"}

router = APIRouter()
noAccMsg = "You need to login with a Maltion account to do this action."

@router.post("/mnetwork/create-community")
def router_create_community(payload: mnetwork_create_community, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail=noAccMsg)
    
    check_ban(user_id, "MNetwork")
    
    name = payload.name
    description = payload.description

    with get_connection("mnetwork") as conn:
        user_info = get_user_information(user_id)
               
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        username = user_info.get("username")
        premium = user_info["premium"]
        username_color = "#808080"
        if premium == 1:
            username_color = get_setting(user_id, "Username color")
        
        username = user_info["username"]
        extra_information = { "Username color": username_color }
        extra_info = json.dumps(extra_information)

        with conn.cursor() as cursor:
            cursor.execute('''INSERT INTO communities (author_id, author_name, name, description, locked, extra_info) VALUES (%s, %s, %s, %s, 0, %s)''', (user_id, username, name, description, extra_info))
            conn.commit()
        return JSONResponse(status_code=201, content={"message": "Community created successfully."})
    
@router.post("/mnetwork/create-thread")
def router_create_thread(payload: mnetwork_create_thread, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail=noAccMsg)
    
    check_ban(user_id, "MNetwork")
    
    title = payload.title
    content = payload.content
    community_id = payload.community_id

    with get_connection("mnetwork") as conn:
        user_info = get_user_information(user_id)

        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        username = user_info.get("username")
        premium = user_info["premium"]
        username_color = "#808080"
        if premium == 1:
            username_color = get_setting(user_id, "Username color")
        
        username = user_info["username"]
        extra_information = { "Username color": username_color }
        extra_info = json.dumps(extra_information)

        with conn.cursor() as cursor:
            cursor.execute('''SELECT locked, can_add, id FROM communities WHERE id = %s''', (community_id,))
            result = cursor.fetchone()
            if result:
                if result[0] == 1:
                    raise HTTPException(status_code=401, detail="This community is locked.")
                if result[1] == 0:
                    raise HTTPException(status_code=401, detail="This community doesn't allow the creation of threads.")
                
                comm_id = result[2]
                
                cursor.execute('''INSERT INTO threads (community_id, author_id, author_name, title, content, locked, extra_info) VALUES (%s, %s, %s, %s, %s, 0, %s)''', (community_id, user_id, username, title, content, extra_info))
                cursor.execute('''UPDATE communities SET activity_detail = %s WHERE id = %s''', (f"{username} created a new thread: {title}", comm_id))
                cursor.execute('''UPDATE communities SET last_activity = NOW() WHERE id = %s''', comm_id)
                conn.commit()
            else:
                raise HTTPException(status_code=404, detail="The community you tried to post this thread in was not found.")
            
        return JSONResponse(status_code=201, content={"message": "Thread created successfully."})

@router.post("/mnetwork/create-post")
async def router_create_post(
    content: str = Form(...),
    thread_id: int = Form(...),
    parent_post_id: int = Form(...),
    image: Optional[UploadFile] = File(None),
    user_id: int = Depends(get_current_user_id)
):
    has_image = 0
    if image:
        has_image = 1

    comm_id = 0

    if not user_id:
        raise HTTPException(status_code=401, detail=noAccMsg)
    
    check_ban(user_id, "MNetwork")

    with get_connection("mnetwork") as conn:
        user_info = get_user_information(user_id)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        username = user_info["username"]
        premium = user_info["premium"]
        username_color = "#808080"
        if premium == 1:
            username_color = get_setting(user_id, "Username color")
        
        extra_information = { "Username color": username_color }
        extra_info = json.dumps(extra_information)

        with conn.cursor() as cursor:
            cursor.execute('''SELECT locked, community_id, title FROM threads WHERE id = %s''', (thread_id,))
            result = cursor.fetchone()
            if result:
                if result[0] == 1:
                    raise HTTPException(status_code=401, detail="This thread is locked.")
            else:
                raise HTTPException(status_code=404, detail="The thread you tried to post this in was not found.")
            
            comm_id = result[1]
            title = result[2]

            cursor.execute('''SELECT id, locked, name FROM communities WHERE id = %s''', (comm_id,))
            result = cursor.fetchone()
            if result:
                if result[1] == 1:
                    raise HTTPException(status_code=401, detail="This community is locked.")
            else:
                raise HTTPException(status_code=404, detail="The community you tried to post this in was not found.")
            
            community_name = result[2]

            cursor.execute('''SELECT parent_post_id FROM posts WHERE id = %s''', (parent_post_id,))
            result = cursor.fetchone()

            if result:
                if result[0] > 0:
                    raise HTTPException(status_code=400, detail="You cannot nest your post under a nested post.")
            else:
                if parent_post_id > 0:
                    raise HTTPException(status_code=404, detail="The parent post was not found.")

            cursor.execute(
                '''INSERT INTO posts (thread_id, author_id, author_name, content, has_image, parent_post_id, extra_info) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id''',
                (thread_id, user_id, username, content, has_image, parent_post_id, extra_info)
            )
            post_id = cursor.fetchone()[0]
            cursor.execute('''UPDATE threads SET activity_detail = %s WHERE id = %s''', (f"{username} added a post.", thread_id,))
            cursor.execute('''UPDATE threads SET last_activity = NOW() WHERE id = %s''', (thread_id,))
            cursor.execute('''UPDATE communities SET activity_detail = %s WHERE id = %s''', (f"{username} posted in thread: {title}", comm_id,))
            cursor.execute('''UPDATE communities SET last_activity = NOW() WHERE id = %s''', (comm_id,))
            

            if image:
                image_bytes = await image.read()
                if len(image_bytes) > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="Image exceeds 5 MB limit.")

                try:
                    img = Image.open(io.BytesIO(image_bytes))
                    img.verify()
                    img = Image.open(io.BytesIO(image_bytes))
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    
                    max_size = 2000
                    if img.width > max_size or img.height > max_size:
                        img.thumbnail((max_size, max_size), Image.ANTIALIAS)

                    os.makedirs(IMAGE_UPLOAD_FOLDER, exist_ok=True)
                    file_location = f"{IMAGE_UPLOAD_FOLDER}/{post_id}.jpg"
                    img.save(file_location, format="JPEG", quality=80, optimize=True)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Image processing failed: {str(e)}")

            mentions = set(re.findall(r"(?<!\w)@([A-Za-z0-9_.-]+)(?=\s|$|[.,!?:])", content))
            was_everyone_mentioned = False
            for recipient in mentions:
                if recipient != username:
                    if parent_post_id == 0:
                        notify = notification("MNetwork", f"@{username} mentioned you in {title} of {community_name}", thread_id, "post_mention")
                    else:
                        notify = notification("MNetwork", f"@{username} replied to you in {title} of {community_name}", thread_id, "post_reply")
                    if recipient == "everyone" and not was_everyone_mentioned:
                        was_everyone_mentioned = True
                        cursor.execute("SELECT * FROM community_follows WHERE community_id = %s", (comm_id,))
                        result = cursor.fetchall()
                        if parent_post_id == 0:
                            notify = notification("MNetwork", f"@{username} mentioned everyone in {title} of {community_name}", thread_id, "post_mention")
                        else:
                            notify = notification("MNetwork", f"@{username} replied to everyone in {title} of {community_name}", thread_id, "post_reply")
                        for processed_recipient in result:
                            send_notification(processed_recipient[2], notify)
                    else:
                        recipient_data = get_user_information_by_username(recipient)
                        if recipient_data:
                            recipient_id = recipient_data.get("id")
                            send_notification(recipient_id, notify)

            conn.commit()

        return JSONResponse(status_code=201, content={"message": "Post created successfully."})

    
# should work even if not logged in
@router.get("/mnetwork/get-community")
def router_get_community(community: int, user_id = Depends(get_current_user_id)):
    liked = False
    check_ban(user_id, "MNetwork")
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
    check_ban(user_id, "MNetwork")

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
def router_get_thread(thread: int, user_id = Depends(get_current_user_id)):
    liked = False
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM threads WHERE id = %s LIMIT 1', (thread,))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Thread not found.")

            try:
                result["extra_info"] = json.loads(result.get("extra_info", "{}"))
            except (TypeError, json.JSONDecodeError):
                result["extra_info"] = {}

            community_id = result["community_id"]
            cursor.execute('SELECT * FROM communities WHERE id = %s LIMIT 1', (community_id,))
            community_result = cursor.fetchone()

            if user_id:
                cursor.execute(
                    'SELECT id FROM thread_likes WHERE thread_id = %s AND author_id = %s LIMIT 1',
                    (thread, user_id)
                )
                follow_result = cursor.fetchone()
                liked = bool(follow_result)

    return {
        "thread": result,
        "community": community_result,
        "liked": liked
    }

@router.get("/mnetwork/get-community-threads")
def router_get_community_threads(community: int):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM threads WHERE community_id = %s AND pinned = 0 LIMIT 50''', (community,))
            result = cursor.fetchall()

            cursor.execute('''SELECT * FROM threads WHERE community_id = %s AND pinned = 1 LIMIT 50''', (community,))
            pinned = cursor.fetchall()
            return { "threads": result, "pinned": pinned }

@router.get("/mnetwork/get-thread-posts")
def router_get_thread_posts(thread: int, user_id = Depends(get_current_user_id)):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM posts WHERE thread_id = %s ORDER BY timestamp DESC LIMIT 50''', (thread,))
            posts = cursor.fetchall()

            liked_post_ids = set()
            if user_id and posts:
                post_ids = [post["id"] for post in posts]

                placeholders = ','.join(['%s'] * len(post_ids))
                query = f'''SELECT post_id FROM post_likes WHERE author_id = %s AND post_id IN ({placeholders})'''

                cursor.execute(query, (user_id, *post_ids))
                liked_rows = cursor.fetchall()
                liked_post_ids = {row["post_id"] for row in liked_rows}

            for post in posts:
                post["liked"] = post["id"] in liked_post_ids
                try:
                    post["extra_info"] = json.loads(post["extra_info"])
                except (TypeError, json.JSONDecodeError):
                    post["extra_info"] = {}

    return {"posts": posts}

@router.get("/mnetwork/search-community")
def router_search_community(query: str):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM communities WHERE name LIKE %s OR description LIKE %s ORDER BY last_activity DESC LIMIT 50''', (f"%{query}%", f"%{query}%"))
            result = cursor.fetchall()
            return { "communities": result }
        
@router.get("/mnetwork/search-thread")
def router_search_thread(query: str):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM threads WHERE title LIKE %s OR content LIKE %s ORDER BY last_activity DESC LIMIT 50''', (f"%{query}%", f"%{query}%"))
            result = cursor.fetchall()
            return { "threads": result }
        
@router.get("/mnetwork/search-post")
def router_search_post(query: str):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM posts WHERE content LIKE %s ORDER BY timestamp DESC LIMIT 50''', (f"%{query}%",))
            result = cursor.fetchall()
            return { "posts": result }
        
@router.get("/mnetwork/search-users")
def router_search_users(query: str):
    with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT id, username, createdOn FROM users WHERE username LIKE %s ORDER BY createdOn DESC LIMIT 50''', (f"%{query}%",))
            result = cursor.fetchall()
            return { "users": result }
        
@router.get("/mnetwork/featured-communities")
def router_featured_communities():
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM communities WHERE id IN (3, 4, 5, 19) LIMIT 50''')
            result = cursor.fetchall()
            return result
        
@router.get("/mnetwork/my-communities")
def router_my_communities(user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    check_ban(user_id, "MNetwork")
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM communities WHERE author_id = %s LIMIT 50''', (user_id,))
            result = cursor.fetchall()
            return result
        
@router.post("/mnetwork/follow-user")
def router_mnetwork_like_post(payload: follow, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    check_ban(user_id, "MNetwork")
    
    user_info = get_user_information(user_id)
    username = user_info["username"]
    with get_dict_connection("mnetwork") as conn:
        recipient = payload.user
        with conn.cursor() as cursor:
            recipient_info = get_user_information_by_username(recipient)
            if recipient_info:
                recipient_id = recipient_info["id"]
                cursor.execute('''SELECT id FROM user_follows WHERE user_id = %s AND author_id = %s''', (recipient_id, user_id))
                result2 = cursor.fetchone()
                if result2:
                    raise HTTPException(status_code=400, detail="You already followed this user.")
                else:
                    cursor.execute('''INSERT INTO user_follows (user_id, author_id) VALUES (%s, %s)''', (recipient_id, user_id))
                    conn.commit()
                    notify = notification("MNetwork", f"@{username} is now following you.", username, "user_follow")
                    send_notification(recipient_id, notify)
                    return JSONResponse(status_code=200, content={"message": "User followed successfully."})
            else:
                raise HTTPException(status_code=404, detail="The user you attempted to follow was not found.")
        
@router.post("/mnetwork/like-post")
def router_mnetwork_like_post(payload: like, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    check_ban(user_id, "MNetwork")
    
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
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    check_ban(user_id, "MNetwork")
    
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
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    check_ban(user_id, "MNetwork")
    
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
            
@router.post("/mnetwork/unfollow-community")
def router_mnetwork_unfollow_community(payload: like, user_id=Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    check_ban(user_id, "MNetwork")
    
    with get_dict_connection("mnetwork") as conn:
        community = payload.id
        with conn.cursor() as cursor:
            cursor.execute('''SELECT follows FROM communities WHERE id = %s''', (community,))
            result1 = cursor.fetchone()
            if result1:
                cursor.execute('''SELECT id FROM community_follows WHERE community_id = %s AND author_id = %s''', (community, user_id))
                result2 = cursor.fetchone()
                if not result2:
                    raise HTTPException(status_code=400, detail="You are not following this community.")
                else:
                    cursor.execute('''DELETE FROM community_follows WHERE community_id = %s AND author_id = %s''', (community, user_id))
                    cursor.execute('''SELECT COUNT(*) AS cnt FROM community_follows WHERE community_id = %s''', (community,))
                    result3 = cursor.fetchone()
                    likes = result3["cnt"]
                    cursor.execute('''UPDATE communities SET follows = %s WHERE id = %s''', (likes, community))
                    conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Unfollowed successfully."})
            else:
                raise HTTPException(status_code=404, detail="The community you attempted to unfollow was not found.")
            
@router.post("/mnetwork/unlike-post")
def router_mnetwork_unlike_post(payload: like, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    check_ban(user_id, "MNetwork")
    
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
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    check_ban(user_id, "MNetwork")
    
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
            
@router.post("/mnetwork/unfollow-user")
def router_mnetwork_unfollow_user(payload: follow, user_id=Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    check_ban(user_id, "MNetwork")

    with get_dict_connection("mnetwork") as conn:
        recipient = payload.user
        with conn.cursor() as cursor:
            recipient_info = get_user_information_by_username(recipient)
            if recipient_info:
                recipient_id = recipient_info["id"]
                cursor.execute(
                    '''SELECT id FROM user_follows WHERE user_id = %s AND author_id = %s''',
                    (recipient_id, user_id)
                )
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=400, detail="You are not following this user.")
                else:
                    cursor.execute(
                        '''DELETE FROM user_follows WHERE user_id = %s AND author_id = %s''',
                        (recipient_id, user_id)
                    )
                    conn.commit()
                    return JSONResponse(status_code=200, content={"message": "User unfollowed successfully."})
            else:
                raise HTTPException(status_code=404, detail="The user you attempted to unfollow was not found.")
                    
@router.get("/mnetwork/get-feed")
def router_mnetwork_get_feed(user_id=Depends(get_current_user_id)):
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
                    SELECT t.*, c.name AS community_name
                    FROM threads t
                    JOIN communities c ON t.community_id = c.id
                    WHERE t.community_id IN ({format_strings})
                    ORDER BY t.timestamp DESC
                    LIMIT 30
                '''
                cursor.execute(query, tuple(followed_communities))
                threads = cursor.fetchall()
            else:
                query = '''
                    SELECT t.*, c.name AS community_name
                    FROM threads t
                    JOIN communities c ON t.community_id = c.id
                    WHERE t.community_id = 3
                    ORDER BY t.timestamp DESC
                    LIMIT 30
                '''
                cursor.execute(query)
                threads = cursor.fetchall()
            
            for thread in threads:
                try:
                    thread["extra_info"] = json.loads(thread.get("extra_info", "{}"))
                except (TypeError, json.JSONDecodeError):
                    thread["extra_info"] = {}
            
            return {"threads": threads}


@router.post("/mnetwork/transfer-community-ownership")
def transfer_community_ownership(payload: transferCommunityOwnership, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    community_id = payload.community_id
    new_owner = payload.new_owner
    password = payload.password

    check_ban(user_id, "MNetwork")

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

                                    main_cursor.execute("SELECT id, username FROM users WHERE username = %s", (new_owner,))
                                    result_2 = main_cursor.fetchone()
                                    if result_2:
                                        new_owner_id = result_2["id"]
                                        new_owner_username = result_2["username"] # to match database's username since it's not case sensitive

                                        cursor.execute('''SELECT id FROM community_follows WHERE community_id = %s AND author_id = %s''', (community_id, new_owner_id))
                                        result_3 = cursor.fetchone()

                                        if not result_3:
                                            return JSONResponse(status_code=401, content="The new owner should be following this community in order to transfer it.")

                                        cursor.execute("UPDATE communities SET author_id = %s, author_name = %s WHERE id = %s", (new_owner_id, new_owner_username, community_id))
                                        conn.commit()
                                        return {"message": "Ownership successfully transferred."}
                                    else:
                                        return JSONResponse(status_code=404, content="New owner not found. Make sure you wrote their username right.")
                        else:
                            return JSONResponse(status_code=403, content="You need to be the owner of this community to do this action.")
                    else:
                        return JSONResponse(status_code=404, content="Community not found.")
                else:
                    return JSONResponse(status_code=401, content="Login required.")
        except Exception as e:
            conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")

@router.post("/mnetwork/delete-community")
def delete_community(payload: deleteCommunity, user_id=Depends(get_current_user_id)):
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    check_ban(user_id, "MNetwork")

    community_id = payload.community_id
    password = payload.password

    with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            with conn.cursor() as cursor:
                cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (community_id,))
                result = cursor.fetchone()

                if not result:
                    return JSONResponse(status_code=404, content={"detail": "Community not found."})

                author = result["author_id"]

                user_info = get_user_information(user_id)
                if not user_info:
                    return JSONResponse(status_code=404, content={"detail": "User not found."})
                
                trust = user_info["trust"]
                if not trust:
                    trust = 0

                if author != user_id:
                    if trust < 10:
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
                cursor.execute("DELETE FROM threads WHERE community_id = %s", (community_id,))
                conn.commit()

                return {"message": "Community successfully deleted."}

        except Exception as e:
            conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")
        
def get_thread_and_check_permission(thread_id, user_id, conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT author_id, community_id FROM threads WHERE id = %s LIMIT 1", (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found.")

        cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (thread["community_id"],))
        community = cursor.fetchone()
        if not community:
            raise HTTPException(status_code=404, detail="Community not found.")

        if thread["author_id"] != user_id and community["author_id"] != user_id:
            with get_dict_connection("main") as conn_2:
                with conn_2.cursor() as cursor:
                    cursor.execute("SELECT trust FROM users WHERE id = %s", (user_id,))
                    result = cursor.fetchone()
                    if not result:
                        raise HTTPException(status_code=404, detail="User not found.")
                    trust = result.get("trust")

                    # this so admins can do this.

                    if not trust or trust < 10:
                        raise HTTPException(
                            status_code=403,
                            detail="You must be the author of this thread or owner of community to perform this action."
                        )

        return thread
    
def get_thread_community_and_check_permission(thread_id, user_id, conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT community_id FROM threads WHERE id = %s LIMIT 1", (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found.")

        cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (thread["community_id"],))
        community = cursor.fetchone()
        if not community:
            raise HTTPException(status_code=404, detail="Community not found.")

        if community["author_id"] != user_id:
            with get_dict_connection("main") as conn_2:
                with conn_2.cursor() as cursor:
                    cursor.execute("SELECT trust FROM users WHERE id = %s", (user_id,))
                    result = cursor.fetchone()
                    if not result:
                        raise HTTPException(status_code=404, detail="User not found.")
                    trust = result.get("trust")

                    # this so admins can do this.

                    if not trust or trust < 10:
                        raise HTTPException(
                            status_code=403,
                            detail="You must be the author of this thread or owner of community to perform this action."
                        )

        return thread

@router.post("/mnetwork/delete-thread")
def delete_thread(payload: threadOperation, user_id=Depends(get_current_user_id)):
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    check_ban(user_id, "MNetwork")

    thread_id = payload.thread_id
    with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            thread = get_thread_and_check_permission(thread_id, user_id, conn)

            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM posts WHERE thread_id = %s", (thread_id,))
                cursor.execute("DELETE FROM threads WHERE id = %s", (thread_id,))
                conn.commit()

            return {"message": "Thread successfully deleted."}

        except HTTPException as he:
            raise he
        except Exception as e:
            conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")

@router.post("/mnetwork/lock-thread")
def lock_thread(payload: threadOperation, user_id=Depends(get_current_user_id)):
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    check_ban(user_id, "MNetwork")

    thread_id = payload.thread_id
    with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            thread = get_thread_and_check_permission(thread_id, user_id, conn)

            with conn.cursor() as cursor:
                cursor.execute("UPDATE threads SET locked = 1 WHERE id = %s", (thread_id,))
                conn.commit()

            return {"message": "Thread successfully locked."}

        except HTTPException as he:
            raise he
        except Exception as e:
            conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")

@router.post("/mnetwork/unlock-thread")
def unlock_thread(payload: threadOperation, user_id=Depends(get_current_user_id)):
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    check_ban(user_id, "MNetwork")

    thread_id = payload.thread_id
    with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            thread = get_thread_and_check_permission(thread_id, user_id, conn)

            with conn.cursor() as cursor:
                cursor.execute("UPDATE threads SET locked = 0 WHERE id = %s", (thread_id,))
                conn.commit()

            return {"message": "Thread successfully unlocked."}

        except HTTPException as he:
            raise he
        except Exception as e:
            conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")
        
@router.post("/mnetwork/delete-post")
def delete_post(payload: deletePost, user_id=Depends(get_current_user_id)):
    post_id = payload.id

    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    check_ban(user_id, "MNetwork")

    with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            with conn.cursor() as cursor:
                cursor.execute("SELECT author_id, thread_id FROM posts WHERE id = %s LIMIT 1", (post_id,))
                result = cursor.fetchone()

                if not result:
                    return JSONResponse(status_code=404, content={"detail": "Post not found."})

                post_author = result["author_id"]
                thread_id = result["thread_id"]

                user_info = get_user_information(user_id)
                if not user_info:
                    return JSONResponse(status_code=404, content={"detail": "User not found."})
                
                trust = int(user_info.get("trust", 0))

                if post_author != user_id:
                    # most scuffed way of getting the community id bruh i cant remember how to use JOIN
                    
                    community_author = None
                    cursor.execute("SELECT community_id FROM threads WHERE id = %s LIMIT 1", (thread_id,))
                    result_1 = cursor.fetchone()
                    if result_1:
                        community_id = result_1["community_id"]
                        cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (community_id,))
                        result_2 = cursor.fetchone()
                        community_author = result_2["author_id"]

                    if community_author != user_id:
                        # we also want admins to be able to delete posts
                        if trust < 10:
                            return JSONResponse(status_code=403, content={"detail": "You must be the author of this post or the owner of the community to delete it."})
            

                cursor.execute("DELETE FROM posts WHERE id = %s", (post_id,))
                conn.commit()

                return {"message": "Post successfully deleted."}

        except Exception as e:
            conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")
        
@router.get("/mnetwork/get-user-communities")
def get_user_communities(user: str):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM communities WHERE author_name = %s ORDER BY timestamp DESC LIMIT 50", (user,))
            result = cursor.fetchall()

            return {"communities": result}
        
@router.get("/mnetwork/get-user-threads")
def get_user_communities(user: str):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM threads WHERE author_name = %s ORDER BY timestamp DESC LIMIT 50", (user,))
            result = cursor.fetchall()

            return {"threads": result}
        
@router.get("/mnetwork/get-user-posts")
def get_user_communities(user: str):
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM posts WHERE author_name = %s ORDER BY timestamp DESC LIMIT 50", (user,))
            result = cursor.fetchall()

            return {"posts": result}
        
@router.get("/mnetwork/get-user-followers")
def get_user_communities(user: str):
    user_information = get_user_information_by_username(user)
    if not user_information:
        raise HTTPException(status_code=404, detail="User not found.")
    user_id = user_information["id"]
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_follows WHERE user_id = %s ORDER BY timestamp DESC LIMIT 50", (user_id,))
            result = cursor.fetchall()

            return {"followers": result}
        
@router.get("/mnetwork/get-user-following")
def get_user_communities(user: str):
    user_information = get_user_information_by_username(user)
    if not user_information:
        raise HTTPException(status_code=404, detail="User not found.")
    user_id = user_information["id"]
    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_follows WHERE author_id = %s ORDER BY timestamp DESC LIMIT 50", (user_id,))
            result = cursor.fetchall()

            return {"following": result}
        
@router.get("/mnetwork/get-followed-communities")
def get_followed_communities(user_id=Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    check_ban(user_id, "MNetwork")

    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT cf.community_id, c.name, cf.timestamp
                FROM community_follows cf
                JOIN communities c ON cf.community_id = c.id
                WHERE cf.author_id = %s
                ORDER BY cf.timestamp DESC
                LIMIT 50
            ''', (user_id,))
            result = cursor.fetchall()

            return {"following": result}
        
@router.get("/mnetwork/get-user-profile")
def get_user_profile(user: str, author_id=Depends(get_current_user_id)):
    user_information = get_user_information_by_username(user)
    if not user_information:
        raise HTTPException(status_code=404, detail="User not found.")

    user_id = user_information["id"]

    # just in case
    result1 = None
    result2 = None
    result3 = None
    follower_count = 0

    with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username, biography, createdOn FROM users WHERE id = %s", (user_id,))
            result1 = cursor.fetchone()
            if not result1:
                raise HTTPException(status_code=404, detail="User not found.")

    following = False
    username_color = get_setting(user_id, "Username color")

    badges = get_setting(user_id, "Badges")
    if badges:
        try:
            badges = json.loads(badges)
        except json.JSONDecodeError:
            badges = []
    else:
        badges = []


    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT COUNT(*) AS cnt FROM user_follows WHERE user_id = %s''', (user_id,))
            result2 = cursor.fetchone()
            follower_count = result2["cnt"]

            if author_id:
                cursor.execute("SELECT id FROM user_follows WHERE author_id = %s AND user_id = %s", (author_id, user_id))
                result3 = cursor.fetchone()
                if result3:
                    following = True

    return { "profile": result1, "following": following, "follower_count": follower_count, "username_color": username_color, "badges": badges }
        
@router.post("/mnetwork/update-community-name")
def router_update_community_name(payload: editCommunity, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    check_ban(user_id, "MNetwork")

    community_id = payload.community_id
    value = payload.value

    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT author_id FROM communities WHERE id = %s", (community_id,))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Community not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the community to do this operation.")
            
            user_info = get_user_information(user_id)

            premium = user_info["premium"]
            username_color = "#808080"
            if premium == 1:
                username_color = get_setting(user_id, "Username color")

            username = user_info["username"]
            extra_information = { "Username color": username_color }
            
            cursor.execute("UPDATE communities SET name = %s WHERE id = %s", (value, community_id))
            conn.commit()
            return { "message": "Name updated successfully" }
        
@router.post("/mnetwork/update-community-description")
def router_update_community_description(payload: editCommunity, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    check_ban(user_id, "MNetwork")

    community_id = payload.community_id
    value = payload.value

    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT author_id FROM communities WHERE id = %s", (community_id,))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Community not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the community to do this operation.")
            
            cursor.execute("UPDATE communities SET description = %s WHERE id = %s", (value, community_id))
            conn.commit()
            return { "message": "Description updated successfully" }
        
@router.post("/mnetwork/update-thread-title")
def router_update_thread_title(payload: editThread, user_id = Depends(get_current_user_id)):
    thread_id = payload.thread_id
    value = payload.value

    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    check_ban(user_id, "MNetwork")

    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT author_id FROM threads WHERE id = %s", (thread_id,))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Thread not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the thread to do this operation.")
            
            user_info = get_user_information(user_id)
            premium = user_info["premium"]
            username_color = "#808080"
            if premium == 1:
                username_color = get_setting(user_id, "Username color")

            extra_information = { "Username color": username_color }
            
            cursor.execute("UPDATE threads SET title = %s, extra_info = %s WHERE id = %s", (value, extra_information, thread_id))
            conn.commit()
            return { "message": "Title updated successfully" }
        
@router.post("/mnetwork/update-thread-description")
def router_update_thread_description(payload: editThread, user_id = Depends(get_current_user_id)):
    thread_id = payload.thread_id
    value = payload.value

    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    check_ban(user_id, "MNetwork")

    with get_dict_connection("mnetwork") as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT author_id FROM threads WHERE id = %s", (thread_id,))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Thread not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the thread to do this operation.")
            
            cursor.execute("UPDATE threads SET content = %s WHERE id = %s", (value, thread_id))
            conn.commit()
            return { "message": "Description updated successfully" }
        
@router.post("/mnetwork/pin-thread")
def router_pin_thread(thread_id: int, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    check_ban(user_id, "MNetwork")

    with get_dict_connection("mnetwork") as conn:
        conn.autocommit = False
        thread = get_thread_community_and_check_permission(thread_id, user_id, conn)

        with conn.cursor() as cursor:
            cursor.execute("UPDATE threads SET pinned = 1 WHERE id = %s", (thread_id,))
            conn.commit()

            return { "message": "Thread pinned successfully" }
        
@router.post("/mnetwork/unpin-thread")
def router_pin_thread(thread_id: int, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    check_ban(user_id, "MNetwork")

    with get_dict_connection("mnetwork") as conn:
        conn.autocommit = False
        thread = get_thread_community_and_check_permission(thread_id, user_id, conn)

        with conn.cursor() as cursor:
            cursor.execute("UPDATE threads SET pinned = 0 WHERE id = %s", (thread_id,))
            conn.commit()
            
            return { "message": "Thread un-pinned successfully" }
        
@router.post("/mnetwork/change-username-color")
def router_change_username_color(payload: field_1, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    value = payload.value
    
    check_ban(user_id, "MNetwork")
    user_info = get_user_information(user_id)

    if user_info["premium"] == 0:
        raise HTTPException(status_code=402, detail="You need a premium account to do this operation.")
    if not re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value):
        raise HTTPException(status_code=400, detail="Invalid HEX code for color. Must be this format: #000000 or #FFF")
    
    set_setting(user_id, "Username color", value)

@router.post("/mnetwork/claim-vip")
def router_claim_vip(request: Request, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    client_ip = (
        request.headers.get("x-real-ip")
        or request.headers.get("X-Forwarded-For")
        or request.client.host
    )

    stored_ip = hash_ip(client_ip)
    
    with get_dict_connection("main") as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET ip_address = %s WHERE id = %s", (stored_ip, user_id))
            
            client_info = get_user_information(user_id, conn)
            client_email = client_info["email"]
            client_username = client_info["username"]
            client_premium = client_info["premium"]

            if client_premium == 1:
                raise HTTPException(status_code=400, detail="You already have claimed this!")

            cursor.execute("SELECT email, ip_address FROM users WHERE invited_by = %s", (client_username,))
            invited_users = cursor.fetchall()

            valid_count = 0
            seen_emails = set()
            seen_ips = set()

            for email, ip in invited_users:
                if (
                    email != client_email and 
                    ip != stored_ip and 
                    email not in seen_emails and 
                    ip not in seen_ips
                ):
                    valid_count += 1
                    seen_emails.add(email)
                    seen_ips.add(ip)

            if valid_count >= 3:
                cursor.execute("UPDATE users SET premium = 1 WHERE id = %s", (user_id,))
                add_badge(user_id, "vip")
                conn.commit()
                return { "status": "Congratulations! You now have the VIP pass. Enjoy :)" }
            else:
                conn.commit()
                return { "message": "Sorry, but you do not have enough invites. Valid invites (creating accounts yourself does not count as valid invite): " +  str(valid_count) }
