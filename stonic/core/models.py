from datetime import datetime, timezone
from enum import StrEnum, IntEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Activity(StrEnum):
    INITIALIZING = "initializing"
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    ERROR = "error"
    STOPPED = "stopped"


class PermissionLevel(IntEnum):
    SAFE = 0
    NORMAL = 1
    SENSITIVE = 2
    CRITICAL = 3


class ActionResult(Contract):
    success: bool
    status: Literal["completed", "failed", "denied", "unavailable"]
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    retryable: bool = False
    verification: str | None = None
    verification_kind: Literal["observed", "delivery", "provider", "evidence"] = "evidence"
    permission_level: PermissionLevel = PermissionLevel.SAFE
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthCheck(Contract):
    id: str
    name: str
    status: Literal["ready", "degraded", "unavailable", "unconfigured", "initializing", "recovering", "failed"]
    detail: str


class RuntimeEvent(Contract):
    id: str = Field(default_factory=lambda: str(uuid4()))
    time: str = Field(default_factory=utc_now)
    subsystem: str
    level: Literal["info", "warning", "error"] = "info"
    message: str


class RecordCreate(Contract):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=20000)
    memory_type: Literal["user", "conversation", "task", "environment"] = "user"
    confirm_memory: bool = False


class RecordUpdate(Contract):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=20000)
    status: Literal["open", "done"] | None = None
    memory_type: Literal["user", "conversation", "task", "environment"] | None = None
    confirm_memory: bool = False


class ChatInput(Contract):
    content: str = Field(min_length=1, max_length=12000)
    session_id: str = Field(default="main", pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class PermissionRequest(Contract):
    id: str = Field(default_factory=lambda: str(uuid4()))
    action: str
    level: PermissionLevel
    description: str
    fingerprint: str = ""
