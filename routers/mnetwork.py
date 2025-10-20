from fastapi import APIRouter, Body, Depends, HTTPException, Response, Cookie, UploadFile, File, UploadFile, Form, Request
from fastapi.responses import JSONResponse
from models import mnetwork_create_community, mnetwork_create_thread, mnetwork_create_post, editCommunity, editThread, threadOperation, like, follow, transferCommunityOwnership, deleteCommunity, updateCommunitySettings, deletePost, field_1
from auth import get_current_user_id, check_password, hash_ip
from db import get_connection, get_dict_connection
from utils import get_user_information, get_user_information_by_username, send_notification, notification, check_ban, set_setting, get_setting, add_badge, rate_limiter, rate_limiter_guest_ip, get_guest_info
from typing import Optional
from config import IMAGE_UPLOAD_FOLDER
from PIL import Image
import re, os, io, json, asyncio

MAX_UPLOAD_SIZE = 1024 * 1024 * 5
ALLOWED_IMAGE_TYPES = {"jpeg", "png", "gif"}

router = APIRouter()
noAccMsg = "You need to login with a Maltion account to do this action."


async def process_image(image_bytes: bytes, output_path: str, max_size: int = 2000):
    def _process():
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.ANTIALIAS)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, format="JPEG", quality=80, optimize=True)

    await asyncio.to_thread(_process)

async def get_thread_and_check_permission(thread_id, user_id, conn):
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT author_id, community_id FROM threads WHERE id = %s LIMIT 1", (thread_id,))
        thread = await cursor.fetchone()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found.")

        await cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (thread["community_id"],))
        community = await cursor.fetchone()
        if not community:
            raise HTTPException(status_code=404, detail="Community not found.")

        if thread["author_id"] != user_id and community["author_id"] != user_id:
            async with get_dict_connection("main") as conn_2:
                async with conn_2.cursor() as cursor:
                    await cursor.execute("SELECT trust FROM users WHERE id = %s", (user_id,))
                    result = await cursor.fetchone()
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
    
async def get_thread_community_and_check_permission(thread_id, user_id, conn):
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT community_id FROM threads WHERE id = %s LIMIT 1", (thread_id,))
        thread = await cursor.fetchone()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found.")

        await cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (thread["community_id"],))
        community = await cursor.fetchone()
        if not community:
            raise HTTPException(status_code=404, detail="Community not found.")

        if community["author_id"] != user_id:
            async with get_dict_connection("main") as conn_2:
                async with conn_2.cursor() as cursor:
                    await cursor.execute("SELECT trust FROM users WHERE id = %s", (user_id,))
                    result = await cursor.fetchone()
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


@router.post("/mnetwork/create-community")
async def router_create_community(payload: mnetwork_create_community, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail=noAccMsg)
    
    await check_ban(user_id, "MNetwork")

    if await rate_limiter(user_id) is False:
        raise HTTPException(status_code=429, detail="Slow down!")
    
    name = payload.name
    description = payload.description

    async with get_connection("mnetwork") as conn:
        user_info = await get_user_information(user_id)
               
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        username = user_info.get("username")
        premium = user_info["premium"]
        username_color = "#808080"
        if premium == 1:
            username_color = await get_setting(user_id, "Username color")
        
        username = user_info["username"]
        extra_information = { "Username color": username_color }
        extra_info = json.dumps(extra_information)

        async with conn.cursor() as cursor:
            await cursor.execute('''INSERT INTO communities (author_id, author_name, name, description, locked, extra_info) VALUES (%s, %s, %s, %s, 0, %s)''', (user_id, username, name, description, extra_info))
            await conn.commit()
        return JSONResponse(status_code=201, content={"message": "Community created successfully."})
    
@router.post("/mnetwork/create-thread")
async def router_create_thread(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    community_id: int = Form(...),
    image: Optional[UploadFile] = File(None),
    user_id: int = Depends(get_current_user_id)
):
    client_ip = (request.headers.get("x-real-ip") or request.headers.get("X-Forwarded-For") or request.client.host)

    if user_id:
        await check_ban(user_id, "MNetwork")

        if await rate_limiter(user_id) is False:
            raise HTTPException(status_code=429, detail="Slow down!")
    else:
        user_id = 0

        if await rate_limiter_guest_ip(client_ip) is False:
            raise HTTPException(status_code=429, detail="Guests can only post once every 60 seconds. Please try again later (or log in).")
    
    async with get_dict_connection("mnetwork") as conn:
        user_info = await get_user_information(user_id)
        username = None
        premium = None
        try:
            username = user_info.get("username")
            premium = user_info.get("premium", 0)
        except Exception:
            username = "Guest"
            premium = 0

        username_color = "#808080"
        if premium == 1 and user_info:
            username_color = await get_setting(user_id, "Username color")

        if not user_info:
            guest_info = await get_guest_info(client_ip)
            if not guest_info:
                raise HTTPException(status_code=400, detail="Choose a guest nickname first.")
            username = f"{guest_info[1]} (Guest #{guest_info[0]})"
            

        extra_info = json.dumps({"Username color": username_color})

        async with conn.cursor() as cursor:
            # Validate community
            await cursor.execute("SELECT locked, can_add, id FROM communities WHERE id = %s", (community_id,))
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="The community you tried to post this thread in was not found.")
            if result["locked"] == 1:
                raise HTTPException(status_code=401, detail="This community is locked.")
            if result["can_add"] == 0:
                raise HTTPException(status_code=401, detail="This community doesn't allow the creation of threads.")

            comm_id = result["id"]

            await cursor.execute(
                """INSERT INTO threads 
                   (community_id, author_id, author_name, title, content, locked, extra_info, has_image)
                   VALUES (%s, %s, %s, %s, %s, 0, %s, %s)
                   RETURNING id""",
                (community_id, user_id, username, title, content, extra_info, 1 if image else 0)
            )
            thread_id = (await cursor.fetchone())["id"]

            if image:
                if user_id == 0:
                    raise HTTPException(status_code=401, detail="You need to log in with a Maltion account to upload images.")

                image_bytes = await image.read()
                if len(image_bytes) > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="Image exceeds 5 MB limit.")
                file_location = f"{IMAGE_UPLOAD_FOLDER}/thread_{thread_id}.jpg"
                await process_image(image_bytes, file_location)

            await cursor.execute(
                "UPDATE communities SET activity_detail = %s, last_activity = NOW() WHERE id = %s",
                (f"{username} created a new thread: {title}", comm_id)
            )
            await conn.commit()
    
    return JSONResponse(status_code=201, content={"message": "Thread created successfully."})

@router.post("/mnetwork/create-post")
async def router_create_post(
    request: Request,
    content: str = Form(...),
    thread_id: int = Form(...),
    parent_post_id: int = Form(...),
    image: Optional[UploadFile] = File(None),
    user_id: int = Depends(get_current_user_id),
):
    client_ip = (request.headers.get("x-real-ip") or request.headers.get("X-Forwarded-For") or request.client.host)

    if user_id:    
        await check_ban(user_id, "MNetwork")

        if await rate_limiter(user_id) is False:
            raise HTTPException(status_code=429, detail="Slow down!")
    else:
        user_id = 0

        if await rate_limiter_guest_ip(client_ip) is False:
            raise HTTPException(status_code=429, detail="Guests can only post once every 60 seconds. Please try again later (or log in).")

    async with get_dict_connection("mnetwork") as conn:
        user_info = await get_user_information(user_id)
        username = None
        premium = None
        try:
            username = user_info.get("username")
            premium = user_info.get("premium", 0)
        except Exception:
            username = "Guest"
            premium = 0

        username_color = "#808080"
        if premium == 1 and user_info:
            username_color = await get_setting(user_id, "Username color")

        if not user_info:
            guest_info = await get_guest_info(client_ip)
            if not guest_info:
                raise HTTPException(status_code=400, detail="Choose a guest nickname first.")
            username = f"{guest_info[1]} (Guest #{guest_info[0]})"

        extra_info = json.dumps({"Username color": username_color})

        async with conn.cursor() as cursor:
            await cursor.execute("SELECT locked, community_id, title FROM threads WHERE id = %s", (thread_id,))
            thread = await cursor.fetchone()
            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found.")
            if thread["locked"] == 1:
                raise HTTPException(status_code=401, detail="This thread is locked.")
            
            community_id = thread["community_id"]
            thread_title = thread["title"]

            await cursor.execute("SELECT locked, name FROM communities WHERE id = %s", (community_id,))
            community = await cursor.fetchone()
            if not community:
                raise HTTPException(status_code=404, detail="Community not found.")
            if community["locked"] == 1:
                raise HTTPException(status_code=401, detail="This community is locked.")
            community_name = community["name"]

            if parent_post_id > 0:
                await cursor.execute("SELECT parent_post_id FROM posts WHERE id = %s", (parent_post_id,))
                parent = await cursor.fetchone()
                if not parent:
                    raise HTTPException(status_code=404, detail="Parent post not found.")
                if parent["parent_post_id"] > 0:
                    raise HTTPException(status_code=400, detail="Cannot reply to nested post.")

            await cursor.execute(
                """INSERT INTO posts 
                   (thread_id, author_id, author_name, content, has_image, parent_post_id, extra_info)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (thread_id, user_id, username, content, 1 if image else 0, parent_post_id, extra_info)
            )
            post_id = (await cursor.fetchone())["id"]

            await cursor.execute("UPDATE threads SET activity_detail = %s, last_activity = NOW() WHERE id = %s",
                                 (f"{username} added a post.", thread_id))
            await cursor.execute("UPDATE communities SET activity_detail = %s, last_activity = NOW() WHERE id = %s",
                                 (f"{username} posted in thread: {thread_title}", community_id))

            if image:
                if user_id == 0:
                    raise HTTPException(status_code=401, detail="You need to log in with a Maltion account to upload images.")
                image_bytes = await image.read()
                if len(image_bytes) > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="Image exceeds 5 MB limit.")
                file_location = f"{IMAGE_UPLOAD_FOLDER}/{post_id}.jpg"
                await process_image(image_bytes, file_location)

            mentions = set(re.findall(r"(?<!\w)@([A-Za-z0-9_.-]+)(?=\s|$|[.,!?:])", content))
            was_everyone_mentioned = False
            for recipient in mentions:
                if recipient == username:
                    continue

                if recipient == "everyone" and not was_everyone_mentioned:
                    if user_id == 0:
                        raise HTTPException(status_code=401, detail="You need to log in with a Maltion account to mention everyone.")
                    was_everyone_mentioned = True
                    await cursor.execute("SELECT author_id FROM community_follows WHERE community_id = %s", (community_id,))
                    followers = await cursor.fetchall()
                    for f in followers:
                        notify = notification("MNetwork", f"@{username} mentioned everyone in {thread_title} of {community_name}", thread_id, "post_mention")
                        await send_notification(f["author_id"], notify)
                else:
                    recipient_data = await get_user_information_by_username(recipient)
                    if recipient_data:
                        notify = notification("MNetwork", f"@{username} mentioned you in {thread_title} of {community_name}", thread_id, "post_mention")
                        await send_notification(recipient_data["id"], notify)

            await conn.commit()

    return JSONResponse(status_code=201, content={"message": "Post created successfully."})

    
@router.get("/mnetwork/get-community")
async def router_get_community(community: int, user_id = Depends(get_current_user_id)):
    liked = False
    await check_ban(user_id, "MNetwork")
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT author_id, author_name, name, description, locked, can_add, timestamp, last_activity, follows FROM communities WHERE id = %s LIMIT 1''', (community,))
            result1 = await cursor.fetchone()
            if result1:
                if user_id:
                    # return if user is following this community
                    await cursor.execute('''SELECT id FROM community_follows WHERE community_id = %s AND author_id = %s LIMIT 1''', (community, user_id))
                    result2 = await cursor.fetchone()

                    liked = bool(result2)
            else:
                raise HTTPException(status_code=404, detail="Community not found.")
            
            locked = result1["locked"]
            can_add = result1["can_add"]
            settings = { "locked": locked, "can_add": can_add }

    return {"community": result1, "liked": liked, "settings": settings }

@router.post("/mnetwork/update-community-settings")
async def router_update_community_settings(payload: updateCommunitySettings, user_id = Depends(get_current_user_id)):
    community_id = payload.community_id
    locked = payload.locked
    can_add = payload.can_add
    await check_ban(user_id, "MNetwork")

    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT author_id FROM communities WHERE id = %s", (community_id,))
            result = await cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Community not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the community to do this operation.")
            
            await cursor.execute("UPDATE communities SET locked = %s, can_add = %s WHERE id = %s", (locked, can_add, community_id))
            await conn.commit()
            return { "message": "Settings updated successfully" }
    
@router.get("/mnetwork/get-thread")
async def router_get_thread(thread: int, user_id = Depends(get_current_user_id)):
    liked = False
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('SELECT * FROM threads WHERE id = %s LIMIT 1', (thread,))
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Thread not found.")

            try:
                result["extra_info"] = json.loads(result.get("extra_info", "{}"))
            except (TypeError, json.JSONDecodeError):
                result["extra_info"] = {}

            community_id = result["community_id"]
            await cursor.execute('SELECT * FROM communities WHERE id = %s LIMIT 1', (community_id,))
            community_result = await cursor.fetchone()

            if user_id:
                await cursor.execute(
                    'SELECT id FROM thread_likes WHERE thread_id = %s AND author_id = %s LIMIT 1',
                    (thread, user_id)
                )
                follow_result = await cursor.fetchone()
                liked = bool(follow_result)

    return {
        "thread": result,
        "community": community_result,
        "liked": liked
    }

@router.get("/mnetwork/get-community-threads")
async def router_get_community_threads(community: int):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM threads WHERE community_id = %s AND pinned = 0 LIMIT 50''', (community,))
            result = await cursor.fetchall()

            await cursor.execute('''SELECT * FROM threads WHERE community_id = %s AND pinned = 1 LIMIT 50''', (community,))
            pinned = await cursor.fetchall()
            return { "threads": result, "pinned": pinned }

@router.get("/mnetwork/get-thread-posts")
async def router_get_thread_posts(thread: int, user_id = Depends(get_current_user_id)):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM posts WHERE thread_id = %s ORDER BY timestamp DESC LIMIT 50''', (thread,))
            posts = await cursor.fetchall()

            liked_post_ids = set()
            if user_id and posts:
                post_ids = [post["id"] for post in posts]

                placeholders = ','.join(['%s'] * len(post_ids))
                query = f'''SELECT post_id FROM post_likes WHERE author_id = %s AND post_id IN ({placeholders})'''

                await cursor.execute(query, (user_id, *post_ids))
                liked_rows = await cursor.fetchall()
                liked_post_ids = {row["post_id"] for row in liked_rows}

            for post in posts:
                post["liked"] = post["id"] in liked_post_ids
                try:
                    post["extra_info"] = json.loads(post["extra_info"])
                except (TypeError, json.JSONDecodeError):
                    post["extra_info"] = {}

    return {"posts": posts}

@router.get("/mnetwork/get-community-posts")
async def router_get_community_posts(community: int, user_id=Depends(get_current_user_id)):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''
                SELECT p.* 
                FROM posts p
                JOIN threads t ON p.thread_id = t.id
                WHERE t.community_id = %s
                ORDER BY p.timestamp DESC
                LIMIT 10
            ''', (community,))
            
            posts = await cursor.fetchall()

            liked_post_ids = set()
            if user_id and posts:
                post_ids = [post["id"] for post in posts]
                placeholders = ','.join(['%s'] * len(post_ids))
                query = f'''SELECT post_id FROM post_likes WHERE author_id = %s AND post_id IN ({placeholders})'''
                await cursor.execute(query, (user_id, *post_ids))
                liked_rows = await cursor.fetchall()
                liked_post_ids = {row["post_id"] for row in liked_rows}

            for post in posts:
                post["liked"] = post["id"] in liked_post_ids
                try:
                    post["extra_info"] = json.loads(post["extra_info"])
                except (TypeError, json.JSONDecodeError):
                    post["extra_info"] = {}

    return {"posts": posts}


@router.get("/mnetwork/search-community")
async def router_search_community(query: str):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM communities WHERE name LIKE %s OR description LIKE %s ORDER BY last_activity DESC LIMIT 50''', (f"%{query}%", f"%{query}%"))
            result = await cursor.fetchall()
            return { "communities": result }
        
@router.get("/mnetwork/search-thread")
async def router_search_thread(query: str):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM threads WHERE title LIKE %s OR content LIKE %s ORDER BY last_activity DESC LIMIT 50''', (f"%{query}%", f"%{query}%"))
            result = await cursor.fetchall()
            return { "threads": result }
        
@router.get("/mnetwork/search-post")
async def router_search_post(query: str):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM posts WHERE content LIKE %s ORDER BY timestamp DESC LIMIT 50''', (f"%{query}%",))
            result = await cursor.fetchall()
            return { "posts": result }
        
@router.get("/mnetwork/search-users")
async def router_search_users(query: str):
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT id, username, createdOn FROM users WHERE username LIKE %s ORDER BY createdOn DESC LIMIT 50''', (f"%{query}%",))
            result = await cursor.fetchall()
            return { "users": result }
        
@router.get("/mnetwork/featured-communities")
async def router_featured_communities():
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM communities WHERE id IN (3, 4, 5, 19, 27) LIMIT 50''')
            result = await cursor.fetchall()
            return result
        
@router.get("/mnetwork/my-communities")
async def router_my_communities(user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    await check_ban(user_id, "MNetwork")
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM communities WHERE author_id = %s LIMIT 50''', (user_id,))
            result = await cursor.fetchall()
            return result
        
@router.post("/mnetwork/follow-user")
async def router_mnetwork_like_post(payload: follow, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    await check_ban(user_id, "MNetwork")
    
    user_info = await get_user_information(user_id)
    username = user_info["username"]
    async with get_dict_connection("mnetwork") as conn:
        recipient = payload.user
        async with conn.cursor() as cursor:
            recipient_info = await get_user_information_by_username(recipient)
            if recipient_info:
                recipient_id = recipient_info["id"]
                await cursor.execute('''SELECT id FROM user_follows WHERE user_id = %s AND author_id = %s''', (recipient_id, user_id))
                result2 = await cursor.fetchone()
                if result2:
                    raise HTTPException(status_code=400, detail="You already followed this user.")
                else:
                    await cursor.execute('''INSERT INTO user_follows (user_id, author_id) VALUES (%s, %s)''', (recipient_id, user_id))
                    await conn.commit()
                    notify = notification("MNetwork", f"@{username} is now following you.", username, "user_follow")
                    await send_notification(recipient_id, notify)
                    return JSONResponse(status_code=200, content={"message": "User followed successfully."})
            else:
                raise HTTPException(status_code=404, detail="The user you attempted to follow was not found.")
        
@router.post("/mnetwork/like-post")
async def router_mnetwork_like_post(payload: like, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    await check_ban(user_id, "MNetwork")
    
    async with get_dict_connection("mnetwork") as conn:
        post = payload.id
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT likes FROM posts WHERE id = %s''', (post,))
            result1 = await cursor.fetchone()
            if result1:
                await cursor.execute('''SELECT id FROM post_likes WHERE post_id = %s AND author_id = %s''', (post, user_id))
                result2 = await cursor.fetchone()
                if result2:
                    raise HTTPException(status_code=400, detail="You already liked this post.")
                else:
                    await cursor.execute('''INSERT INTO post_likes (post_id, author_id) VALUES (%s, %s)''', (post, user_id))
                    await cursor.execute('''SELECT COUNT(*) AS cnt FROM post_likes WHERE post_id = %s''', (post,))
                    result3 = await cursor.fetchone()
                    likes = result3["cnt"]
                    await cursor.execute('''UPDATE posts SET likes = %s WHERE id = %s''', (likes, post))
                    await conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like added successfully."})
            else:
                raise HTTPException(status_code=404, detail="The post you attempted to like was not found.")
            
@router.post("/mnetwork/like-thread")
async def router_mnetwork_like_thread(payload: like, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    await check_ban(user_id, "MNetwork")
    
    async with get_dict_connection("mnetwork") as conn:
        thread = payload.id
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT likes FROM threads WHERE id = %s''', (thread,))
            result1 = await cursor.fetchone()
            if result1:
                await cursor.execute('''SELECT id FROM thread_likes WHERE thread_id = %s AND author_id = %s''', (thread, user_id))
                result2 = await cursor.fetchone()
                if result2:
                    raise HTTPException(status_code=400, detail="You already liked this thread.")
                else:
                    await cursor.execute('''INSERT INTO thread_likes (thread_id, author_id) VALUES (%s, %s)''', (thread, user_id))
                    await cursor.execute('''SELECT COUNT(*) AS cnt FROM thread_likes WHERE thread_id = %s''', (thread,))
                    result3 = await cursor.fetchone()
                    likes = result3["cnt"]
                    await cursor.execute('''UPDATE threads SET likes = %s WHERE id = %s''', (likes, thread))
                    await conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like added successfully."})
            else:
                raise HTTPException(status_code=404, detail="The thread you attempted to like was not found.")
            
@router.post("/mnetwork/follow-community")
async def router_mnetwork_follow_community(payload: like, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    await check_ban(user_id, "MNetwork")
    
    async with get_dict_connection("mnetwork") as conn:
        community = payload.id
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT follows FROM communities WHERE id = %s''', (community,))
            result1 = await cursor.fetchone()
            if result1:
                await cursor.execute('''SELECT id FROM community_follows WHERE community_id = %s AND author_id = %s''', (community, user_id))
                result2 = await cursor.fetchone()
                if result2:
                    raise HTTPException(status_code=400, detail="You already liked this community.")
                else:
                    await cursor.execute('''INSERT INTO community_follows (community_id, author_id) VALUES (%s, %s)''', (community, user_id))
                    await cursor.execute('''SELECT COUNT(*) AS cnt FROM community_follows WHERE community_id = %s''', (community,))
                    result3 = await cursor.fetchone()
                    likes = result3["cnt"]
                    await cursor.execute('''UPDATE communities SET follows = %s WHERE id = %s''', (likes, community))
                    await conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Follow added successfully."})
            else:
                raise HTTPException(status_code=404, detail="The community you attempted to follow was not found.")
            
@router.post("/mnetwork/unfollow-community")
async def router_mnetwork_unfollow_community(payload: like, user_id=Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    await check_ban(user_id, "MNetwork")
    
    async with get_dict_connection("mnetwork") as conn:
        community = payload.id
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT follows FROM communities WHERE id = %s''', (community,))
            result1 = await cursor.fetchone()
            if result1:
                await cursor.execute('''SELECT id FROM community_follows WHERE community_id = %s AND author_id = %s''', (community, user_id))
                result2 = await cursor.fetchone()
                if not result2:
                    raise HTTPException(status_code=400, detail="You are not following this community.")
                else:
                    await cursor.execute('''DELETE FROM community_follows WHERE community_id = %s AND author_id = %s''', (community, user_id))
                    await cursor.execute('''SELECT COUNT(*) AS cnt FROM community_follows WHERE community_id = %s''', (community,))
                    result3 = await cursor.fetchone()
                    likes = result3["cnt"]
                    await cursor.execute('''UPDATE communities SET follows = %s WHERE id = %s''', (likes, community))
                    await conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Unfollowed successfully."})
            else:
                raise HTTPException(status_code=404, detail="The community you attempted to unfollow was not found.")
            
@router.post("/mnetwork/unlike-post")
async def router_mnetwork_unlike_post(payload: like, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    await check_ban(user_id, "MNetwork")
    
    async with get_dict_connection("mnetwork") as conn:
        post = payload.id
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT likes FROM posts WHERE id = %s''', (post,))
            result1 = await cursor.fetchone()
            if result1:
                await cursor.execute('''SELECT id FROM post_likes WHERE post_id = %s AND author_id = %s''', (post, user_id))
                result2 = await cursor.fetchone()
                if result2:
                    await cursor.execute('''DELETE FROM post_likes WHERE post_id = %s AND author_id = %s''', (post, user_id))
                    await cursor.execute('''SELECT COUNT(*) AS cnt FROM post_likes WHERE post_id = %s''', (post,))
                    result3 = await cursor.fetchone()
                    likes = result3["cnt"]
                    await cursor.execute('''UPDATE posts SET likes = %s WHERE id = %s''', (likes, post))
                    await conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like removed successfully."})
                else:
                    raise HTTPException(status_code=400, detail="You didn't like this post yet.")
            else:
                raise HTTPException(status_code=404, detail="The post you attempted to remove your like from was not found.")

@router.post("/mnetwork/unlike-thread")
async def router_mnetwork_unlike_thread(payload: like, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    await check_ban(user_id, "MNetwork")
    
    async with get_dict_connection("mnetwork") as conn:
        thread = payload.id
        with conn.cursor() as cursor:
            await cursor.execute('''SELECT likes FROM threads WHERE id = %s''', (thread,))
            result1 = await cursor.fetchone()
            if result1:
                await cursor.execute('''SELECT id FROM thread_likes WHERE thread_id = %s AND author_id = %s''', (thread, user_id))
                result2 = await cursor.fetchone()
                if result2:
                    await cursor.execute('''DELETE FROM thread_likes WHERE thread_id = %s AND author_id = %s''', (thread, user_id))
                    await cursor.execute('''SELECT COUNT(*) AS cnt FROM thread_likes WHERE thread_id = %s''', (thread,))
                    result3 = await cursor.fetchone()
                    likes = result3["cnt"]
                    await cursor.execute('''UPDATE threads SET likes = %s WHERE id = %s''', (likes, thread))
                    await conn.commit()
                    return JSONResponse(status_code=200, content={"message": "Like removed successfully."})
                else:
                    raise HTTPException(status_code=400, detail="You didn't like this thread yet.")
            else:
                raise HTTPException(status_code=404, detail="The thread you attempted to remove your like from was not found.")
            
@router.post("/mnetwork/unfollow-user")
async def router_mnetwork_unfollow_user(payload: follow, user_id=Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    await check_ban(user_id, "MNetwork")

    async with get_dict_connection("mnetwork") as conn:
        recipient = payload.user
        async with conn.cursor() as cursor:
            recipient_info = await get_user_information_by_username(recipient)
            if recipient_info:
                recipient_id = recipient_info["id"]
                await cursor.execute(
                    '''SELECT id FROM user_follows WHERE user_id = %s AND author_id = %s''',
                    (recipient_id, user_id)
                )
                result = await cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=400, detail="You are not following this user.")
                else:
                    await cursor.execute(
                        '''DELETE FROM user_follows WHERE user_id = %s AND author_id = %s''',
                        (recipient_id, user_id)
                    )
                    await conn.commit()
                    return JSONResponse(status_code=200, content={"message": "User unfollowed successfully."})
            else:
                raise HTTPException(status_code=404, detail="The user you attempted to unfollow was not found.")
                    
@router.get("/mnetwork/get-feed")
async def router_mnetwork_get_feed(user_id=Depends(get_current_user_id)):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                '''SELECT community_id FROM community_follows WHERE author_id = %s''',
                (user_id,)
            )
            followed_communities = [row['community_id'] for row in await cursor.fetchall()]
            
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
                await cursor.execute(query, tuple(followed_communities))
                threads = await cursor.fetchall()
            else:
                query = '''
                    SELECT t.*, c.name AS community_name
                    FROM threads t
                    JOIN communities c ON t.community_id = c.id
                    WHERE t.community_id = 3
                    ORDER BY t.timestamp DESC
                    LIMIT 30
                '''
                await cursor.execute(query)
                threads = await cursor.fetchall()
            
            for thread in threads:
                try:
                    thread["extra_info"] = json.loads(thread.get("extra_info", "{}"))
                except (TypeError, json.JSONDecodeError):
                    thread["extra_info"] = {}
            
            return {"threads": threads}


@router.post("/mnetwork/transfer-community-ownership")
async def transfer_community_ownership(payload: transferCommunityOwnership, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="You have to log in to do this operation.")
    
    community_id = payload.community_id
    new_owner = payload.new_owner
    password = payload.password

    await check_ban(user_id, "MNetwork")

    async with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            async with conn.cursor() as cursor:
                if user_id:
                    await cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (community_id,))
                    result = await cursor.fetchone()
                    if result:
                        author = result["author_id"]

                        if author == user_id:
                            async with get_dict_connection("main") as main_conn:
                                async with main_conn.cursor() as main_cursor:
                                    await main_cursor.execute("SELECT password FROM users WHERE id = %s", (user_id,))
                                    credentials = await main_cursor.fetchone()
            
                                    if not credentials:
                                        return JSONResponse(
                                            status_code=500,
                                            content={"detail": "Unexpected error occurred: Missing user information. Contact support to fix this."}
                                        )
            
                                    hashed_password = credentials["password"]
                                    if check_password(password, hashed_password):
                                        return JSONResponse(status_code=401, content={"detail": "Incorrect password."})

                                    await main_cursor.execute("SELECT id, username FROM users WHERE username = %s", (new_owner,))
                                    result_2 = await main_cursor.fetchone()
                                    if result_2:
                                        new_owner_id = result_2["id"]
                                        new_owner_username = result_2["username"] # to match database's username since it's not case sensitive

                                        await cursor.execute('''SELECT id FROM community_follows WHERE community_id = %s AND author_id = %s''', (community_id, new_owner_id))
                                        result_3 = await cursor.fetchone()

                                        if not result_3:
                                            return JSONResponse(status_code=401, content="The new owner should be following this community in order to transfer it.")

                                        await cursor.execute("UPDATE communities SET author_id = %s, author_name = %s WHERE id = %s", (new_owner_id, new_owner_username, community_id))
                                        await conn.commit()
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
            await conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")

@router.post("/mnetwork/delete-community")
async def delete_community(payload: deleteCommunity, user_id=Depends(get_current_user_id)):
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    await check_ban(user_id, "MNetwork")

    community_id = payload.community_id
    password = payload.password

    async with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            with conn.cursor() as cursor:
                await cursor.execute("SELECT author_id FROM communities WHERE id = %s LIMIT 1", (community_id,))
                result = await cursor.fetchone()

                if not result:
                    return JSONResponse(status_code=404, content={"detail": "Community not found."})

                author = result["author_id"]

                user_info = await get_user_information(user_id)
                if not user_info:
                    return JSONResponse(status_code=404, content={"detail": "User not found."})
                
                trust = user_info["trust"]
                if not trust:
                    trust = 0

                if author != user_id:
                    if trust < 10:
                        return JSONResponse(status_code=403, content={"detail": "You must be the owner of this community to delete it."})
                
                async with get_dict_connection("main") as main_conn:
                    async with main_conn.cursor() as main_cursor:
                        await main_cursor.execute("SELECT password FROM users WHERE id = %s", (user_id,))
                        credentials = await main_cursor.fetchone()

                        if not credentials:
                            return JSONResponse(
                                status_code=500,
                                content={"detail": "Unexpected error occurred: Missing user information. Contact support to fix this."}
                            )

                        hashed_password = credentials["password"]
                        if not check_password(password, hashed_password):
                            return JSONResponse(status_code=401, content={"detail": "Incorrect password."})

                await cursor.execute("DELETE FROM communities WHERE id = %s", (community_id,))
                await cursor.execute("DELETE FROM threads WHERE community_id = %s", (community_id,))
                conn.commit()

                return {"message": "Community successfully deleted."}

        except Exception as e:
            await conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")

@router.post("/mnetwork/delete-thread")
async def delete_thread(payload: threadOperation, user_id=Depends(get_current_user_id)):
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    await check_ban(user_id, "MNetwork")

    thread_id = payload.thread_id
    async with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            thread = await get_thread_and_check_permission(thread_id, user_id, conn)

            async with conn.cursor() as cursor:
                await cursor.execute("DELETE FROM posts WHERE thread_id = %s", (thread_id,))
                await cursor.execute("DELETE FROM threads WHERE id = %s", (thread_id,))
                await conn.commit()

            return {"message": "Thread successfully deleted."}

        except HTTPException as he:
            raise he
        except Exception as e:
            await conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")

@router.post("/mnetwork/lock-thread")
async def lock_thread(payload: threadOperation, user_id=Depends(get_current_user_id)):
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    await check_ban(user_id, "MNetwork")

    thread_id = payload.thread_id
    async with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            thread = await get_thread_and_check_permission(thread_id, user_id, conn)

            async with conn.cursor() as cursor:
                await cursor.execute("UPDATE threads SET locked = 1 WHERE id = %s", (thread_id,))
                await conn.commit()

            return {"message": "Thread successfully locked."}

        except HTTPException as he:
            raise he
        except Exception as e:
            conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")

@router.post("/mnetwork/unlock-thread")
async def unlock_thread(payload: threadOperation, user_id=Depends(get_current_user_id)):
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    await check_ban(user_id, "MNetwork")

    thread_id = payload.thread_id
    async with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            thread = await get_thread_and_check_permission(thread_id, user_id, conn)

            async with conn.cursor() as cursor:
                await cursor.execute("UPDATE threads SET locked = 0 WHERE id = %s", (thread_id,))
                await conn.commit()

            return {"message": "Thread successfully unlocked."}

        except HTTPException as he:
            raise he
        except Exception as e:
            await conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")
        
@router.post("/mnetwork/delete-post")
async def delete_post(payload: deletePost, user_id=Depends(get_current_user_id)):
    post_id = payload.id

    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Login required."})
    
    await check_ban(user_id, "MNetwork")

    async with get_dict_connection("mnetwork") as conn:
        try:
            conn.autocommit = False
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT 
                        p.author_id AS post_author,
                        c.author_id AS community_author
                    FROM 
                        posts p
                    INNER JOIN 
                        threads t ON p.thread_id = t.id
                    INNER JOIN 
                        communities c ON t.community_id = c.id
                    WHERE 
                        p.id = %s
                    LIMIT 1
                    """, 
                    (post_id,)
                )
                
                result = await cursor.fetchone()

                if not result:
                    return JSONResponse(status_code=404, content={"detail": "Post not found."})

                post_author = result["post_author"]
                community_author = result["community_author"]

                user_info = await get_user_information(user_id)
                if not user_info:
                    return JSONResponse(status_code=404, content={"detail": "User not found."})
                
                trust = int(user_info.get("trust", 0))

                is_post_author = post_author == user_id
                is_community_author = community_author == user_id
                is_admin = trust >= 10

                if not (is_post_author or is_community_author or is_admin):
                    return JSONResponse(
                        status_code=403, 
                        content={"detail": "You must be the author of this post or the owner of the community to delete it."}
                    )
                
                await cursor.execute("DELETE FROM posts WHERE id = %s", (post_id,))
                await conn.commit()

                return {"message": "Post successfully deleted."}

        except Exception as e:
            await conn.rollback()
            print("Error: " + str(e))
            raise HTTPException(status_code=500, detail="Operation failed.")
        
@router.get("/mnetwork/get-user-communities")
async def get_user_communities(user: str):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM communities WHERE author_name = %s ORDER BY timestamp DESC LIMIT 50", (user,))
            result = await cursor.fetchall()

            return {"communities": result}
        
@router.get("/mnetwork/get-user-threads")
async def get_user_communities(user: str):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM threads WHERE author_name = %s ORDER BY timestamp DESC LIMIT 50", (user,))
            result = await cursor.fetchall()

            return {"threads": result}
        
@router.get("/mnetwork/get-user-posts")
async def get_user_communities(user: str):
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM posts WHERE author_name = %s ORDER BY timestamp DESC LIMIT 50", (user,))
            result = await cursor.fetchall()

            return {"posts": result}
        
@router.get("/mnetwork/get-user-followers")
async def get_user_communities(user: str):
    user_information = await get_user_information_by_username(user)
    if not user_information:
        raise HTTPException(status_code=404, detail="User not found.")
    user_id = user_information["id"]
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM user_follows WHERE user_id = %s ORDER BY timestamp DESC LIMIT 50", (user_id,))
            result = await cursor.fetchall()

            return {"followers": result}
        
@router.get("/mnetwork/get-user-following")
async def get_user_communities(user: str):
    user_information = await get_user_information_by_username(user)
    if not user_information:
        raise HTTPException(status_code=404, detail="User not found.")
    user_id = user_information["id"]
    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM user_follows WHERE author_id = %s ORDER BY timestamp DESC LIMIT 50", (user_id,))
            result = await cursor.fetchall()

            return {"following": result}
        
@router.get("/mnetwork/get-followed-communities")
async def get_followed_communities(user_id=Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    await check_ban(user_id, "MNetwork")

    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''
                SELECT cf.community_id, c.name, cf.timestamp
                FROM community_follows cf
                JOIN communities c ON cf.community_id = c.id
                WHERE cf.author_id = %s
                ORDER BY cf.timestamp DESC
                LIMIT 50
            ''', (user_id,))
            result = await cursor.fetchall()

            return {"following": result}
        
@router.get("/mnetwork/get-user-profile")
async def get_user_profile(user: str, author_id=Depends(get_current_user_id)):
    user_information = await get_user_information_by_username(user)
    if not user_information:
        raise HTTPException(status_code=404, detail="User not found.")

    user_id = user_information["id"]

    # just in case
    result1 = None
    result2 = None
    result3 = None
    follower_count = 0

    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id, username, biography, createdOn FROM users WHERE id = %s", (user_id,))
            result1 = await cursor.fetchone()
            if not result1:
                raise HTTPException(status_code=404, detail="User not found.")

    following = False
    username_color = await get_setting(user_id, "Username color")

    badges = await get_setting(user_id, "Badges")
    if badges:
        try:
            badges = json.loads(badges)
        except json.JSONDecodeError:
            badges = []
    else:
        badges = []


    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT COUNT(*) AS cnt FROM user_follows WHERE user_id = %s''', (user_id,))
            result2 = await cursor.fetchone()
            follower_count = result2["cnt"]

            if author_id:
                await cursor.execute("SELECT id FROM user_follows WHERE author_id = %s AND user_id = %s", (author_id, user_id))
                result3 = await cursor.fetchone()
                if result3:
                    following = True

    return { "profile": result1, "following": following, "follower_count": follower_count, "username_color": username_color, "badges": badges }
        
@router.post("/mnetwork/update-community-name")
async def router_update_community_name(payload: editCommunity, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail=noAccMsg)
    
    await check_ban(user_id, "MNetwork")

    community_id = payload.community_id
    value = payload.value

    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT author_id FROM communities WHERE id = %s", (community_id,))
            result = await cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Community not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the community to do this operation.")
            
            user_info = await get_user_information(user_id)

            premium = user_info["premium"]
            username_color = "#808080"
            if premium == 1:
                username_color = await get_setting(user_id, "Username color")

            username = user_info["username"]
            extra_information = { "Username color": username_color }
            
            await cursor.execute("UPDATE communities SET name = %s WHERE id = %s", (value, community_id))
            await conn.commit()
            return { "message": "Name updated successfully" }
        
@router.post("/mnetwork/update-community-description")
async def router_update_community_description(payload: editCommunity, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail=noAccMsg)
    
    await check_ban(user_id, "MNetwork")

    community_id = payload.community_id
    value = payload.value

    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT author_id FROM communities WHERE id = %s", (community_id,))
            result = await cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Community not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the community to do this operation.")
            
            await cursor.execute("UPDATE communities SET description = %s WHERE id = %s", (value, community_id))
            await conn.commit()
            return { "message": "Description updated successfully" }
        
@router.post("/mnetwork/update-thread-title")
async def router_update_thread_title(payload: editThread, user_id = Depends(get_current_user_id)):
    thread_id = payload.thread_id
    value = payload.value

    if not user_id:
        raise HTTPException(status_code=404, detail=noAccMsg)
    
    await check_ban(user_id, "MNetwork")

    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT author_id FROM threads WHERE id = %s", (thread_id,))
            result = await cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Thread not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the thread to do this operation.")
            
            user_info = await get_user_information(user_id)
            premium = user_info["premium"]
            username_color = "#808080"
            if premium == 1:
                username_color = await get_setting(user_id, "Username color")

            extra_information = { "Username color": username_color }
            
            await cursor.execute("UPDATE threads SET title = %s, extra_info = %s WHERE id = %s", (value, json.dumps(extra_information), thread_id))
            await conn.commit()
            return { "message": "Title updated successfully" }
        
@router.post("/mnetwork/update-thread-description")
async def router_update_thread_description(payload: editThread, user_id = Depends(get_current_user_id)):
    thread_id = payload.thread_id
    value = payload.value

    if not user_id:
        raise HTTPException(status_code=404, detail=noAccMsg)
    
    await check_ban(user_id, "MNetwork")

    async with get_dict_connection("mnetwork") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT author_id FROM threads WHERE id = %s", (thread_id,))
            result = await cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Thread not found.")
            
            author_id = result["author_id"]

            if not user_id == author_id:
                raise HTTPException(status_code=403, detail="You need to be the owner of the thread to do this operation.")
            
            await cursor.execute("UPDATE threads SET content = %s WHERE id = %s", (value, thread_id))
            await conn.commit()
            return { "message": "Description updated successfully" }
        
@router.post("/mnetwork/pin-thread")
async def router_pin_thread(thread_id: int, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    await check_ban(user_id, "MNetwork")

    async with get_dict_connection("mnetwork") as conn:
        conn.autocommit = False
        community = await get_thread_community_and_check_permission(thread_id, user_id, conn)

        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE threads SET pinned = 1 WHERE id = %s", (thread_id,))
            await conn.commit()

            return { "message": "Thread pinned successfully" }
        
@router.post("/mnetwork/unpin-thread")
async def router_pin_thread(thread_id: int, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    await check_ban(user_id, "MNetwork")

    async with get_dict_connection("mnetwork") as conn:
        conn.autocommit = False
        thread = await get_thread_community_and_check_permission(thread_id, user_id, conn)

        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE threads SET pinned = 0 WHERE id = %s", (thread_id,))
            await conn.commit()
            
            return { "message": "Thread un-pinned successfully" }
        
@router.post("/mnetwork/change-username-color")
async def router_change_username_color(payload: field_1, user_id = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    value = payload.value
    
    await check_ban(user_id, "MNetwork")
    user_info = await get_user_information(user_id)

    if user_info["premium"] == 0:
        raise HTTPException(status_code=402, detail="You need a premium account to do this operation.")
    if not re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value):
        raise HTTPException(status_code=400, detail="Invalid HEX code for color. Must be this format: #000000 or #FFF")
    
    await set_setting(user_id, "Username color", value)

def normalize_ip_value(ip_val):
    if ip_val is None:
        return None
    if isinstance(ip_val, memoryview):
        ip_val = bytes(ip_val)
    if isinstance(ip_val, (bytes, bytearray)):
        try:
            return ip_val.decode('utf-8').rstrip('\x00')
        except Exception:
            return ip_val.hex()
    return str(ip_val).strip()

@router.post("/mnetwork/claim-vip")
async def router_claim_vip(request: Request, user_id=Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found.")
    
    client_ip = (
        request.headers.get("x-real-ip")
        or request.headers.get("X-Forwarded-For")
        or request.client.host
    )

    stored_ip = hash_ip(client_ip)
    stored_ip_norm = normalize_ip_value(stored_ip)
    
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE users SET ip_address = %s WHERE id = %s",
                (stored_ip_norm, user_id)
            )
            
            client_info = await get_user_information(user_id, conn)
            client_email = client_info["email"]
            client_username = client_info["username"]
            client_premium = client_info["premium"]

            if client_premium == 1:
                raise HTTPException(status_code=400, detail="You already have claimed this!")

            await cursor.execute(
                "SELECT email, ip_address FROM users WHERE invited_by = %s",
                (client_username,)
            )
            invited_users = await cursor.fetchall()

            valid_count = 0
            seen_emails = set()
            seen_ips = set()

            for row in invited_users:
                email = row["email"]
                ip = normalize_ip_value(row["ip_address"])

                if ip == stored_ip_norm:
                    continue

                if email == client_email or email in seen_emails or ip in seen_ips:
                    continue

                valid_count += 1
                seen_emails.add(email)
                seen_ips.add(ip)

            if valid_count >= 3:
                await cursor.execute(
                    "UPDATE users SET premium = 1 WHERE id = %s",
                    (user_id,)
                )
                await add_badge(user_id, "vip")
                await conn.commit()
                return {"status": "Congratulations! You now have the VIP pass. Enjoy :)"}
            
            await conn.commit()
            return JSONResponse(status_code=400, content={"detail": "Sorry, but you do not have enough valid invites", "invites": valid_count})