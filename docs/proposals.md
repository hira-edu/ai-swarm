Improvement Proposal Schema

Purpose
- Standardize how agents propose improvements in read-only rounds without writing files directly.

Schema
{
  "type": "proposal",
  "items": [
    {
      "area": "coordination|observability|safety|docs|testing|server",
      "change": "short actionable description",
      "rationale": "brief reason or risk addressed"
    }
  ]
}

Example
{
  "type": "proposal",
  "items": [
    {
      "area": "coordination",
      "change": "Add task lease heartbeat to extend active leases",
      "rationale": "Avoids orphaned tasks expiring mid-execution"
    },
    {
      "area": "observability",
      "change": "Emit rate-limit remaining/reset in structured logs",
      "rationale": "Helps tune limits and diagnose throttling"
    }
  ]
}

Tool Call Examples
- Read before write
  { "tool_calls": [ { "name": "fs_read", "args": { "path": "docs/proposals.md" } } ] }

- Write a small, safe change (full content)
  { "tool_calls": [ { "name": "fs_write", "args": { "path": "docs/proposals.md", "content": "<entire updated file content>", "create_dirs": true, "allow_overwrite": true } } ] }
