# Voice

STONIC talks and listens through Google's **Gemini Live** (speech in, speech out). Gemini Live is only the
mouth and ears: every real request is handed to STONIC's own pipeline (`CoreService.chat`), so voice goes through
the same planner, permission gate, verification and audit trail as typing.

## Turning it on

1. **Settings → Privacy → Allow cloud voice.** While voice is on, microphone audio is streamed to Google.
   Nothing is sent while voice is off or muted. (The microphone button asks for this the first time.)
2. **Settings → Voice → Gemini API key** (create one at aistudio.google.com/apikey). It is stored with Windows
   user-bound encryption, separately from the intelligence-provider key, and never leaves the backend. The
   `GEMINI_API_KEY` environment variable also works. The provider's key is never sent to Google.
3. Press the **microphone button** beside the message box. Press again to stop.

Optional: **Start voice when STONIC opens** (Settings → Voice), a **push-to-talk** key, **Interrupt by speaking**.

## Controls

| Control | What it does |
|---|---|
| Microphone button | Start / stop voice |
| Mute | Closes the microphone device entirely (the Windows mic indicator goes off) and tells Google the audio stopped |
| Stop speaking | Silences STONIC within about one audio buffer and cancels a spoken request that is still running |
| Push-to-talk | Settings → Voice. Hold Ctrl+Space / Ctrl+Alt+Space / F8 / F9 (global on Windows), or hold the on-screen HOLD button. While not held, no audio leaves the PC |
| Idle stop | Optional: stop listening after N minutes without speech |

The orb swells with the sound actually being spoken or heard.

## How a spoken request works

```
microphone → (echo guard) → Gemini Live ──► small talk answered directly
                                   │
                                   └─ ask_stonic("…") ─► CoreService.chat ─► planner → permission gate → tools → verify
                                                                 │
speakers ◄── Gemini Live speaks the verified reply ◄────────────┘
```

* Casual conversation (greetings, clarifications) is answered by the voice model and saved like typed chat.
* Everything else, including any question needing facts, the PC, memory, files or web, calls `ask_stonic`.
  The model is told never to claim something happened unless `ask_stonic` returned `ok`.
* **Approvals are UI-only.** If an action needs approval the model says so; approving happens in Task activity.
  Voice cannot approve anything, by design (a spoken "yes" cannot be bound to the exact inputs the approval covers).
* A spoken request appears in the chat panel as a normal user/assistant exchange.

## Echo: STONIC hearing itself

The microphone stays open, so the assistant would hear its own voice. `stonic/voicelive/echo.py` decides, block
by block, whether what the microphone heard is explained by what was just played (delayed, coloured by your
speakers and room) or is something else. It learns your room while STONIC talks. Uses:

* **After-speech tail** (always on): for a moment after each reply (measured output latency + 250 ms) blocks
  explained as echo are dropped, but a person answering immediately is heard.
* **Interrupt by speaking** (Settings → Voice, default **Off**): talk over STONIC to stop it. Only active where
  the guard has learned the room and judges echo and voices separable; the panel says when it is not.
  Run `python scripts/voicelive-calibrate.py` on your PC to see whether your room qualifies.
* Headsets/headphones make all of this unnecessary (the microphone does not hear the speakers).

Honest limits: this is signal processing tested on simulated rooms. Very reverberant or noisy rooms, a quiet
talker against loud playback, or a microphone right next to the speaker can defeat it. Failure modes are
conservative: worst case the first fraction of a second of an instant reply is missed, or you use the Stop button.

## Settings (Settings → Voice / Privacy)

| Setting | Default | Notes |
|---|---|---|
| Allow cloud voice (`voice_cloud_consent`) | off | Required to start |
| Start voice when STONIC opens | off | Needs consent + key |
| Voice | Charon | Applies next time voice starts |
| Live model | `gemini-3.8-live` | Any Gemini Live model id, e.g. `gemini-3.1-flash-live-preview` |
| Microphone / Speaker | system default | Exact device name; an unavailable one falls back to the default and says so |
| Push-to-talk | off | |
| Interrupt by speaking | off | `guarded` uses the echo guard |
| Pause before STONIC replies | 650 ms | Server-side end-of-speech silence; 500–800 suits most people |
| Stop after idle minutes | 0 (never) | |

Voice, model, devices and pause length apply the next time voice starts; push-to-talk, interrupt mode and idle
stop apply immediately.

## Reliability

* Setup fields the model may not accept (VAD tuning, the explicit tool behaviour) are dropped one tier at a time
  if the server rejects them, then it reconnects.
* Connections renew automatically (Gemini Live sessions are short); context is carried over with a resumption
  handle kept in memory only. Reconnects back off 3 s → 60 s. A refused key stops retrying and says so;
  quota exhaustion waits longer.
* If the chosen microphone/speaker will not open, the system default is used and a notice is logged.
* Diagnostics shows a **Voice (Gemini Live)** check once you have engaged with voice (consent or key). A text-only
  install is unchanged.

## Privacy and safety model

* Audio goes to Google only while voice is on, unmuted (and, in push-to-talk mode, while the key is held).
  Audio is not stored by STONIC. Conversation text is stored only if "save conversations" is on, as for typing.
  How Google handles API audio depends on your Gemini plan; check its terms before using voice for sensitive material.
* Always-listening voice means **anything the microphone hears can become a request**: other people, or audio
  playing from your own speakers. STONIC's protections still apply (permission gate, approvals only in the UI),
  but for sensitive work prefer push-to-talk or a headset, or mute.
* The Gemini key is DPAPI-encrypted, kept per endpoint, excluded from exports, never returned by the API and never
  logged. The backend, not the browser, talks to Google. The renderer never touches the microphone.

## Verifying on your machine

```
python scripts/voicelive-check.py --play       # real connection to Google; speaks a sentence back
python scripts/voicelive-calibrate.py          # your microphone + speakers: can echo be told from your voice?
python scripts/voicelive-calibrate.py --list   # device names
```

## Code map

`stonic/voicelive/`: `service.py` (lifecycle, routing, state, SSE, `ask_stonic` bridge), `live.py` (Gemini Live
session), `audio.py` (devices, capture, callback-driven playback), `echo.py` (echo guard), `controls.py`
(push-to-talk), `persona.py` (what the voice model is told), `routes.py` (`/api/voice/*`, behind the same token).
UI: `ui/components/VoiceControl.tsx`, `VoiceSettings.tsx`, `ui/voiceStore.ts`, `ui/voice.css`. Tests:
`tests/test_voicelive_*.py` with scripted fakes for Google and the sound card.

The package is deliberately not named `stonic/voice`: `Setup-Stonic.cmd` and `APPLY-STONIC-FINAL-FIX.cmd` delete
that path (legacy cleanup).

## Attribution

The overall shape (speech-to-speech session, echo handling, push-to-talk, resumption) follows ideas seen in the
open-source Mark LIV project (CC BY-NC 4.0). No code was copied; this implementation is written from scratch.
