Structured Logging

Purpose
- Provide consistent, machine‑parseable JSON logs for agent calls, tool calls, arbiter decisions, and system events.

Fields
- ts: ISO8601 UTC timestamp (e.g., 2025-01-01T12:00:00.000Z)
- level: one of DEBUG, INFO, WARN, ERROR
- event: short event key (e.g., agent_call, tool_call, breaker_open)
- message: optional human message (short)
- corr_id: correlation ID for a swarm run
- agent: agent display name (e.g., Grok, Gemini, Claude)
- provider: xai | google | anthropic
- model: model identifier used by the agent
- ms: integer duration in milliseconds (when applicable)
- error: error string (when applicable)

Examples
{
  "ts": "2025-01-01T12:00:00.000Z",
  "level": "INFO",
  "event": "agent_call",
  "agent": "Gemini",
  "provider": "google",
  "model": "gemini-1.5-pro-latest",
  "corr_id": "abc123def456",
  "ms": 842
}

{
  "ts": "2025-01-01T12:00:01.000Z",
  "level": "ERROR",
  "event": "tool_error",
  "agent": "Claude",
  "provider": "anthropic",
  "corr_id": "abc123def456",
  "error": "rate_limited",
  "message": "fs_read exceeded limit"
}

Usage
- Emitted via src/logging/structured.py helpers: info(), warn(), error().
- Always include corr_id for cross‑component tracing.
- Keep messages short; prefer structured fields for details.

Recommendations
- Prefer INFO for normal operations; WARN for recoverable anomalies; ERROR for failures.
- Include ms for any operation with meaningful duration.
- Avoid logging secrets or full payloads; log types and sizes instead.

Code Snippets (Python)
from src.logging.structured import info, warn, error

corr_id = "abc123def456"
info("agent_call", agent="Gemini", provider="google", model="gemini-1.5-pro-latest", ms=842, corr_id=corr_id)
warn("breaker_open", agent="Grok", provider="xai", fails=2, corr_id=corr_id)
error("tool_error", tool="fs_read", error="rate_limited", corr_id=corr_id, message="Exceeded per-agent rate limit")

Testing Notes
- Unit test that log records are valid JSON with required fields.
- Validate timestamps (ISO8601), levels, and presence of corr_id.
- Avoid brittle string comparisons; parse JSON and assert on keys.
