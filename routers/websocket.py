from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
from db import get_connection
from datetime import datetime

router = APIRouter()

clients = []
typing_users = set()

@router.websocket("/connect")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT author, content, timestamp FROM chat ORDER BY timestamp DESC LIMIT 20")
    history = cursor.fetchall()
    cursor.close()
    conn.close()

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
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO chat (author, content, addressee, timestamp) VALUES (%s, %s, %s, NOW())",
                    (username, message, addressee)
                )
                conn.commit()
                cursor.close()
                conn.close()

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
