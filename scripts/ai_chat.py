#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import random
from typing import Optional
from urllib import request, parse, error


def http_post_json(url: str, payload: dict, headers: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    attempts = int(os.getenv("AI_HTTP_RETRIES", "3"))
    base_delay = float(os.getenv("AI_HTTP_RETRY_BASE", "0.5"))
    timeout = int(os.getenv("AI_HTTP_TIMEOUT", "90"))

    last_err = None
    for i in range(attempts):
        req = request.Request(url, data=data, headers=headers, method="POST")
        try:
            start = time.time()
            with request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                took = int((time.time() - start) * 1000)
                # Optionally expose timing via env (debug only)
                if os.getenv("AI_HTTP_DEBUG"):
                    print(f"[http] {url} {resp.status} {took}ms", file=sys.stderr)
                return json.loads(body)
        except error.HTTPError as e:
            try:
                msg = e.read().decode("utf-8")
            except Exception:
                msg = str(e)
            # Retry on typical transient statuses
            if e.code in (408, 409, 425, 429, 500, 502, 503, 504):
                last_err = f"HTTP {e.code}: {msg[:200]}"
            else:
                raise SystemExit(f"HTTP {e.code}: {msg}")
        except error.URLError as e:
            last_err = f"Network error: {e}"

        # Backoff
        if i < attempts - 1:
            delay = base_delay * (2 ** i) + random.uniform(0, 0.2)
            time.sleep(delay)

    raise SystemExit(last_err or "HTTP request failed")


def arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Unified AI chat: xAI (Grok), Google (Gemini), Anthropic (Claude)")
    p.add_argument("prompt", nargs="?", help="User prompt. If omitted, reads stdin.")
    p.add_argument("--provider", "-p", choices=["xai", "google", "anthropic"], default=os.getenv("AI_PROVIDER", "xai"), help="Provider: xai | google | anthropic (env: AI_PROVIDER)")
    p.add_argument("--model", "-m", help="Model name; falls back to provider-specific env and defaults")
    p.add_argument("--system", "-s", default=os.getenv("AI_SYSTEM"), help="Optional system instruction (env: AI_SYSTEM)")
    p.add_argument("--api-key", "-k", help="API key; else read provider-specific env vars")
    p.add_argument("--base", "-b", help="Override API base URL for xai/anthropic; google base is fixed unless provided")
    p.add_argument("--max-tokens", type=int, default=int(os.getenv("AI_MAX_TOKENS", "1024")), help="Max tokens for providers that require it")
    p.add_argument("--temperature", type=float, default=float(os.getenv("AI_TEMPERATURE", "0.2")), help="Sampling temperature")
    p.add_argument("--json", action="store_true", help="Print raw JSON response")
    return p


def get_default_model(provider: str) -> str:
    if provider == "xai":
        return os.getenv("GROK_MODEL", os.getenv("XAI_MODEL", "grok-code-fast-1"))
    if provider == "google":
        return os.getenv("GOOGLE_MODEL", os.getenv("GEMINI_MODEL", "gemini-1.5-pro-latest"))
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_MODEL", "claude-opus-4-1-20250805")
    return ""


def get_default_base(provider: str) -> str:
    if provider == "xai":
        return os.getenv("GROK_API_BASE", os.getenv("XAI_API_BASE", "https://api.x.ai/v1"))
    if provider == "google":
        # Default Gemini REST base; endpoint adds model path and :generateContent
        return os.getenv("GOOGLE_API_BASE", os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"))
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_BASE", "https://api.anthropic.com/v1")
    return ""


def get_api_key(provider: str, explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    if provider == "xai":
        return os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY", "")
    if provider == "google":
        return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY", "")
    return ""


def call_xai(prompt: str, system: Optional[str], model: str, base: str, api_key: str, temperature: float) -> dict:
    url = base.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    return http_post_json(url, payload, headers)


def call_google(prompt: str, system: Optional[str], model: str, base: str, api_key: str, temperature: float) -> dict:
    # Gemini generateContent endpoint takes API key as query param
    path = f"/models/{model}:generateContent"
    q = parse.urlencode({"key": api_key})
    url = base.rstrip("/") + path + ("?" + q)
    headers = {"Content-Type": "application/json"}

    contents = [{
        "role": "user",
        "parts": [{"text": prompt}],
    }]
    payload: dict = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if system:
        payload["systemInstruction"] = {"role": "system", "parts": [{"text": system}]}

    return http_post_json(url, payload, headers)


def call_anthropic(prompt: str, system: Optional[str], model: str, base: str, api_key: str, temperature: float, max_tokens: int) -> dict:
    url = base.rstrip("/") + "/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    return http_post_json(url, payload, headers)


def extract_text(provider: str, resp: dict) -> str:
    try:
        if provider == "xai":
            return resp["choices"][0]["message"]["content"].strip()
        if provider == "google":
            # candidates[0].content.parts[].text
            candidates = resp.get("candidates") or []
            parts = (candidates[0].get("content", {}).get("parts") if candidates else None) or []
            texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
            return "\n".join([t for t in texts if t]).strip()
        if provider == "anthropic":
            # content is a list of blocks with type "text"
            blocks = resp.get("content") or []
            texts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
            return "\n".join([t for t in texts if t]).strip()
    except Exception:
        pass
    # Fallback to raw JSON if parsing fails
    return json.dumps(resp, indent=2, ensure_ascii=False)


def main() -> None:
    p = arg_parser()
    args = p.parse_args()

    # Prompt input
    prompt = args.prompt if args.prompt else (sys.stdin.read().strip() if not sys.stdin.isatty() else None)
    if not prompt:
        print("No prompt provided. Type prompt and Ctrl-D to send:", file=sys.stderr)
        prompt = sys.stdin.read().strip()
    if not prompt:
        raise SystemExit("Empty prompt")

    provider = args.provider
    model = args.model or get_default_model(provider)
    base = args.base or get_default_base(provider)
    api_key = get_api_key(provider, args.api_key)
    if not api_key:
        raise SystemExit(f"Missing API key for provider '{provider}'. Set --api-key or relevant env var.")

    if provider == "xai":
        resp = call_xai(prompt, args.system, model, base, api_key, args.temperature)
    elif provider == "google":
        resp = call_google(prompt, args.system, model, base, api_key, args.temperature)
    elif provider == "anthropic":
        resp = call_anthropic(prompt, args.system, model, base, api_key, args.temperature, args.max_tokens)
    else:
        raise SystemExit(f"Unsupported provider: {provider}")

    if args.json:
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return

    print(extract_text(provider, resp))


if __name__ == "__main__":
    main()
