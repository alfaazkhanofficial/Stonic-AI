"""Model router: picks the model and reasoning effort for each agent step, with a fallback chain.

Profiles, fastest first: ``fast`` (routine steps) -> ``strong`` (planning, recovery, summaries) -> ``main`` (the provider
configured under AI & Providers, xKiro by default). Fast/strong use an OpenAI-compatible endpoint (Gemini by default) and need
explicit consent because requests leave for that provider. Nothing here names a vendor other than through settings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from stonic.config.settings import Settings
from stonic.providers.llm import GEMINI_HOST

GEMINI_KEY_ENDPOINT = "https://generativelanguage.googleapis.com"   # where VoiceService stores the Gemini key
PURPOSE_PROFILE = {"step": "fast", "plan": "strong", "reflect": "strong", "summarize": "fast"}
PURPOSE_EFFORT = {"step": "low", "plan": "medium", "reflect": "medium", "summarize": "minimal"}


@dataclass(frozen=True)
class Route:
    profile: str                 # fast | strong | main
    settings: Settings
    reasoning: str | None


class ModelRouter:
    def __init__(self, provider, credentials=None) -> None:
        self.provider, self.credentials = provider, credentials

    # -- credentials -------------------------------------------------------------------------------------------------
    def _agent_key(self, settings: Settings) -> str:
        host = urlsplit(settings.agent_base_url).hostname
        try:
            if self.credentials is not None:
                saved = self.credentials._load().get(GEMINI_KEY_ENDPOINT if host == GEMINI_HOST else settings.agent_base_url, "")
                if saved:
                    return saved
        except (OSError, ValueError, UnicodeError, AttributeError):
            pass
        if host == GEMINI_HOST:
            return os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        return os.environ.get("STONIC_AGENT_API_KEY", "")

    def _register(self, settings: Settings) -> None:
        resolvers = getattr(self.provider, "resolvers", None)
        if resolvers is not None:
            resolvers[settings.agent_base_url] = lambda s=settings: self._agent_key(s)

    # -- availability ------------------------------------------------------------------------------------------------
    def fast_available(self, settings: Settings) -> bool:
        return bool(settings.agent_fast_consent and settings.agent_fast_model and self._agent_key(settings))

    def main_available(self, settings: Settings) -> bool:
        return bool(hasattr(self.provider, "act") and hasattr(self.provider, "available") and self.provider.available(settings))

    def usable(self, settings: Settings) -> bool:
        return bool(settings.agent_enabled and hasattr(self.provider, "act") and (self.fast_available(settings) or self.main_available(settings)))

    def description(self, settings: Settings) -> str:
        if self.fast_available(settings):
            return f"fast={settings.agent_fast_model}, strong={settings.agent_strong_model}, fallback=main"
        return "main provider only" if self.main_available(settings) else "unavailable"

    # -- routing -----------------------------------------------------------------------------------------------------
    def route(self, settings: Settings, purpose: str = "step", *, skip: frozenset[str] = frozenset()) -> Route | None:
        """First profile in the chain that is available and not in ``skip`` (profiles that already failed this goal)."""
        wanted = PURPOSE_PROFILE.get(purpose, "fast")
        chain = [wanted] + [p for p in ("fast", "strong") if p != wanted] + ["main"]
        effort = PURPOSE_EFFORT.get(purpose, "low")
        for profile in chain:
            if profile in skip:
                continue
            if profile == "main":
                if self.main_available(settings):
                    return Route("main", settings, None)
                continue
            if not self.fast_available(settings):
                continue
            model = settings.agent_fast_model if profile == "fast" else (settings.agent_strong_model or settings.agent_fast_model)
            self._register(settings)
            routed = settings.model_copy(update={"llm_base_url": settings.agent_base_url, "llm_model": model})
            return Route(profile, routed, effort)
        return None
