Unified AI CLI

This repo includes a small, dependency‑free CLI to call:
- xAI Grok (OpenAI‑compatible)
- Google Gemini (latest models)
- Anthropic Claude

Binaries
- `bin/ai-chat`: unified entrypoint (choose provider)
- `bin/grok-chat`: xAI shortcut (existing)
- `bin/gemini-chat`: Google shortcut
- `bin/anthropic-chat`: Anthropic shortcut

Env vars
- Common
  - `AI_PROVIDER` (optional): default provider for `bin/ai-chat`
  - `AI_SYSTEM` (optional): system instruction
  - `AI_TEMPERATURE` (default `0.2`), `AI_MAX_TOKENS` (default `1024` for Anthropic)
- xAI (Grok)
  - `GROK_API_KEY` or `XAI_API_KEY` (required for xAI)
  - `GROK_API_BASE` or `XAI_API_BASE` (default `https://api.x.ai/v1`)
  - `GROK_MODEL` or `XAI_MODEL` (default `grok-code-fast-1`)
- Google (Gemini)
  - `GOOGLE_API_KEY` or `GEMINI_API_KEY` (required for Google)
  - `GOOGLE_API_BASE` or `GEMINI_API_BASE` (default `https://generativelanguage.googleapis.com/v1beta`)
  - `GOOGLE_MODEL` or `GEMINI_MODEL` (default `gemini-1.5-pro-latest`)
- Anthropic (Claude)
  - `ANTHROPIC_API_KEY` (required for Anthropic)
  - `ANTHROPIC_API_BASE` (default `https://api.anthropic.com/v1`)
  - `ANTHROPIC_MODEL` (default `claude-opus-4-1-20250805`)
  - `ANTHROPIC_VERSION` (default `2023-06-01`)

Usage
- Unified: `AI_PROVIDER=xai bin/ai-chat -m grok-code-fast-1 "Hello"`
- xAI: `GROK_API_KEY=… bin/grok-chat "Hello"`
- Google: `GOOGLE_API_KEY=… bin/gemini-chat -m gemini-1.5-pro-latest "Hello"`
- Anthropic: `ANTHROPIC_API_KEY=… bin/anthropic-chat -m claude-opus-4-1-20250805 "Hello"`

Notes
- No SDK dependencies; pure HTTPS via Python stdlib.
- The CLI prints plain text by default; add `--json` to see raw responses.
- System instruction is supported for all providers.
