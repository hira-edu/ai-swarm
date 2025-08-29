AI Swarm (Multi‑Agent Orchestrator)

Runs Grok (xAI), Gemini (Google), and Claude (Anthropic) in rounds, lets them see a shared transcript, and asks an arbiter to synthesize consensus.

CLI
- `bin/ai-swarm "Your task here"`

Behavior
- Each round: all agents read the recent transcript and post analysis, steps, risks, decision.
- Arbiter (default Claude) reads the round outputs and returns a concise consensus sectioned as Summary, Plan, Suggestions, Risks, Decision.
- The transcript is preserved across rounds to simulate shared visibility.

Config
- Rounds: `--rounds N` (default 2)
- Providers: limit via `--only xai google anthropic`
- Arbiter: `--arbiter anthropic|xai|google`, `--arbiter-model ...`
- Temperature: `--temperature 0.2`
- Provider overrides: `--xai-...`, `--google-...`, `--anthropic-...`
- Config file: `--config config/agents.json` (optional). Example included with models, bases, and circuit-breaker limits.

Keys (env)
- xAI: `GROK_API_KEY` or `XAI_API_KEY`
- Google: `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`

Examples
- Minimal: `GROK_API_KEY=… GOOGLE_API_KEY=… ANTHROPIC_API_KEY=… bin/ai-swarm "Draft a migration plan"`
- Anthropic arbiter: `SWARM_ARBITER=anthropic bin/ai-swarm --rounds 3 "Design an API"`
- Google‑only: `GOOGLE_API_KEY=… bin/ai-swarm --only google "Brainstorm approaches"`

Notes
- No keys are written to disk; the tool reads from env or flags.
- No SDKs; it uses HTTPS via stdlib. Responses are printed as they arrive per round.
- Tool caching and circuit breakers reduce redundant work and isolate failing agents.
