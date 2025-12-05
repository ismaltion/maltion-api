from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from db import get_connection, get_dict_connection
from datetime import datetime
from utils import get_user_information, get_user_information_by_username, notification, send_notification
from auth import get_current_user_id
from typing import Set, Dict, List
from collections import defaultdict
from starlette.websockets import WebSocketState
import json

router = APIRouter()

cloud_data: Dict[str, Dict[str, int]] = {}
connections: Dict[str, List[WebSocket]] = {}

@router.websocket("/scratchcloud-test")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_json()
            
            method = message.get("method")
            user = message.get("user")
            project_id = message.get("project_id")
            name = message.get("name")
            value = message.get("value")

            if method == "set":
                cloud_data.setdefault(project_id, {})[name] = value
                
                for conn in connections.get(project_id, []):
                    if conn != websocket:
                        await conn.send_json({
                            "method": "set",
                            "name": name,
                            "value": value
                        })

            elif method == "get":
                current_value = cloud_data.get(project_id, {}).get(name, 0)
                await websocket.send_json({
                    "method": "set",
                    "name": name,
                    "value": current_value
                })

    except WebSocketDisconnect:
        pass
