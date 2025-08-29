Swarm Tools Schema

Agents can request tools by returning a JSON object (standalone or inside a ```json fenced block) with a `tool_calls` list. The orchestrator executes read‑only tools immediately and queues write proposals for arbiter approval. If `--allow-write` is passed, approved writes are applied.

JSON envelope
{
  "tool_calls": [
    {"name": "fs_list", "args": {"dir": ".", "pattern": "py$", "max_results": 200}},
    {"name": "fs_read", "args": {"path": "scripts/ai_swarm.py", "max_bytes": 50000}},
    {"name": "search_text", "args": {"pattern": "def main", "dir": "scripts", "max_matches": 50}},
    {"name": "fs_write", "args": {"path": "docs/notes.md", "content": "Hello", "create_dirs": true}}
  ]
}

Tools
- fs_list: list files
  - args: `dir` (default "."), `pattern` (glob by default; use `regex:` prefix for regex), `max_results` (default 200)
  - result: JSON with `files[]` and `count`

- fs_read: read file content
  - args: `path` (required), `max_bytes` (default 50000)
  - result: JSON with `path`, `bytes`, `content`

- search_text: regex search across files
  - args: `pattern` (required), `dir` (default "."), `max_matches` (default 200)
  - result: JSON with `matches[]` entries `{file, line, text}`

- fs_write: write file (proposal; requires arbiter approval)
  - args: `path` (required), `content` (required), `create_dirs` (default true)
  - processing: queued; arbiter receives proposals and responds with STRICT JSON:
    {
      "decisions": [
        {"path": "docs/notes.md", "action": "approve", "notes": "ok"}
      ]
    }
  - application: applied only when `--allow-write` is passed; result is reported to transcript

Shared Context
- ctx_put: store a value in shared context
  - args: `key` (string), `value` (any JSON), `mode` (optional: `set`|`if_absent`|`if_version`), `expected_version` (int for if_version)
  - result: `{ ok, key, version }` (or `{ ok:false, error:"version_mismatch", version }`)
- ctx_get: retrieve a value from shared context
  - args: `key` (string)
  - result: `{ key, value, version }`
- ctx_keys: list context keys
  - args: `prefix` (optional string)
  - result: `{ keys: [ ... ] }`

Quick example (ctx)
- Publish finding:
  { "tool_calls": [ { "name": "ctx_put", "args": { "key": "Gemini.list_code_files", "value": { "ok": true, "task": "list_code_files", "data": ["scripts/ai_swarm.py"], "ts": "2025-01-01T12:00:00Z", "agent": "Gemini" } } } ] }
- Discover keys:
  { "tool_calls": [ { "name": "ctx_keys", "args": { "prefix": "Gemini." } } ] }
- Retrieve:
  { "tool_calls": [ { "name": "ctx_get", "args": { "key": "Gemini.list_code_files" } } ] }

Coordinator Queue (MVP)
- coord_enqueue: enqueue a work item for agents
  - args: `kind` (string), `payload` (object)
  - result: `{ enqueued: true, id, kind }`
- coord_next: get next queued item (FIFO)
  - args: `lease_sec` (optional; default 180)
  - result: `{ item: { id, kind, payload, lease_until, claimed_by } | null }`
- coord_status: peek queue state
  - args: none
  - result: `{ length: number, front: {id,kind,payload,status}|null, counts: {queued,claimed,done}, phase: number }`
- coord_claim: claim a specific task id (with lease)
  - args: `id` (string), `lease_sec` (optional)
  - result: `{ id, kind, lease_until, claimed_by }` or `{ error, code }`
- coord_complete: mark a task done
  - args: `id` (string), `result` (any JSON)
  - result: `{ id, status: "done" }` or `{ error, code }`
- coord_extend: extend lease for claimed task
  - args: `id` (string), `extend_sec` (int)
  - result: `{ id, lease_until }` or `{ error, code }`

Quick example (coord)
- Enqueue:
  { "tool_calls": [ { "name": "coord_enqueue", "args": { "kind": "scan_docs", "payload": { "dir": "docs" } } } ] }
- Claim next (180s lease):
  { "tool_calls": [ { "name": "coord_next", "args": { "lease_sec": 180 } } ] }
- Complete:
  { "tool_calls": [ { "name": "coord_complete", "args": { "id": "<task_id>", "result": { "ok": true } } } ] }

Shared Findings Schema (convention)
- When storing findings in shared context via `ctx_put`, use this shape for consistency:
  { "ok": true|false, "task": "string", "data": <any JSON>, "ts": ISO8601, "agent": "Grok|Gemini|Claude" }
- Key naming: `AgentName.task`, e.g., `Gemini.list_code_files`, to avoid conflicts.
- Use `ctx_keys` then `ctx_get` to consolidate findings across agents.

Barriers and Phases
- Orchestrator sets `phase` in shared context per round.
- Optionally, agents can set/read `phase_ready` to coordinate progression across rounds.

Improvement Proposal Schema (read-only rounds)
{ "type": "proposal", "items": [ { "area": "coordination|observability|safety", "change": "string", "rationale": "string" } ] }

Best practices for agents
- Always include a short free‑text rationale in your normal output in addition to tool_calls JSON.
- Prefer small, targeted reads/searches first; propose writes only after consensus.
- When proposing writes, include full file content you want on disk (not a diff).

Rate‑Limit Transparency
- Tools enforce per‑tool, per‑agent token buckets. When a request is rate‑limited, responses include fields to help clients back off:
  - error: "rate_limited"
  - code: 429
  - tool: tool name
  - limit: tokens allowed in the window
  - remaining: tokens left in the current window
  - reset_sec: seconds until tokens reset
  - scope: agent name (rate‑limit scope)

Example (rate‑limited)
{
  "error": "rate_limited",
  "code": 429,
  "tool": "fs_read",
  "limit": 30,
  "remaining": 0,
  "reset_sec": 12,
  "scope": "Gemini"
}
