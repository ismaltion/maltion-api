from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
from db import get_google_api_key
import google.generativeai as genai

genai.configure(api_key=get_google_api_key())
model = genai.GenerativeModel("gemini-2.0-flash")

router = APIRouter()

class Message(BaseModel):
    role: str
    parts: list[dict]

class ChatRequest(BaseModel):
    prompt: str
    history: list[Message] = []

@router.post("/cheatgpt/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        history_as_dicts = [msg.model_dump() for msg in request.history]

        chat = model.start_chat(history=history_as_dicts)

        response = chat.send_message(request.prompt)

        return { "message": response.text }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))