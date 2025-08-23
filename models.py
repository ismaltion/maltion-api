from pydantic import BaseModel
from datetime import date
from enum import Enum

class FieldType(str, Enum):
    username = "username"
    nickname = "nickname"
    country = "country"
    birthday = "birthday"
    email = "email"

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