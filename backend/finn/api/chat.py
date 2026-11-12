"""Surya chat endpoints: general guidance + document-grounded company answers,
server-side speech-to-text for the mic button, and chat history for logged-in
(non-guest) accounts."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from finn import llm
from finn.api.auth import User, current_user
from finn.db import cursor
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
    thread_id: int | None = None


@router.get("/hello")
def hello(user: User = Depends(current_user)):
    return {"greeting": GREETING, "history": not user.is_anonymous}


def _own_thread(c, thread_id: int, user: User) -> None:
    c.execute("select 1 from public.chat_threads where id = %s and user_id = %s::uuid", (thread_id, user.id))
    if not c.fetchone():
        raise HTTPException(404, "No such conversation")


@router.post("")
def send(req: ChatReq, user: User = Depends(current_user)):
    out = chat(req.message, [t.model_dump() for t in req.history], req.symbols)
    if not user.is_admin:
        out["model"] = None
    out["thread_id"] = None
    if not user.is_anonymous:                  # guests' chats stay on their device only
        payload = {k: out[k] for k in ("kind", "citations", "verified", "companies")}
        with cursor() as c:
            tid = req.thread_id
            if tid:
                _own_thread(c, tid, user)
                c.execute("update public.chat_threads set updated_at = now() where id = %s", (tid,))
            else:
                c.execute("insert into public.chat_threads (user_id, title) values (%s::uuid, %s) returning id",
                          (user.id, req.message.strip()[:80]))
                tid = c.fetchone()[0]
            c.execute("insert into public.chat_messages (thread_id, role, content) values (%s, 'user', %s)",
                      (tid, req.message.strip()))
            c.execute("""insert into public.chat_messages (thread_id, role, content, payload)
                         values (%s, 'assistant', %s, %s::jsonb)""", (tid, out["answer"], json.dumps(payload)))
        out["thread_id"] = tid
    return out


@router.get("/threads")
def threads(user: User = Depends(current_user)):
    if user.is_anonymous:
        return {"threads": [], "history": False}
    with cursor(commit=False) as c:
        c.execute("""select t.id, t.title, t.updated_at, count(m.id)
                     from public.chat_threads t left join public.chat_messages m on m.thread_id = t.id
                     where t.user_id = %s::uuid group by t.id order by t.updated_at desc limit 50""", (user.id,))
        rows = [{"id": i, "title": t, "updated_at": u.isoformat(), "messages": n} for i, t, u, n in c.fetchall()]
    return {"threads": rows, "history": True}


@router.get("/threads/{thread_id}")
def thread(thread_id: int, user: User = Depends(current_user)):
    with cursor(commit=False) as c:
        _own_thread(c, thread_id, user)
        c.execute("""select id, role, content, payload from public.chat_messages
                     where thread_id = %s order by id""", (thread_id,))
        msgs = []
        for mid, role, content, payload in c.fetchall():
            p = payload if isinstance(payload, dict) else (json.loads(payload) if payload else {})
            msgs.append({"id": mid, "role": role, "text": content, **p})
    return {"id": thread_id, "messages": msgs}


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: int, user: User = Depends(current_user)):
    with cursor() as c:
        _own_thread(c, thread_id, user)
        c.execute("delete from public.chat_threads where id = %s", (thread_id,))
    return {"status": "deleted", "id": thread_id}


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
