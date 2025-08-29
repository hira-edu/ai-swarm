#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Optional
from urllib import request, error


def post_json(url: str, payload: dict, headers: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except error.HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        raise SystemExit(f"HTTP {e.code}: {msg}")
    except error.URLError as e:
        raise SystemExit(f"Network error: {e}")


def build_messages(user_prompt: str, system_prompt: Optional[str]) -> list:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    return messages


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Call Grok (xAI) chat completions")
    p.add_argument("prompt", nargs="?", help="User prompt. If omitted, reads stdin.")
    p.add_argument("--model", "-m", default=os.getenv("GROK_MODEL", "grok-code-fast-1"), help="Model name (env: GROK_MODEL)")
    p.add_argument("--base", "-b", default=os.getenv("GROK_API_BASE", "https://api.x.ai/v1"), help="API base URL (env: GROK_API_BASE)")
    p.add_argument("--system", "-s", default=os.getenv("GROK_SYSTEM"), help="Optional system prompt (env: GROK_SYSTEM)")
    p.add_argument("--api-key", "-k", default=os.getenv("GROK_API_KEY"), help="API key (env: GROK_API_KEY)")
    p.add_argument("--json", action="store_true", help="Print raw JSON response")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Read prompt from stdin if not provided as an arg
    if not args.prompt:
        if sys.stdin.isatty():
            print("No prompt provided. Type your prompt and press Ctrl-D:", file=sys.stderr)
        args.prompt = sys.stdin.read().strip()
    if not args.prompt:
        raise SystemExit("Empty prompt")

    if not args.api_key:
        raise SystemExit("Missing API key. Set --api-key or GROK_API_KEY.")

    # Endpoint path follows OpenAI-compatible schema
    url = args.base.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": args.model,
        "messages": build_messages(args.prompt, args.system),
        "temperature": 0.2,
    }

    resp = post_json(url, payload, headers)

    if args.json:
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return

    try:
        content = resp["choices"][0]["message"]["content"].strip()
    except Exception:
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        raise SystemExit(1)

    print(content)


if __name__ == "__main__":
    main()
