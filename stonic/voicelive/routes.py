"""HTTP surface for voice, registered onto the existing authenticated ``/api`` app.

Everything here sits behind the same per-launch token and origin checks as the
rest of the API (the middleware guards the whole ``/api`` prefix).
"""
from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from stonic.voicelive.service import VoiceUnavailable


def register_voice_routes(app: FastAPI) -> None:
    def voice():
        return app.state.voice

    @app.get("/api/voice/status")
    async def voice_status():
        return voice().status()

    @app.get("/api/voice/devices")
    async def voice_devices():
        return await voice().devices()

    @app.get("/api/voice/stream")
    async def voice_stream(request: Request):
        service = voice()

        async def stream():
            queue = service.subscribe()
            try:
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                        yield f"data: {json.dumps(event)}\n\n"
                    except TimeoutError:
                        yield ": heartbeat\n\n"
            finally:
                service.unsubscribe(queue)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/voice/start")
    async def voice_start(body: dict | None = None):
        session_id = (body or {}).get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            raise HTTPException(422, "Session id must be text")
        try:
            return await voice().start(session_id)
        except VoiceUnavailable as error:
            raise HTTPException(409, str(error))
        except ValueError:
            raise HTTPException(422, "Session id is not valid")

    @app.post("/api/voice/stop")
    async def voice_stop():
        return await voice().stop()

    @app.post("/api/voice/mute")
    async def voice_mute(body: dict):
        if type(body.get("muted")) is not bool:
            raise HTTPException(422, "Choose muted true or false")
        try:
            return voice().set_muted(body["muted"])
        except VoiceUnavailable as error:
            raise HTTPException(409, str(error))

    @app.post("/api/voice/interrupt")
    async def voice_interrupt():
        return voice().interrupt()

    @app.post("/api/voice/ptt")
    async def voice_ptt(body: dict):
        if type(body.get("held")) is not bool:
            raise HTTPException(422, "Choose held true or false")
        return voice().set_ptt_held(body["held"])

    @app.put("/api/voice/session")
    async def voice_session(body: dict):
        try:
            voice().set_session(body.get("session_id"))
        except (ValueError, TypeError):
            raise HTTPException(422, "Session id is not valid")
        return voice().status()

    @app.put("/api/voice/credential")
    async def voice_save_credential(body: dict):
        try:
            if set(body) != {"key"} or not isinstance(body["key"], str):
                raise ValueError("Provide one API key")
            voice().save_key(body["key"])
        except (ValueError, OSError):
            raise HTTPException(422, "The Gemini API key could not be saved securely. Enter a valid key on Windows.")
        return {"credential_configured": True}

    @app.delete("/api/voice/credential")
    async def voice_delete_credential(request: Request):
        if request.headers.get("X-Stonic-Confirm") != "delete":
            raise HTTPException(400, "Explicit deletion confirmation required")
        voice().delete_key()
        return {"credential_configured": voice().credential_configured()}
