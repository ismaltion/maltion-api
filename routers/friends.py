from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from auth import get_current_user_id
from db import get_connection, get_dict_connection
from utils import get_user_information, get_user_information_by_username, send_notification, notification
from models import add_friend, decline_friend_request, friend_operation

router = APIRouter()

# friend list and friend requests work in the same table.
# a friend request is a single row with status "pending"
# a friendship is two rows with status "accepted"

@router.get("/friend-list")
async def router_friend_list(user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="You need to login to do this operation.")
    
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM friends WHERE author_id = %s AND status = %s", (user_id, "accepted"))
            friends = await cursor.fetchall()

        return friends
    
# this is also the same route used to accept friend requests
@router.post("/add-friend")
async def router_add_friend(payload: add_friend, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="You need to login to do this operation.")
    
    friend_name = payload.friend_name.lower()
    message = payload.message

    if len(friend_name) < 3 or len(friend_name) > 32:
        raise HTTPException(status_code=400, detail="The username must be between 3 and 32 characters long.")
    if len(message) > 255:
        raise HTTPException(status_code=400, detail="The message must be less than 255 characters long.")

    async with get_dict_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        friend_info = await get_user_information_by_username(friend_name, conn)

        if not friend_info:
            raise HTTPException(status_code=404, detail="The user you tried to send the friend request to was not found.")
        
        user_username = user_info["username"]
        friend_id = friend_info["id"]
        request_type = "pending"

        if not user_info:
            raise HTTPException(status_code=404, detail="Your user account was not found.")
        if not friend_info:
            raise HTTPException(status_code=404, detail="The user you tried to send the friend request to was not found.")
        if friend_id == user_id:
            raise HTTPException(status_code=400, detail="Duplicate personalities are not supported.")
        
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM friends WHERE author_id = %s AND recipient_id = %s AND status = %s", (user_id, friend_id, "pending"))
            existing_request = await cursor.fetchone()
            if existing_request:
                raise HTTPException(status_code=400, detail="You have already sent a friend request to this user.")
            
            await cursor.execute("SELECT * FROM friends WHERE author_id = %s AND recipient_id = %s AND status = %s", (user_id, friend_id, "accepted"))
            existing_friendship = await cursor.fetchone()
            if existing_friendship:
                raise HTTPException(status_code=400, detail="You already are friends with this user.")
            
            await cursor.execute("SELECT * FROM friends WHERE author_id = %s AND recipient_id = %s AND status = %s", (friend_id, user_id, "pending"))
            reverse_request = await cursor.fetchone()
            if reverse_request:
                request_type = "accepted"
                await cursor.execute("UPDATE friends SET status = %s WHERE id = %s", (request_type, reverse_request["id"]))

            await cursor.execute("INSERT INTO friends (author, author_id, recipient, recipient_id, timestamp, message, status) VALUES (%s, %s, %s, %s, NOW(), %s, %s)", (user_username, user_id, friend_name, friend_id, message, request_type))
            await conn.commit()

            notify = notification("friend_request", f"{user_username} has sent you a friend request.", f"/profile/{user_username}", friend_id)
            if request_type == "accepted":
                notify = notification("friend_request_accepted", f"{user_username} has accepted your friend request.", f"/profile/{user_username}", friend_id)
            await send_notification(friend_id, notify, conn)
        return {"message": "Friend request sent."}
        
            
@router.post("/decline-friend-request")
async def router_decline_friend_request(payload: decline_friend_request, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="You need to login to do this operation.")
    
    friend_name = payload.friend_name.lower()

    if len(friend_name) < 3 or len(friend_name) > 32:
        raise HTTPException(status_code=400, detail="The username must be between 3 and 32 characters long.")

    async with get_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        friend_info = await get_user_information_by_username(friend_name, conn)

        user_username = user_info["username"]
        friend_id = friend_info["id"]

        if not user_info:
            raise HTTPException(status_code=404, detail="Your user account was not found.")
        
        with conn.cursor() as cursor:
            if not friend_info:
                # in case account was deleted but request somehow still exists
                await cursor.execute("DELETE FROM friends WHERE recipient_id = %s AND author = %s AND status = %s", (user_id, friend_name, "pending"))
                await conn.commit()
                return JSONResponse(content={"message": "Friend request declined."}, status_code=200)

            await cursor.execute("SELECT * FROM friends WHERE author_id = %s AND recipient_id = %s AND status = %s", (friend_id, user_id, "pending"))
            existing_request = await cursor.fetchone()
            if not existing_request:
                raise HTTPException(status_code=400, detail="You have no pending friend request from this user.")
            
            await cursor.execute("DELETE FROM friends WHERE id = %s", (existing_request[0],))
            await conn.commit()
        return {"message": "Friend request declined."}
    
@router.post("/cancel-friend-request")
async def router_decline_friend_request(payload: decline_friend_request, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="You need to login to do this operation.")
    
    friend_name = payload.friend_name.lower()

    if len(friend_name) < 3 or len(friend_name) > 32:
        raise HTTPException(status_code=400, detail="The username must be between 3 and 32 characters long.")

    async with get_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        friend_info = await get_user_information_by_username(friend_name, conn)

        user_username = user_info["username"]
        friend_id = friend_info["id"]

        if not user_info:
            raise HTTPException(status_code=404, detail="Your user account was not found.")
        
        with conn.cursor() as cursor:
            if not friend_info:
                # in case account was deleted but request somehow still exists
                await cursor.execute("DELETE FROM friends WHERE recipient_id = %s AND author = %s AND status = %s", (user_id, friend_name, "pending"))
                await conn.commit()
                return JSONResponse(content={"message": "Friend request cancelled."}, status_code=200)

            await cursor.execute("SELECT * FROM friends WHERE author_id = %s AND recipient_id = %s AND status = %s", (user_id, friend_id, "pending"))
            existing_request = await cursor.fetchone()
            if not existing_request:
                raise HTTPException(status_code=400, detail="You have no pending friend request for this user.")
            
            await cursor.execute("DELETE FROM friends WHERE id = %s", (existing_request[0],))
            await conn.commit()
        return {"message": "Friend request cancelled."}
    
@router.post("/remove-friend")
async def router_remove_friend(payload: friend_operation, user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="You need to login to do this operation.")
    
    friend_name = payload.friend_name.lower()

    if len(friend_name) < 3 or len(friend_name) > 32:
        raise HTTPException(status_code=400, detail="The username must be between 3 and 32 characters long.")

    async with get_dict_connection("main") as conn:
        user_info = await get_user_information(user_id, conn)
        friend_info = await get_user_information_by_username(friend_name, conn)

        user_username = user_info["username"]
        friend_id = friend_info["id"]

        if not user_info:
            raise HTTPException(status_code=404, detail="Your user account was not found.")
        
        async with conn.cursor() as cursor:
            if not friend_info:
                # in case account was deleted but friendship somehow still exists
                await cursor.execute("DELETE FROM friends WHERE author_name = %s AND recipient_id = %s AND status = %s", (friend_name, user_id, "accepted"))
                await conn.commit()
            
            await cursor.execute("SELECT * FROM friends WHERE author_id = %s AND recipient_id = %s AND status = %s", (user_id, friend_id, "accepted"))
            existing_friendship = await cursor.fetchone()
            if not existing_friendship:
                raise HTTPException(status_code=400, detail="You are not friends with this user.")
            
            await cursor.execute("DELETE FROM friends WHERE (author_id = %s AND recipient_id = %s) OR (author_id = %s AND recipient_id = %s)", (user_id, friend_id, friend_id, user_id))
            await conn.commit()
        return {"message": "Friend removed."}
    
@router.get("/friend-requests")
async def router_friend_requests(user_id: int = Depends(get_current_user_id)):
    if not user_id:
        raise HTTPException(status_code=404, detail="You need to login to do this operation.")
    
    async with get_dict_connection("main") as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM friends WHERE recipient_id = %s AND status = %s", (user_id, "pending"))
            incoming_requests = await cursor.fetchall()
            await cursor.execute("SELECT * FROM friends WHERE author_id = %s AND status = %s", (user_id, "pending"))
            outgoing_requests = await cursor.fetchall()

        return {"incoming": incoming_requests, "outgoing": outgoing_requests}