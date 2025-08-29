from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid
from datetime import datetime


@dataclass
class Job:
    id: str
    kind: str
    payload: Dict[str, Any]
    status: str = "queued"  # queued|running|done|error|canceled
    result: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class InMemoryJobs:
    def __init__(self) -> None:
        self._store: Dict[str, Job] = {}

    def submit(self, kind: str, payload: Dict[str, Any]) -> Job:
        jid = uuid.uuid4().hex[:12]
        job = Job(id=jid, kind=kind, payload=payload, status="queued")
        self._store[jid] = job
        return job

    def get(self, jid: str) -> Optional[Job]:
        return self._store.get(jid)

    def cancel(self, jid: str) -> Optional[Job]:
        job = self._store.get(jid)
        if not job:
            return None
        if job.status in ("done", "error", "canceled"):
            return job
        job.status = "canceled"
        return job


# TODO: Wire this into an HTTP layer (e.g., FastAPI/Flask) in a later iteration.
# For now, provide simple helpers that a future server layer can call.
jobs = InMemoryJobs()


def submit_job(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    j = jobs.submit(kind, payload)
    return {"id": j.id, "status": j.status, "kind": j.kind}


def get_job(jid: str) -> Dict[str, Any]:
    j = jobs.get(jid)
    if not j:
        return {"error": "not_found"}
    return {"id": j.id, "status": j.status, "result": j.result}


def cancel_job(jid: str) -> Dict[str, Any]:
    j = jobs.cancel(jid)
    if not j:
        return {"error": "not_found"}
    return {"id": j.id, "status": j.status}

