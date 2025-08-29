# Multi‑Provider AI CLI + Swarm Orchestrator

A lightweight toolkit to call xAI Grok, Google Gemini, and Anthropic Claude from the command line, plus a multi‑agent "swarm" orchestrator for coordinated problem solving. Includes an optional minimal HTTP server exposing a job API and an OpenAI‑compatible `/v1/chat/completions` endpoint.

## Binaries
- `bin/ai-chat` — Unified client (providers: xai, google, anthropic)
- `bin/grok-chat` — xAI shortcut
- `bin/gemini-chat` — Google shortcut
- `bin/anthropic-chat` — Anthropic shortcut
- `bin/ai-swarm` — Multi‑agent orchestrator

## Quick Start
1) Export keys (use ephemeral env vars; do not commit secrets):
```
export GROK_API_KEY=...
export GOOGLE_API_KEY=...
export ANTHROPIC_API_KEY=...
```
2) Call a model:
```
bin/ai-chat -p anthropic -m claude-opus-4-1-20250805 "Hello"
```
3) Run a 2‑round swarm (read‑only):
```
bin/ai-swarm --rounds 2 "Plan a feature and risks"
```

## Config
- `config/agents.json` — defaults for models/bases and limits (rate limits, timeouts, circuit breaker)
- CLI flags: `--only`, `--disable`, `--config`, `--allow-write`

## Tools & Orchestrator
- See `docs/tools.md` for available tools (fs_*, ctx_*, coord_*), shared findings schema, and rate‑limit transparency.
- See `docs/swarm.md` for swarm behavior.
- See `docs/ai.md` and `docs/grok.md` for clients.
- See `docs/logging.md` for structured logs and examples.
- See `docs/coordinator_api.md` for the minimal API and error schema.

## Minimal Server
- Optional FastAPI server in `src/coordination/server.py`:
  - Job endpoints: `POST/GET/DELETE /v1/jobs`
  - OpenAI‑compatible chat: `POST /v1/chat/completions` (routes to providers by model hint)

## Development
- No external SDKs required for CLI; uses Python stdlib HTTP.
- Keep secrets in environment only.
- Rate limits and timeouts are configurable; per‑agent buckets reduce noisy‑neighbor issues.

## Safety
- Swarm writes are gated by an arbiter and require `--allow-write`.
- Paths are sanitized; writes are confined to the workspace.

## License
- Add a license of your choice before publishing (MIT/Apache‑2.0 recommended).

