Coordinator API (MVP)

Scope
- Minimal job lifecycle endpoints to coordinate agent work.
- Synchronous MVP; no background processing or persistence guaranteed.

Base Path
- /v1

Endpoints
- POST /v1/jobs
  - Purpose: Submit a job request
  - Request JSON:
    { "kind": "string", "payload": {"any": "json"} }
  - Responses:
    - 201: { "id": "string", "status": "queued", "kind": "string" }
    - 400: { "error": "invalid_request" }
    - 429: { "error": "rate_limited", "limit": n, "remaining": n, "reset_sec": n }

- GET /v1/jobs/{id}
  - Purpose: Retrieve job status/result
  - Responses:
    - 200: { "id": "string", "status": "queued|running|done|error|canceled", "result": {"any": "json"} }
    - 404: { "error": "not_found" }

- DELETE /v1/jobs/{id}
  - Purpose: Cancel a running/queued job
  - Responses:
    - 200: { "id": "string", "status": "canceled" }
    - 404: { "error": "not_found" }

Authentication (placeholder)
- Add an Authorization: Bearer <token> header check for non‑local deployments.
- Return 401 on missing/invalid token.

Rate Limiting
- Return 429 with transparency fields: limit, remaining, reset_sec, scope.

Notes
- This MVP pairs with src/coordination/api.py which provides an in‑process stub backing store and helpers.
- Future: OpenAPI spec, async execution, durable store, and pagination for job listings.

Error Schema and Status Codes
- Standard error shape for error responses:
  { "error": "string", "code": 4xx|5xx, "message": "optional short description" }
- Common statuses:
  - 200 OK, 201 Created
  - 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict, 429 Too Many Requests
  - 500 Internal Server Error

Sequence (ASCII)
Client -> Coordinator: POST /v1/jobs {kind,payload}
Coordinator -> (Internal) enqueue + log -> agent workflow
Agents -> Tools: read/search/write with telemetry + logs
Arbiter -> Coordinator: consensus/updates (future)
Client -> Coordinator: GET /v1/jobs/{id} -> {status,result}

Testing Strategy
- Unit tests: src/coordination/api.py submit/get/cancel behavior; id uniqueness; state transitions.
- Integration tests: (optional) HTTP server wrapper for endpoints; verify JSON schemas and status codes.
- Error tests: invalid payloads (400), unknown IDs (404), unauthorized (401/403 placeholder), rate limited (429).
- Logging tests: verify request/response logging contains corr_id and required fields (see logging.md).

Versioning
- Prefix all endpoints with /v1; plan deprecation policy before introducing /v2 breaking changes.
- Maintain compatibility window and document migration steps.

Optional HTTP Server
- A minimal FastAPI server is provided in src/coordination/server.py to expose these endpoints for local testing.
- Start (after installing deps):
  uvicorn src.coordination.server:app --reload --port 8080
