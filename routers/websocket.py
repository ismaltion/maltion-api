from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from db import get_connection, get_dict_connection
from datetime import datetime
from utils import get_user_information, get_user_information_by_username, notification, send_notification, get_friend_list
from auth import get_current_user_id
from typing import Set
from collections import defaultdict
from starlette.websockets import WebSocketState
import json

router = APIRouter()

clients = []
typing_users = set()

# this one is just a test
@router.websocket("/connect")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)

    conn = await get_connection()
    cursor = await conn.cursor()
    await cursor.execute("SELECT author, content, timestamp FROM chat ORDER BY timestamp DESC LIMIT 20")
    history = await cursor.fetchall()
    await cursor.close()
    await conn.close()

    for username, message, timestamp in reversed(history):
        await websocket.send_text(json.dumps({
            "timestamp": str(timestamp),
            "username": username,
            "message": message,
        }))

    try:
        while True:
            raw_data = await websocket.receive_text()

            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid message format. Use JSON."}))
                continue

            event_type = data.get("type", "message")

            if event_type == "typing":
                username = data.get("username")
                if username:
                    typing_users.add(username)
                    broadcast_typing = json.dumps({"type": "typing", "username": username})
                    for client in clients:
                        if client != websocket:
                            await client.send_text(broadcast_typing)

            elif event_type == "stop_typing":
                username = data.get("username")
                if username and username in typing_users:
                    typing_users.remove(username)
                    broadcast_stop = json.dumps({"type": "stop_typing", "username": username})
                    for client in clients:
                        if client != websocket:
                            await client.send_text(broadcast_stop)

            elif event_type == "message":
                username = data.get("username", "Guest").strip()
                message = data.get("message", "").strip()
                addressee = "everyone"

                if not message:
                    continue

                # Save message to DB
                conn = await get_connection()
                cursor = await conn.cursor()
                await cursor.execute(
                    "INSERT INTO chat (author, content, addressee, timestamp) VALUES (%s, %s, %s, NOW())",
                    (username, message, addressee)
                )
                await conn.commit()
                await cursor.close()
                await conn.close()

                broadcast_message = json.dumps({
                    "type": "message",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "username": username,
                    "message": message,
                })

                for client in clients:
                    await client.send_text(broadcast_message)

                if username in typing_users:
                    typing_users.remove(username)
                    broadcast_stop = json.dumps({"type": "stop_typing", "username": username})
                    for client in clients:
                        if client != websocket:
                            await client.send_text(broadcast_stop)

    except WebSocketDisconnect:
        clients.remove(websocket)

active_conversations: dict[tuple[int,int], dict[int, WebSocket]] = {}
last_typing_timestamps: dict[tuple[int,int], dict[int, float]] = {}

async def safe_send(ws: WebSocket, message: dict):
    try:
        await ws.send_json(message)
    except Exception:
        pass


@router.websocket("/chat")
async def chat_ws(
    websocket: WebSocket,
    user_id: int = Depends(get_current_user_id),
    friend_username: str = Query(...)
):
    get_friend_list(user_id)

    # update requested by @aveyal in MNetwork: prevent chat if the friend is not in the friend list (good idea).
    friends = await get_friend_list(user_id)
    friend_usernames = {f["friend_username"] for f in friends}
    if friend_username not in friend_usernames:
        await safe_send(websocket, {type: "message", "timestamp": str(datetime.utcnow()), "author_id": 0, "author_name": "System", "recipient_id": user_id, "content": "You can only chat with users in your friends list."})
        await websocket.close(code=1008)
        return

    friend_info = await get_user_information_by_username(friend_username)
    if not friend_info:
        await websocket.close(code=1008)
        return
    friend_id = friend_info["id"]

    user_info = await get_user_information(user_id)
    if not user_info:
        await websocket.close(code=1008)
        return
    username = user_info["username"]

    await websocket.accept()

    conversation_key = tuple(sorted([user_id, friend_id]))

    if conversation_key not in active_conversations:
        active_conversations[conversation_key] = {}
        last_typing_timestamps[conversation_key] = {}

    active_conversations[conversation_key][user_id] = websocket

    friend_ws = active_conversations[conversation_key].get(friend_id)
    friend_online = friend_ws is not None
    friend_last_typing = last_typing_timestamps[conversation_key].get(friend_id, 0)

    await safe_send(websocket, {
        "type": "status",
        "status": "Online" if friend_online else "Offline",
        "username": friend_username,
        "last_typing": friend_last_typing
    })

    if friend_ws:
        await safe_send(friend_ws, {"type": "status", "status": "Online", "username": username})

    try:
        async with get_dict_connection("mnetwork") as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT author_id, author_name, recipient_id, content, timestamp
                    FROM chat
                    WHERE (author_id=%s AND recipient_id=%s) OR (author_id=%s AND recipient_id=%s)
                    ORDER BY timestamp DESC
                    LIMIT 100
                    """,
                    (user_id, friend_id, friend_id, user_id)
                )
                history = await cursor.fetchall()
    except Exception:
        history = []

    for row in reversed(history):
        await safe_send(websocket, {
            "type": "message",
            "timestamp": str(row["timestamp"]),
            "author_id": row["author_id"],
            "author_name": row["author_name"],
            "recipient_id": row["recipient_id"],
            "content": row["content"]
        })

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            event_type = data.get("type", "message")

            if event_type == "typing":
                now_ts = datetime.utcnow().timestamp()
                last_typing_timestamps[conversation_key][user_id] = now_ts

                friend_ws = active_conversations[conversation_key].get(friend_id)
                if friend_ws:
                    await safe_send(friend_ws, {
                        "type": "typing",
                        "username": username,
                        "last_typing": now_ts
                    })
                continue

            elif event_type == "message":
                content = data.get("content", "").strip()
                if not content:
                    continue

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                try:
                    async with get_dict_connection("mnetwork") as conn:
                        async with conn.cursor() as cursor:
                            await cursor.execute(
                                """
                                INSERT INTO chat (author_id, author_name, recipient_id, content)
                                VALUES (%s, %s, %s, %s)
                                """,
                                (user_id, username, friend_id, content)
                            )
                            await conn.commit()
                except Exception:
                    await safe_send(websocket, {"error": "Failed to save message"})
                    continue

                message_payload = {
                    "type": "message",
                    "timestamp": timestamp,
                    "author_id": user_id,
                    "author_name": username,
                    "recipient_id": friend_id,
                    "content": content
                }

                await safe_send(websocket, message_payload)

                friend_ws = active_conversations[conversation_key].get(friend_id)
                if friend_ws:
                    await safe_send(friend_ws, message_payload)
                else:
                    notify = notification("mnetwork", f"You have new message(s) from @{username}", friend_id, "chat")
                    await send_notification(friend_id, notify, no_spam=False)

    except WebSocketDisconnect:
        if conversation_key in active_conversations:
            active_conversations[conversation_key].pop(user_id, None)
            last_typing_timestamps[conversation_key].pop(user_id, None)

            friend_ws = active_conversations[conversation_key].get(friend_id)
            if friend_ws:
                await safe_send(friend_ws, {"type": "status", "status": "Offline", "username": username})

            if not active_conversations[conversation_key]:
                del active_conversations[conversation_key]
                del last_typing_timestamps[conversation_key]