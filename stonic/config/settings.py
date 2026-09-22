import json
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from stonic.core.models import Contract
from stonic.storage.database import Database


def metadata(category: str, help_text: str) -> dict:
    return {"category": category, "help": help_text, "restart_required": False, "sensitive": False}


class Settings(Contract):
    schema_version: Literal[1, 2] = Field(default=2, json_schema_extra={"internal": True})
    display_name: str = Field(default="", max_length=60, title="Your name",
        json_schema_extra=metadata("Personalization", "Used to address you in conversations."))
    response_style: Literal["balanced", "concise", "detailed"] = Field(default="balanced", title="Response style",
        json_schema_extra=metadata("Personalization", "Sets the preferred level of detail for AI responses."))
    reduced_motion: bool = Field(default=False, title="Reduced motion",
        json_schema_extra=metadata("Appearance", "Keep the Core still and reduce decorative animation."))
    interface_density: Literal["comfortable", "compact"] = Field(default="comfortable", title="Interface density",
        json_schema_extra=metadata("Appearance", "Adjust spacing in feeds, records, and controls."))
    llm_base_url: str = Field(default="https://api.xkiro.com/v1", max_length=500, title="Provider endpoint",
        json_schema_extra=metadata("AI & Providers", "An OpenAI-compatible /v1 endpoint. HTTP is allowed only for loopback servers."))
    llm_model: str = Field(default="minimax/minimax-m3:free", max_length=160, title="Model identifier",
        json_schema_extra=metadata("AI & Providers", "Enter the exact vendor/model identifier enabled with your provider."))
    temperature: float = Field(default=0.7, ge=0, le=2, title="Temperature",
        json_schema_extra=metadata("AI & Providers", "Controls variation in model responses (0–2)."))
    max_reply_tokens: int = Field(default=1024, ge=256, le=4096, title="Response length limit",
        json_schema_extra=metadata("AI & Providers", "Bounds generated response tokens and avoids oversized provider requests."))
    save_conversations: bool = Field(default=True, title="Save conversations",
        json_schema_extra=metadata("Privacy", "Store new messages locally. Turning off does not erase existing conversations."))
    memory_enabled: bool = Field(default=True, title="Use relevant memories",
        json_schema_extra=metadata("Memory", "Retrieve a small relevant selection of memories for conversations."))
    max_plan_steps: int = Field(default=8, ge=1, le=20, title="Maximum plan steps",
        json_schema_extra=metadata("Tasks & Automation", "Bound the number of actions in each autonomous plan."))
    workspace_root: str = Field(default="", max_length=1000, title="File workspace",
        json_schema_extra=metadata("Computer Control", "Absolute folder for file and developer tools. Blank uses Stonic's documents folder."))
    context_enabled: bool = Field(default=False, title="Include active window context",
        json_schema_extra=metadata("Privacy", "Include the foreground window title in AI requests. Screen images remain on demand."))
    proactive_enabled: bool = Field(default=False, title="Proactive system notices",
        json_schema_extra=metadata("Events & Proactive", "Notify about low disk space and high memory use, with throttling."))
    gaming_mode: bool = Field(default=False, title="Gaming mode",
        json_schema_extra=metadata("Gaming", "Quiet proactive notices while you play. Scheduled reminders stay in your inbox."))
    quiet_start: int = Field(default=22, ge=0, le=23, title="Quiet hours start",
        json_schema_extra=metadata("Events & Proactive", "Local hour when proactive notices become quiet. Reminders stay visible."))
    quiet_end: int = Field(default=8, ge=0, le=23, title="Quiet hours end",
        json_schema_extra=metadata("Events & Proactive", "Local hour when proactive notices resume. Equal hours disables the quiet interval."))
    learning_enabled: bool = Field(default=False, title="Use approved learned preferences",
        json_schema_extra=metadata("Personalization", "Use preferences you explicitly save or approve. No silent profiling."))
    history_retention_days: int = Field(default=0, ge=0, le=3650, title="Transient history retention",
        json_schema_extra=metadata("Privacy", "Automatically remove old conversations, research history, read notices, and briefings. 0 keeps them until you remove them."))
    recovery_retention_days: int = Field(default=30, ge=1, le=365, title="Deleted-file recovery retention",
        json_schema_extra=metadata("Privacy", "Keep recoverable deleted workspace files for this many days before automatic cleanup."))
    recovery_max_mb: int = Field(default=512, ge=10, le=4096, title="Deleted-file recovery limit",
        json_schema_extra=metadata("Privacy", "Bound the local recovery area. Oldest recovery copies are removed first when this limit is exceeded."))
    ocr_language: Literal["eng", "hin", "eng+hin"] = Field(default="eng", title="Local OCR language",
        json_schema_extra=metadata("Computer Control", "Language pack used for on-device Tesseract OCR. STONIC never uploads OCR input automatically."))

    voice_cloud_consent: bool = Field(default=False, title="Allow cloud voice", json_schema_extra=metadata("Privacy",
        "While voice is on, microphone audio is streamed to Google's Gemini Live service. Nothing is sent while voice is off or muted."))
    voice_autostart: bool = Field(default=False, title="Start voice when STONIC opens", json_schema_extra=metadata("Voice",
        "Begin listening automatically at launch. Requires a Gemini key and cloud voice to be allowed."))
    voice_name: Literal["Charon", "Puck", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr"] = Field(default="Charon", title="Voice", json_schema_extra=metadata("Voice",
        "The voice STONIC speaks with. Applies the next time voice starts."))
    voice_live_model: str = Field(default="gemini-3.8-live", max_length=120, title="Live model", json_schema_extra=metadata("Voice",
        "Gemini Live model identifier. Applies the next time voice starts."))
    voice_input_device: str = Field(default="", max_length=200, title="Microphone", json_schema_extra=metadata("Voice",
        "Exact device name. Blank uses the Windows default. An unavailable device falls back to the default."))
    voice_output_device: str = Field(default="", max_length=200, title="Speaker", json_schema_extra=metadata("Voice",
        "Exact device name. Blank uses the Windows default. An unavailable device falls back to the default."))
    voice_push_to_talk: Literal["off", "ctrl+space", "ctrl+alt+space", "f8", "f9"] = Field(default="off", title="Push-to-talk", json_schema_extra=metadata("Voice",
        "Only hear you while this key is held (global on Windows). Off means always listening."))
    voice_barge_in: Literal["off", "guarded"] = Field(default="off", title="Interrupt by speaking", json_schema_extra=metadata("Voice",
        "Guarded lets you talk over STONIC once it has learned your room's echo; it stays inactive where echo cannot be told from a voice. Off waits until STONIC finishes."))
    voice_end_of_speech_ms: int = Field(default=650, ge=200, le=3000, title="Pause before STONIC replies (ms)", json_schema_extra=metadata("Voice",
        "How long you must be silent before STONIC answers. 500-800 suits most people. Applies the next time voice starts."))
    voice_idle_sleep_minutes: int = Field(default=0, ge=0, le=240, title="Stop after idle minutes", json_schema_extra=metadata("Voice",
        "Stop listening after this many minutes without speech. 0 never stops automatically."))

    @field_validator("voice_live_model", "voice_input_device", "voice_output_device")
    @classmethod
    def trim_voice(cls, value: str) -> str:
        return value.strip()

    @field_validator("voice_live_model")
    @classmethod
    def validate_live_model(cls, value: str) -> str:
        import re
        if not re.fullmatch(r"[A-Za-z0-9._/-]{3,120}", value):
            raise ValueError("Use the model identifier only, for example gemini-3.8-live")
        return value

    @field_validator("workspace_root")
    @classmethod
    def validate_root(cls, value: str) -> str:
        from pathlib import Path
        if value and not Path(value).is_absolute():
            raise ValueError("Workspace must be an absolute folder path")
        return value

    @field_validator("llm_base_url")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
            raise ValueError("Use a clean endpoint URL without credentials, query, or fragment")
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}):
            raise ValueError("Remote providers must use HTTPS; HTTP is allowed only on loopback")
        return value.rstrip("/")

    @field_validator("llm_model", "display_name")
    @classmethod
    def trim(cls, value: str) -> str:
        return value.strip()


class Configuration:
    # Removed with the voice subsystem. Existing installations may still have
    # these keys in the SQLite settings row, so migrate them away before strict
    # Pydantic validation instead of breaking startup after the update.
    RETIRED_SETTINGS = {
        "voice_language", "voice_threads", "speech_speed", "voice_silence_seconds",
        "vad_threshold", "voice_context_seconds", "audio_input_device", "audio_output_device",
    }

    def __init__(self, db: Database) -> None:
        self.db = db
        self.recovered = False
        rows = db.settings_rows()
        current_raw = rows.get("current") if rows else None
        previous_raw = rows.get("previous") if rows else None
        current = self._parse(current_raw)
        previous = self._parse(previous_raw)
        candidate = self._validate(current) if current is not None else None
        if candidate is None and previous is not None:
            candidate = self._validate(previous)
            self.recovered = candidate is not None
        if candidate is None:
            candidate = Settings()
            self.recovered = bool(rows)
        self.values = candidate
        cleaned = {k:v for k,v in (current or {}).items() if k not in self.RETIRED_SETTINGS}
        if self.recovered or cleaned != (current or {}) or self.values.model_dump() != (current or {}):
            self.db.replace_settings(self.values.model_dump(), previous if previous != self.values.model_dump() else None)
        if self.values.llm_base_url == "http://127.0.0.1:11434/v1" and not self.values.llm_model:
            self.update({"llm_base_url":"https://api.xkiro.com/v1","llm_model":"minimax/minimax-m3:free"})
        elif self.values.llm_base_url == "https://api.groq.com/openai/v1":
            self.update({"llm_base_url":"https://api.xkiro.com/v1"})

    @staticmethod
    def _parse(raw):
        if not isinstance(raw,str) or not raw.strip():return None
        try:value=json.loads(raw)
        except (json.JSONDecodeError,TypeError):return None
        return value if isinstance(value,dict) else None

    @classmethod
    def _validate(cls,value):
        if value is None:return None
        cleaned={k:v for k,v in value.items() if k not in cls.RETIRED_SETTINGS}
        try:return Settings.model_validate(cleaned)
        except ValueError:return None

    def update(self, changes: dict) -> Settings:
        # Ignore retired voice keys from stale UI/exported settings rather than
        # reintroducing them or making a whole settings import fail.
        changes = {k: v for k, v in changes.items() if k not in self.RETIRED_SETTINGS}
        candidate = Settings.model_validate({**self.values.model_dump(), **changes})
        self.db.save_settings(candidate.model_dump())
        self.values = candidate
        return candidate

    def reset(self, key: str | None = None) -> Settings:
        defaults = Settings().model_dump()
        if key is not None and (key not in defaults or key == "schema_version"):
            raise ValueError("Unknown setting")
        return self.update({key: defaults[key]} if key else defaults)
