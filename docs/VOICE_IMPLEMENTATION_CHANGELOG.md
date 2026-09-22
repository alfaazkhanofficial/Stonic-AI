# STONIC V2 Fresh Voice Implementation Changelog

## 2026-09-20

Implemented the fresh voice subsystem from the final voice specification without redesigning unrelated STONIC systems.

### Architecture
- Added `VoiceController` with explicit lifecycle/state machine and unique per-start voice session generations.
- Added `AudioManager` as the single microphone owner with bounded audio buffering and 16 kHz normalization.
- Added Silero VAD segmentation with pre-roll/post-roll configuration.
- Added Nemotron streaming STT with a bounded Faster-Whisper fallback.
- Added local Supertonic TTS with sentence-level response chunking.
- Added interruptible playback, barge-in handling and layered echo gating.
- Added cancellation and stale-session protection through the voice pipeline.

### STONIC Integration
- Voice transcripts enter the existing `CoreService.chat()` intelligence/tool/permission path.
- Voice Stop AI cancels only voice-owned intelligence work and does not inject a global “Generation stopped.” chat message.
- Voice errors remain isolated from chat.
- Start AI / Stop AI are backed by the real voice state instead of a visual-only toggle.
- Voice status is observable through `/api/voice/status` and SSE `voice_status` events.

### Verification
- Python test suite: 58 passed, 2 skipped.
- Added fresh voice regression/unit coverage for state transitions, session generation, transcript normalization and speech chunking.
- Added `scripts/setup-voice.py` and `scripts/verify-voice.py`.
- Packaged Windows validation remains a target-hardware acceptance gate because microphone, speaker-mode echo, STT/TTS model availability and measured latency cannot be certified from this code-only environment.
