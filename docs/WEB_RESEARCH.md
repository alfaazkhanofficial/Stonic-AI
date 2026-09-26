# Web research

## What changed and why

Web intelligence used to ask the model provider to browse: it sent `tools: [{"type": "browser_search"}]` and read
`executed_tools` from the reply. That is a Groq-only feature. xKiro (the configured provider) documents function
tools only and has no built-in browsing, so every research request failed with "check your xKiro API key".

Search now happens on this PC and the model only writes the answer:

1. `stonic/providers/websearch.py` runs a keyless metasearch (`ddgs`, which queries several engines and merges results).
2. The top pages are fetched (3 in quick mode, 5 otherwise) and reduced to readable text.
3. The model gets the numbered sources as untrusted data and writes a cited answer from them alone.
4. `sources` in the result are exactly the pages retrieved. No results, or a failed search, means a plain failure:
   the model is never asked to answer from memory.

## Safety

* Result URLs are untrusted. A page is fetched only if it is http(s) on port 80/443, has no credentials in the URL,
  is not a local name, and resolves ONLY to public addresses, checked again at every redirect hop (max 3).
  Localhost, private LAN, link-local and cloud-metadata addresses are never requested.
* Pages are size-capped (500 KB), read as text only (HTML/plain), 7 s timeout, scripts and page chrome stripped.
* Page text can only appear inside the data message, never in the instruction message.

## Privacy

Your query goes to the search engines, and the pages read see this PC's IP address (as any browser visit would).
The retrieved text and your question go to the model provider to write the answer.

## Failure messages

The message now says what failed: search unreachable (network/VPN/firewall), no results, provider key rejected
(401/403), quota (402/429), provider timeout, or a missing key. Details are in the Logs panel.

## Verify on your PC

    python scripts/websearch-check.py --data-dir C:\STONIC_V2\data

It tests the search half (no key) and the provider half (your saved key and model) separately.

## Limits

Keyless search engines rate-limit and occasionally change their pages; if search reports "could not be reached" while
your internet works, wait a minute and retry. Nothing here was run against live search engines during development
(offline sandbox): behaviour against them is covered by mocked tests only.
