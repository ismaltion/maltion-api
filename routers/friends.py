from fastapi import APIRouter, Depends, HTTPException
from auth import get_current_user_id
from db import get_connection
from utils import get_user_information

router = APIRouter()

@router.get("/friend-list")
def friendList(user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        user_info = get_user_information(user_id, conn)
        
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")

        return user_info["friends"]