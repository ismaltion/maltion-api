from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from auth import get_current_user_id
from db import get_connection
from utils import get_user_information, get_user_information_by_username
from models import send_friend_request, accept_friend_request, friend_operation

router = APIRouter()

@router.get("/friend-list")
async def router_friend_list(user_id: int = Depends(get_current_user_id)):
    async with get_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")

        friends = user_info.get("friends")

        return friends
    
@router.post("/add-friend")
async def router_send_friend_request(payload: send_friend_request, user_id: int = Depends(get_current_user_id)):
    async with get_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        recipient = payload.friend_name
        message = payload.message

        if len(message) > 128:
            raise HTTPException(status_code=400, detail="Your message is too long. Please shorten it.")

        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")
        
        friend_list = user_info["friends"]

        if recipient in friend_list:
            raise HTTPException(status_code=400, detail="This user is already in your friend list.")

        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT id FROM users WHERE username = %s''', (recipient,)) # check if the recipient exists in the first place
            result = await cursor.fetchone()

            if result:
                await cursor.execute('''SELECT id FROM friend_requests WHERE author = %s AND recipient = %s''', (user_info["username"], recipient))
                result = await cursor.fetchone()
                if result:
                    raise HTTPException(status_code=400, detail="You have already sent a friend request to this user.")
                await cursor.execute('''SELECT * FROM friend_requests WHERE recipient = %s AND author = %s LIMIT 1''', (user_info.get("username"), recipient))
                if result:
                    raise HTTPException(status_code=400, detail="The recipient has sent you a friend request too. Accept it.")

                await cursor.execute('''INSERT INTO friend_requests (author, recipient, timestamp, message) VALUES (%s, %s, NOW(), %s)''', (user_info["username"], recipient, message))
                await conn.commit()

                return JSONResponse(status_code=201, content={"message": "Friend request sent."})
            else:
                raise HTTPException(status_code=404, detail="Recipient not found - Check for typos.")
            
@router.post("/remove-friend")
async def router_remove_friend(payload: friend_operation, user_id: int = Depends(get_current_user_id)):
    async with get_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        username = str(user_info["username"])
        friend_list = user_info["friends"]
        friend = payload.friend_name

        friend_friend_list = []
        error = False # pov: friend account was deleted and no information can be get from it...
        try:
            friend_info = await get_user_information_by_username(friend, conn)
            friend_friend_list = friend_info["friends"]
        except Exception:
            error = True

        if friend.lower() in friend_list:
            friend_list.remove(friend.lower())

        if username.lower() in friend_friend_list and error == False:
            friend_friend_list.remove(username.lower())

        processed_friend_list = ",".join(friend_list)
        processed_friend_friend_list = ""
        if error == False:
            processed_friend_friend_list = ",".join(friend_friend_list)
        if friend.lower() in friend_list or username.lower() in friend_friend_list:
            async with conn.cursor() as cursor:
                await cursor.execute('''UPDATE users SET friends = %s WHERE username = %s''', (processed_friend_list, username))
                if error == False:
                    await cursor.execute('''UPDATE users SET friends = %s WHERE username = %s''', (processed_friend_friend_list, friend))
            await conn.commit()
    return {"message": "Successfully deleted friend"}

@router.get("/get-friend-requests")
async def router_get_friend_requests(user_id = Depends(get_current_user_id)):
    async with get_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM friend_requests WHERE recipient = %s LIMIT 100''', (user_info.get("username"),))
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            results = [dict(zip(columns, row)) for row in rows]
            return results

@router.post("/reply-friend-request")
async def router_accept_friend_request(payload: accept_friend_request, user_id: int = Depends(get_current_user_id)):
    async with get_connection() as conn:
        user_info = await get_user_information(user_id, conn)
        username = user_info["username"]
        friend = payload.friend_name
        answer = payload.answer

        friend_info = await get_user_information_by_username(friend, conn)

        if not user_info:
            raise HTTPException(status_code=404, detail="User not found.")
        
        if not friend_info:
            raise HTTPException(status_code=404, detail="Friend not found.")

        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT id FROM friend_requests WHERE author = %s AND recipient = %s''', (friend, username))
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Friend request not found.")
            
            if answer == "accept":
                friend_list = user_info["friends"]
                if friend not in friend_list:
                    friend_list.append(friend.lower())
                processed_friend_list = ",".join(friend_list)

                friend_friend_list = friend_info["friends"] # worst name ever for variable?
                if username not in friend_friend_list:
                    friend_friend_list.append(username.lower())
                processed_friend_friend_list = ",".join(friend_friend_list)
        
                await cursor.execute('''UPDATE users SET friends = %s WHERE username = %s''', (processed_friend_list, username))
                await cursor.execute('''UPDATE users SET friends = %s WHERE username = %s''', (processed_friend_friend_list, friend))
                await cursor.execute('''DELETE FROM friend_requests WHERE author = %s AND recipient = %s''', (friend, username))
            else:
                await cursor.execute('''DELETE FROM friend_requests WHERE author = %s AND recipient = %s''', (friend, username))

        conn.commit()

        return JSONResponse(status_code=200, content={"message": "Friend request accepted."})
