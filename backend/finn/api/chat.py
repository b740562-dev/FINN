"""Surya chat endpoints: general guidance + document-grounded company answers,
and server-side speech-to-text for the chat's mic button."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from finn import llm
from finn.api.auth import User, current_user
from finn.pull.chat import GREETING, chat

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_AUDIO = 6 * 1024 * 1024        # ~3 min of 16 kHz mono WAV; the app stops at 60 s
AUDIO_TYPES = ("audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/ogg", "audio/aac", "audio/flac",
               "audio/webm", "audio/mp4")


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


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), user: User = Depends(current_user)):
    """Voice note -> text. The app records, converts to 16 kHz mono WAV and
    posts it here; the transcript goes into the message box for the user to send."""
    mime = (audio.content_type or "").split(";")[0].strip().lower()
    if mime not in AUDIO_TYPES:
        raise HTTPException(415, f"Unsupported audio type: {mime or 'unknown'}")
    data = await audio.read(MAX_AUDIO + 1)
    if len(data) > MAX_AUDIO:
        raise HTTPException(413, "Voice note too long. Keep it under a minute.")
    if len(data) < 2000:
        raise HTTPException(422, "Didn't catch anything. Hold the mic a little longer.")
    try:
        text = llm.transcribe(data, "audio/wav" if mime == "audio/x-wav" else mime, ref_id=user.id)
    except RuntimeError:
        raise HTTPException(503, "Speech service is busy. Try again in a moment.")
    if not text:
        raise HTTPException(422, "Didn't catch any words. Try again a little closer to the mic.")
    return {"text": text[:800]}
