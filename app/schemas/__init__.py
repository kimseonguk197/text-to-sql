from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# Member
class MemberCreate(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
    age: Optional[int] = None


class MemberResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    age: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str


# Product
class ProductCreate(BaseModel):
    name: str
    category: str
    price: float
    stock: int


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    category: str
    price: float
    stock: int
    member_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Order
class OrderCreate(BaseModel):
    product_id: int
    quantity: int


class OrderResponse(BaseModel):
    id: int
    member_id: int
    product_id: int
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


# Chat
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    id: int
    member_id: int
    request: str
    response: str
    created_at: datetime

    class Config:
        from_attributes = True

