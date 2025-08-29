Grok CLI Bridge

Quick wrapper to call xAI Grok via an OpenAI‑compatible chat completions API.

Files
- `bin/grok-chat`: wrapper to run the client
- `scripts/grok_chat.py`: Python client

Config (env vars)
- `GROK_API_KEY` (required): your xAI API key
- `GROK_API_BASE` (default `https://api.x.ai/v1`)
- `GROK_MODEL` (default `grok-code-fast-1`)
- `GROK_SYSTEM` (optional): system prompt

Examples
- One‑off: `GROK_API_KEY=… bin/grok-chat "Hello"`
- Specify base/model: `GROK_API_KEY=… bin/grok-chat -b https://api.x.ai/v1 -m grok-code-fast-1 "Hello"`
- Raw JSON: `GROK_API_KEY=… bin/grok-chat --json "Hello"`

Security notes
- Prefer ephemeral env vars; avoid writing secrets to disk.
- This repo does not store your key; the script only reads from env/flags.
- If you want a persisted setup, create a local, untracked `.env.local` and export it in your shell. Do not commit it.

