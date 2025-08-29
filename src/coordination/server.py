try:
    from fastapi import FastAPI, HTTPException, Header
    from fastapi.responses import JSONResponse
except Exception as e:  # pragma: no cover
    # Minimal shim so importing this module doesn't explode without FastAPI
    FastAPI = None  # type: ignore

from typing import Optional, List, Dict, Any
from .api import submit_job, get_job, cancel_job
import sys
from pathlib import Path

# Make scripts/ importable for provider clients
_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
try:
    from ai_chat import call_xai, call_google, call_anthropic, extract_text, get_default_base, get_default_model, get_api_key
except Exception:
    call_xai = call_google = call_anthropic = extract_text = get_default_base = get_default_model = get_api_key = None  # type: ignore


def require_auth(authorization: Optional[str]) -> None:
    # Placeholder: accept missing auth for local; reject obvious junk
    if authorization is None:
        return
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "code": 401})


if FastAPI is not None:
    app = FastAPI(title="Coordinator API", version="1.0.0")

    @app.post("/v1/jobs")
    def post_job(body: dict, authorization: Optional[str] = Header(default=None)):
        require_auth(authorization)
        kind = body.get("kind")
        payload = body.get("payload") or {}
        if not isinstance(kind, str):
            raise HTTPException(status_code=400, detail={"error": "invalid_request", "code": 400})
        resp = submit_job(kind, payload if isinstance(payload, dict) else {})
        return JSONResponse(status_code=201, content=resp)

    @app.get("/v1/jobs/{jid}")
    def get_job_route(jid: str, authorization: Optional[str] = Header(default=None)):
        require_auth(authorization)
        resp = get_job(jid)
        if "error" in resp:
            raise HTTPException(status_code=404, detail={"error": "not_found", "code": 404})
        return resp

    @app.delete("/v1/jobs/{jid}")
    def delete_job_route(jid: str, authorization: Optional[str] = Header(default=None)):
        require_auth(authorization)
        resp = cancel_job(jid)
        if "error" in resp:
            raise HTTPException(status_code=404, detail={"error": "not_found", "code": 404})
        return resp

    # OpenAI-compatible chat completions (proxy to providers)
    @app.post("/v1/chat/completions")
    def chat_completions(body: Dict[str, Any], authorization: Optional[str] = Header(default=None)):
        # Optional auth check for non-local usage
        require_auth(authorization)
        if call_xai is None:
            raise HTTPException(status_code=503, detail={"error": "not_available", "code": 503, "message": "provider clients unavailable"})

        model = body.get("model") or get_default_model("anthropic")
        messages: List[Dict[str, str]] = body.get("messages") or []
        temperature = float(body.get("temperature", 0.2))
        system_text = None
        user_texts: List[str] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                system_text = content
            elif role == "user":
                user_texts.append(content)
            elif role == "assistant":
                # We don't thread assistant history into all providers in this MVP
                pass
        prompt = "\n\n".join(user_texts) if user_texts else ""
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "invalid_request", "code": 400, "message": "missing user prompt"})

        # Route to provider by model hint
        ml = str(model).lower()
        if "grok" in ml or "xai" in ml:
            provider = "xai"; base = get_default_base("xai"); key = get_api_key("xai", None)
            resp = call_xai(prompt, system_text, model, base, key, temperature)  # type: ignore
            text = extract_text("xai", resp)  # type: ignore
        elif "gemini" in ml or "google" in ml:
            provider = "google"; base = get_default_base("google"); key = get_api_key("google", None)
            resp = call_google(prompt, system_text, model, base, key, temperature)  # type: ignore
            text = extract_text("google", resp)  # type: ignore
        elif "claude" in ml or "anthropic" in ml or "opus" in ml:
            provider = "anthropic"; base = get_default_base("anthropic"); key = get_api_key("anthropic", None)
            resp = call_anthropic(prompt, system_text, model, base, key, temperature, max_tokens=int(body.get("max_tokens", 1024)))  # type: ignore
            text = extract_text("anthropic", resp)  # type: ignore
        else:
            # Default to Anthropic as arbiter-like choice
            provider = "anthropic"; base = get_default_base("anthropic"); key = get_api_key("anthropic", None)
            resp = call_anthropic(prompt, system_text, model, base, key, temperature, max_tokens=int(body.get("max_tokens", 1024)))  # type: ignore
            text = extract_text("anthropic", resp)  # type: ignore

        if text is None:
            raise HTTPException(status_code=502, detail={"error": "bad_gateway", "code": 502})
        # OpenAI-compatible response shell
        return {
            "id": "chatcmpl-" + (provider or "prov"),
            "object": "chat.completion",
            "created": int(__import__('time').time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop"
                }
            ]
        }
else:
    # Provide a hint if someone tries to run this without FastAPI
    app = None  # type: ignore
