from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from auth import get_current_user_id
from db import get_connection
from utils import get_user_information
from models import send_friend_request
router = APIRouter()

@router.get("/friend-list")
def router_friend_list(user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")

        return user_info["friends"]
    
@router.post("/add-friend")
def router_send_friend_request(payload: send_friend_request, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        recipient = payload.friend_name
        message = payload.message

        if len(message) > 128:
            raise HTTPException(status_code=400, detail="Your message is too long. Please shorten it.")

        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")
        
        with conn.cursor() as cursor:
            cursor.execute('''SELECT id FROM users WHERE username = %s''', (recipient,)) # check if the recipient exists in the first place
            result = cursor.fetchone()

            if result:
                cursor.execute('''SELECT id FROM friend_requests WHERE author = %s AND recipient = %s''', (user_info["username"], recipient))
                result_2 = cursor.fetchone()
                if result_2:
                    raise HTTPException(status_code=400, detail="You have already sent a friend request to this user.")
                cursor.execute('''INSERT INTO friend_requests (author, recipient, timestamp, message) VALUES (%s, %s, NOW(), %s)''', (user_info["username"], recipient, message))
                conn.commit()

                return JSONResponse(status_code=201, content={"message": "Friend request sent."})
            else:
                raise HTTPException(status_code=404, detail="Recipient not found - Check for typos.")