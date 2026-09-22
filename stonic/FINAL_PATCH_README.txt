STONIC FINAL PATCH — NO VOICE + xKiro RELIABILITY

1. Close STONIC completely.
2. Extract this ZIP directly into C:\Stonic and choose Replace files in destination.
3. Double-click APPLY-STONIC-FINAL-FIX.cmd.
4. When it reports success, launch Start-Stonic.cmd.

What this final patch does:
- Removes the complete voice/listening/STT/TTS subsystem and its models/dependencies.
- Removes voice API routes, settings, UI controls, startup lifecycle and packaging assets.
- Keeps text chat, xKiro, web research, vision, tools, memory, tasks and PC control.
- Keeps the saved xKiro key cached after a successful DPAPI load/save.
- Distinguishes provider outages/rate limits/free-token exhaustion from a missing key.
- Checks xKiro /v1/usage when needed and reports daily free-token exhaustion clearly.
- Handles xKiro mid-stream SSE error frames so truncated responses are not treated as success.
- Uses MiniMax M3 Free reasoning values supported by xKiro (disabled/adaptive).
- Keeps web/vision on the model configured by the user instead of silently switching models.

Do not put your real API key in bug reports or screenshots.
