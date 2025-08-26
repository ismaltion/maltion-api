from pydantic import BaseModel
from datetime import date
from enum import Enum
from typing import Optional

class WrongDatabase(Exception):
    def __init__(self, message="Attempted to connect to an undefined database."):
        self.message = message
        super().__init__(self.message)

class FieldType(str, Enum):
    username = "username"
    nickname = "nickname"
    country = "country"
    birthday = "birthday"
    email = "email"

class field_1(BaseModel):
    value: str

class field_2(BaseModel):
    value1: str
    value2: str

class ChangeFieldRequest(BaseModel):
    value: str

class ChangeDateRequest(BaseModel):
    value: date

class ChangePasswordRequest(BaseModel):
    oldValue: str
    newValue: str

class send_friend_request(BaseModel):
    friend_name: str
    message: str

class accept_friend_request(BaseModel):
    friend_name: str
    answer: str

class friend_operation(BaseModel):
    friend_name: str

class mnetwork_create_community(BaseModel):
    name: str
    description: Optional[str] = "No description provided."

class mnetwork_create_thread(BaseModel):
    title: str
    content: Optional[str] = "No description provided."
    community_id: int

class mnetwork_create_post(BaseModel):
    content: str
    thread_id: int
