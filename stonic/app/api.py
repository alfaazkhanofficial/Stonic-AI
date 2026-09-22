import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from stonic.config.settings import Configuration, Settings
from stonic.core.models import Activity, ChatInput, RecordCreate, RecordUpdate
from stonic.core.service import CoreService
from stonic.diagnostics.health import Diagnostics
from stonic.events.bus import EventBus
from stonic.providers.llm import OpenAICompatibleProvider
from stonic.storage.database import Database
from stonic.security.secrets import SecretStore
from stonic.tasks.contracts import Decision
from stonic.events.scheduler import ReminderCreate, ReminderCancel
from stonic.providers.web import ResearchRequest
from stonic.providers.vision import VisionRequest
from stonic.tools.knowledge import PreferenceSave
from stonic.tools.gaming import GameQuery
from stonic.events.triggers import Trigger
from stonic.voicelive import VoiceService, register_voice_routes

RecordKind = Literal["notes", "tasks", "memory"]


def create_app(data_dir: Path | None = None, token: str | None = None) -> FastAPI:
    directory = data_dir or Path(os.environ.get("STONIC_DATA_DIR", "data"))
    secret = token or os.environ.get("STONIC_API_TOKEN")
    if not secret:
        raise RuntimeError("STONIC_API_TOKEN is required. Use npm run dev or npm start to launch securely.")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(directory / "stonic.db")
        credentials = SecretStore(directory)
        provider = OpenAICompatibleProvider(credentials)
        try:
            events = EventBus(db)
            events.publish("startup", "Local storage initialized.")
            if db.recovery:
                events.publish("startup", f"The previous database was quarantined at {db.recovery.get('quarantined', 'the recovery folder')}; a fresh local database is active.", "warning")
            config = Configuration(db)
            events.publish("startup", "Configuration validated.")
            if config.recovered:
                events.publish("startup", "A damaged or outdated settings record was recovered from the previous valid copy.", "warning")
            diagnostics = Diagnostics(directory)
            core = CoreService(db, config, diagnostics, events, provider)
            app.state.core = core
            app.state.credentials = credentials
            app.state.provider = provider
            voice = VoiceService(core, credentials)
            app.state.voice = voice
            diagnostics.extra_checks.append(voice.health)
            core.scheduler.start()
            cleanup = db.cleanup(config.values.history_retention_days)
            if any(cleanup.values()): events.publish("startup", f"Privacy retention cleanup removed {sum(cleanup.values())} transient records.")
            events.publish("startup", "State engine, permissions, and local tools initialized.")
            async def refresh_provider_health():
                try:
                    diagnostics.llm = await provider.check(config.values)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    diagnostics.llm.status = "degraded"
                    diagnostics.llm.detail = "The provider connectivity check failed unexpectedly; local workspace features remain available."
            app.state.refresh_provider_health = refresh_provider_health
            provider_health_task = None
            if config.values.llm_model:
                diagnostics.llm.status = "initializing"
                diagnostics.llm.detail = "Checking the configured provider in the background; local workspace features are already available."
                provider_health_task = asyncio.create_task(refresh_provider_health(), name="stonic-provider-health")
            core.state.transition(Activity.IDLE)
            events.publish("startup", "Workspace started. Provider verification is running in the background.")
            if config.values.voice_autostart:
                voice.autostart_soon()
            yield
            await voice.shutdown()
            if provider_health_task and not provider_health_task.done():
                provider_health_task.cancel()
                try: await provider_health_task
                except asyncio.CancelledError: pass
            core.cancel()
            await core.scheduler.close()
            await core.browser.close()
            core.state.transition(Activity.STOPPED)
            events.publish("lifecycle", "Workspace stopped cleanly.")
        finally:
            await provider.close()
            db.close()

    app = FastAPI(title="STONIC V2", version="0.2.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_auth(request: Request, call_next):
        if request.url.path.startswith("/api"):
            provided = request.headers.get("X-Stonic-Token", "")
            if not secrets.compare_digest(provided, secret):
                return JSONResponse({"detail": "Local session authentication required"}, status_code=401)
            origin = request.headers.get("origin")
            ui_port=os.environ.get('STONIC_UI_PORT','5173');backend_port=os.environ.get('STONIC_PORT','8765');allowed={f'http://127.0.0.1:{ui_port}',f'http://localhost:{ui_port}',f'http://127.0.0.1:{backend_port}',f'http://localhost:{backend_port}'}
            if origin and origin not in allowed:
                return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def core() -> CoreService:
        return app.state.core

    @app.get("/api/status")
    async def status():
        service = core()
        checks = service.health_checks()
        health = "healthy" if all(c.status == "ready" for c in checks) else "recovering" if any(c.status == "recovering" for c in checks) else "degraded"
        return {"version": "0.2.0", "health": health, "activity": service.state.activity,
            "metrics": service.diagnostics.metrics(),
            "checks": [c.model_dump() for c in checks],
            "counts": {kind: service.db.query("SELECT COUNT(*) AS count FROM records WHERE kind=?",(kind,))[0]["count"] for kind in ("notes", "tasks", "memory")}}

    @app.get("/api/logs")
    async def logs():
        return core().events.recent()

    @app.get("/api/events")
    async def events(request: Request):
        bus = core().events
        async def stream():
            listener: asyncio.Queue = asyncio.Queue(maxsize=1000)
            bus.listeners.add(listener)
            try:
                yield 'event: connected\ndata: {}\n\n'
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(listener.get(), timeout=15)
                        if isinstance(event, dict):
                            yield f"event: {event['topic']}\ndata: {json.dumps(event['data'])}\n\n"
                        else:
                            yield f"data: {event.model_dump_json()}\n\n"
                    except TimeoutError:
                        yield ": heartbeat\n\n"
            finally:
                bus.listeners.discard(listener)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/config")
    async def configuration():
        endpoint=core().config.values.llm_base_url
        return {"schema": Settings.model_json_schema(), "values": core().config.values.model_dump(),
                "credential_configured": app.state.credentials.configured(endpoint),
                "credential_required": urlsplit(endpoint).hostname == "api.xkiro.com"}

    @app.put("/api/provider/credential")
    async def save_credential(body: dict):
        try:
            if set(body) != {"key"} or not isinstance(body["key"], str):
                raise ValueError("Provide one API key")
            app.state.credentials.save(body["key"], core().config.values.llm_base_url)
        except (ValueError, OSError):
            raise HTTPException(422, "The provider API key could not be saved securely. Enter a valid key on Windows.")
        core().diagnostics.llm.status="initializing"
        core().diagnostics.llm.detail="Credential saved. Checking provider access in the background."
        core().events.publish("security", "Provider credential saved using Windows user-bound encryption.")
        asyncio.create_task(app.state.refresh_provider_health())
        return {"credential_configured": True}

    @app.delete("/api/provider/credential")
    async def delete_credential(request: Request):
        if request.headers.get("X-Stonic-Confirm") != "delete":
            raise HTTPException(400, "Explicit deletion confirmation required")
        app.state.credentials.delete(core().config.values.llm_base_url)
        core().diagnostics.llm.status="unconfigured" if urlsplit(core().config.values.llm_base_url).hostname == "api.xkiro.com" else "initializing"
        core().events.publish("security", "Provider credential removed.")
        return {"credential_configured": app.state.credentials.configured(core().config.values.llm_base_url)}

    @app.get("/api/jobs")
    async def jobs():
        return core().tasks.list()

    @app.get("/api/schedules")
    async def schedules():
        return core().scheduler.list().data["schedules"]

    @app.get("/api/productivity/briefing")
    async def daily_briefing():
        return core().productivity.briefing().data

    @app.post("/api/productivity/briefing/viewed")
    async def viewed_briefing():
        core().productivity.viewed()
        return {"viewed":True}

    @app.get("/api/productivity/calendar")
    async def export_calendar():
        return Response(content=core().productivity.calendar(),media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition":'attachment; filename="stonic-reminders.ics"'})

    @app.post("/api/schedules")
    async def create_schedule(body: ReminderCreate):
        try:
            return core().scheduler.create(body).model_dump()
        except ValueError as error:
            raise HTTPException(422, str(error))

    @app.post("/api/schedules/{identifier}/cancel")
    async def cancel_schedule(identifier: str):
        try:
            return core().scheduler.cancel(ReminderCancel(id=identifier)).model_dump()
        except ValueError as error:
            raise HTTPException(404, str(error))

    @app.get("/api/notifications")
    async def notifications():
        return core().db.query("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 100")

    @app.post("/api/notifications/{identifier}/read")
    async def read_notification(identifier: str):
        if not core().db.execute("UPDATE notifications SET read=1 WHERE id=?", (identifier,)):
            raise HTTPException(404, "Notification does not exist")
        return {"read": True}

    @app.get("/api/preferences")
    async def preferences():
        return core().knowledge.preferences()

    @app.post("/api/preferences")
    async def save_preference(body: PreferenceSave):
        return core().knowledge.preference(body).model_dump()

    @app.patch("/api/preferences/{identifier}")
    async def edit_preference(identifier: str, body: PreferenceSave):
        if not core().db.execute("UPDATE preferences SET category=?,value=?,approved=1 WHERE id=?", (body.category, body.value, identifier)):
            raise HTTPException(404, "Preference does not exist")
        return {"updated": identifier}

    @app.get("/api/gaming")
    async def gaming():
        return {**core().gaming.installed(GameQuery()).data, **core().gaming.performance(GameQuery()).data}

    @app.get("/api/triggers")
    async def triggers():
        return core().triggers.list()

    @app.post("/api/triggers")
    async def create_trigger(body: Trigger):
        return core().triggers.save(body)

    @app.patch("/api/triggers/{identifier}")
    async def edit_trigger(identifier: str, body: Trigger):
        if not core().db.query("SELECT id FROM triggers WHERE id=?", (identifier,)):
            raise HTTPException(404, "Trigger does not exist")
        return core().triggers.save(body, identifier)

    @app.delete("/api/triggers/{identifier}")
    async def delete_trigger(identifier: str, request: Request):
        if request.headers.get("X-Stonic-Confirm") != "delete":
            raise HTTPException(400, "Explicit deletion confirmation required")
        core().db.execute("DELETE FROM triggers WHERE id=?", (identifier,))
        return {"deleted":identifier}

    @app.get("/api/plugins")
    async def plugins():
        return core().skills.list()

    @app.put("/api/plugins/{identifier}")
    async def configure_plugin(identifier: str, body: dict):
        if type(body.get("enabled")) is not bool:
            raise HTTPException(422, "Choose whether the skill is enabled")
        try:
            if body["enabled"]:
                if body.get("confirm_trusted_code") is not True or not isinstance(body.get("config"), dict):
                    raise ValueError("Review and confirm trusted local code and its configuration before enabling")
                core().skills.enable(identifier, body.get("digest"), body["config"])
            else:
                core().skills.disable(identifier)
            return {"enabled": body["enabled"]}
        except (ValueError, OSError) as error:
            raise HTTPException(422, str(error))

    @app.get("/api/research")
    async def research_history():
        reports=[]
        for row in core().db.records("research")[:50]:
            try:
                payload=json.loads(row["content"])
                if isinstance(payload,dict): reports.append({"id":row["id"],**payload})
            except (json.JSONDecodeError,TypeError): continue
        return reports[:30]

    @app.post("/api/vision")
    async def vision(body: VisionRequest):
        if core().lock.locked():
            raise HTTPException(409,"Another request is active. Stop it or wait before analyzing the image.")
        try:
            async with core().lock:
                core().active=asyncio.current_task()
                core().state.transition(Activity.EXECUTING)
                try:
                    return (await core().vision.process(body)).model_dump()
                finally:
                    core().active=None
                    core().state.transition(Activity.IDLE)
        except ValueError as error:
            raise HTTPException(422, str(error))
        except Exception:
            raise HTTPException(502, "Image processing failed. Check the selected provider or local OCR installation.")

    @app.get("/api/vision/captures/{identifier}")
    async def captured_image(identifier: str):
        try:
            return Response(content=core().vision.get_capture(identifier),media_type="image/png")
        except ValueError as error:
            raise HTTPException(404,str(error))

    @app.get("/api/computer/windows")
    async def windows():
        try:
            return core().computer.windows().data
        except ValueError as error:
            raise HTTPException(503, str(error))

    @app.post("/api/computer/action")
    async def computer_action(body: dict):
        if body.get("tool") not in {"computer.window", "computer.launch", "gaming.mode", "gaming.launch", "gaming.fps"} or not isinstance(body.get("arguments"), dict):
            raise HTTPException(422, "Choose a supported computer action")
        if core().lock.locked():
            raise HTTPException(409, "Another request is active")
        decision = Decision.model_validate({"kind": "plan", "message": "Apply the selected " + body["tool"].replace(".", " ") + " action", "steps": [
            {"id": "desktop_action", "title": "Apply the selected " + body["tool"].replace(".", " ") + " action", "tool": body["tool"], "arguments_json": json.dumps(body["arguments"]), "depends_on": []}]})
        async with core().lock:
            session_id = body.get("session_id", "main") if isinstance(body.get("session_id", "main"), str) else "main"
            if not session_id.replace("_", "").replace("-", "").isalnum() or len(session_id) > 64:
                session_id = "main"
            job = core().tasks.create(decision, session_id)
            return await core().run_job(job["id"])

    @app.post("/api/research")
    async def research(body: ResearchRequest):
        if core().lock.locked():
            raise HTTPException(409, "Another request is active")
        async with core().lock:
            core().active = asyncio.current_task()
            core().state.transition(Activity.EXECUTING)
            try:
                async with asyncio.timeout(180):
                    return (await core().web.research(body)).model_dump()
            finally:
                core().active = None
                core().state.transition(Activity.IDLE)

    @app.delete("/api/preferences/{identifier}")
    async def forget_preference(identifier: str, request: Request):
        if request.headers.get("X-Stonic-Confirm") != "delete":
            raise HTTPException(400, "Explicit deletion confirmation required")
        if not core().db.execute("DELETE FROM preferences WHERE id=?", (identifier,)):
            raise HTTPException(404, "Preference does not exist")
        return {"deleted": identifier}

    @app.post("/api/jobs/{identifier}/decision")
    async def job_decision(identifier: str, body: dict):
        if type(body.get("approved")) is not bool or not isinstance(body.get("approval_id"), str):
            raise HTTPException(422, "Approval id and boolean decision required")
        if core().lock.locked():
            raise HTTPException(409, "Wait for the active request or stop it first")
        try:
            async with core().lock:
                core().active = asyncio.current_task()
                core().state.transition(Activity.EXECUTING)
                try:
                    job = await core().tasks.decide(identifier, body["approval_id"], body["approved"])
                    if job["status"] != "waiting_approval":
                        core().append(job["session_id"], "assistant", await core().advance(job))
                        core().events.emit("conversation",{"session_id":job["session_id"]})
                    return job
                finally:
                    core().active = None
                    core().state.transition(Activity.IDLE)
        except ValueError as error:
            raise HTTPException(409, str(error))

    @app.post("/api/jobs/{identifier}/cancel")
    async def cancel_job(identifier: str):
        try:
            return core().tasks.cancel(identifier)
        except ValueError as error:
            raise HTTPException(404, str(error))

    @app.post("/api/jobs/{identifier}/resume")
    async def resume_job(identifier: str):
        if core().lock.locked():
            raise HTTPException(409, "Another request is active")
        try:
            async with core().lock:
                return await core().run_job(identifier)
        except ValueError as error:
            raise HTTPException(409, str(error))

    @app.patch("/api/config")
    async def update_config(changes: dict):
        try:
            old = core().config.values
            values = core().config.update(changes)
            if old.llm_base_url != values.llm_base_url or old.llm_model != values.llm_model:
                core().diagnostics.llm.status = "unconfigured"
                core().diagnostics.llm.detail = "Provider configuration changed. Test the connection to verify it."
            core().events.publish("configuration", "Validated configuration saved.")
            return values.model_dump()
        except ValidationError as error:
            raise HTTPException(422, detail=[{"loc": list(e["loc"]), "msg": e["msg"]} for e in error.errors()])

    @app.post("/api/config/reset")
    async def reset_config(body: dict):
        if body.get("confirm") is not True:
            raise HTTPException(400, "Explicit reset confirmation is required")
        old=core().config.values
        try:result=core().config.reset(body.get("key"))
        except ValueError as error:raise HTTPException(422,str(error))
        if old.llm_base_url!=result.llm_base_url or old.llm_model!=result.llm_model:
            core().diagnostics.llm.status="unconfigured"
            core().diagnostics.llm.detail="Provider configuration changed by reset. Test the connection to verify it."
        core().events.publish("configuration","Configuration reset requested by user.")
        return result.model_dump()

    @app.post("/api/provider/test")
    async def test_provider():
        check = await core().provider.check(core().config.values)
        core().diagnostics.llm = check
        core().events.publish("provider", check.detail, "info" if check.status == "ready" else "warning")
        return check.model_dump()

    @app.get("/api/records/{kind}")
    async def get_records(kind: RecordKind):
        return core().db.records(kind)

    @app.post("/api/records/{kind}", status_code=201)
    async def add_record(kind: RecordKind, body: RecordCreate):
        if not body.title.strip():raise HTTPException(422,"Title cannot be blank")
        if kind == "memory" and not body.confirm_memory:raise HTTPException(400,"Explicit memory confirmation is required")
        record=core().db.create_record(kind,body.title,body.content)
        if kind == "memory":
            core().db.classify_memory(record["id"],body.memory_type)
            record["memory_type"] = body.memory_type
        core().events.publish(kind, "A local record was created.")
        return record

    @app.patch("/api/records/{kind}/{identifier}")
    async def update_record(kind: RecordKind, identifier: str, body: RecordUpdate):
        if body.title is not None and not body.title.strip():
            raise HTTPException(422, "Title cannot be blank")
        if kind == "memory" and not body.confirm_memory:raise HTTPException(400,"Explicit memory confirmation is required")
        record=core().db.update_record(kind,identifier,body.model_dump(exclude_unset=True,exclude={"confirm_memory"}))
        if not record:
            raise HTTPException(404, "Record does not exist")
        if kind == "memory" and body.memory_type:
            core().db.classify_memory(identifier,body.memory_type)
            record["memory_type"] = body.memory_type
        core().events.publish(kind, "A local record was updated.")
        return record

    @app.delete("/api/records/{kind}/{identifier}")
    async def delete_record(kind: RecordKind, identifier: str, request: Request):
        if request.headers.get("X-Stonic-Confirm") != "delete":
            raise HTTPException(400, "Explicit deletion confirmation is required")
        count = core().db.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, identifier))
        if not count:
            raise HTTPException(404, "Record does not exist")
        core().events.publish(kind, "A local record was deleted by user request.")
        return {"deleted": identifier}

    @app.get("/api/chat/{session_id}")
    async def history(session_id: str):
        return core().history(session_id)

    @app.post("/api/chat")
    async def chat(body: ChatInput):
        if not body.content.strip():
            raise HTTPException(422, "Message cannot be blank")
        if core().lock.locked():
            raise HTTPException(409, "A generation is already in progress")
        return await core().chat(body)

    @app.post("/api/chat/cancel")
    async def cancel():
        return {"cancelled": core().cancel()}

    @app.get("/api/skills")
    async def skills():
        return core().tools.catalog()

    register_voice_routes(app)

    dist = Path(__file__).resolve().parents[2] / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="desktop")
    return app
