from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from db import get_google_api_key
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

genai.configure(api_key=get_google_api_key())

model = genai.GenerativeModel(
    "gemini-2.0-flash",
    safety_settings=[
        {
            "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            "threshold": HarmBlockThreshold.BLOCK_NONE,
        },
        {
            "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            "threshold": HarmBlockThreshold.BLOCK_NONE,
        },
        {
            "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            "threshold": HarmBlockThreshold.BLOCK_NONE,
        },
        {
            "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
            "threshold": HarmBlockThreshold.BLOCK_NONE,
        },
    ],
)

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
        if "my students" in request.prompt.lower() or "students" in request.prompt.lower() or "prevent cheating" in request.prompt.lower():
            return StreamingResponse(
                iter(["I'm sorry, but i cannot help teachers with preventing students from cheating."]),
                media_type="text/plain",
                headers={"X-Accel-Buffering": "no"}
            )
        history_as_dicts = [msg.model_dump() for msg in request.history]
        
        chat = model.start_chat(history=history_as_dicts)

        response_stream = chat.send_message(request.prompt, stream=True)

        def generator():
            for chunk in response_stream:
                if chunk.candidates:
                    for part in chunk.candidates[0].content.parts:
                        if hasattr(part, "text") and part.text:
                            yield part.text

        return StreamingResponse(
            generator(),
            media_type="text/plain",
            headers={"X-Accel-Buffering": "no"}  
        )

    except Exception as e:
        print("Error:", str(e))
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")