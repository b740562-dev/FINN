"""Surya chat endpoint: general guidance + document-grounded company answers."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from finn.api.auth import User, current_user
from finn.pull.chat import GREETING, chat

router = APIRouter(prefix="/chat", tags=["chat"])


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=800)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    symbols: list[str] = Field(default_factory=list, max_length=2)


@router.get("/hello")
def hello(user: User = Depends(current_user)):
    return {"greeting": GREETING}


@router.post("")
def send(req: ChatReq, user: User = Depends(current_user)):
    out = chat(req.message, [t.model_dump() for t in req.history], req.symbols)
    if not user.is_admin:
        out["model"] = None
    return out
