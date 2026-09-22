STONIC xKiro Streaming Fix
==========================

Fixes the chat-generation failure where AI & Providers reports that xKiro,
the saved key, selected model, and free-token allowance are healthy, but a
normal message fails before streaming begins.

Root cause:
stonic/providers/llm.py called response.json() from check_response() on an
httpx streaming 200 response before its body had been read. httpx raises
ResponseNotRead in that situation, so STONIC aborted a perfectly healthy
/v1/chat/completions SSE stream before reading the first token.

Install:
1. Close STONIC completely.
2. Extract this ZIP into C:\Stonic and replace the existing file.
3. Start STONIC. No dependency sync, model download, or setup script is needed.

Changed file:
stonic/providers/llm.py
