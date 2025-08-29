#!/usr/bin/env python3
import argparse
import json
import os
import sys
import textwrap
import re
import fnmatch
import time
from datetime import datetime
import uuid
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from pathlib import Path

# Ensure src/ is importable and structured logger available
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
try:
    from logging.structured import info as log_info, warn as log_warn, error as log_error
except Exception:  # fallback no-op
    def log_info(event: str, message: str = "", **kw: Any) -> None:  # type: ignore
        pass
    def log_warn(event: str, message: str = "", **kw: Any) -> None:  # type: ignore
        pass
    def log_error(event: str, message: str = "", **kw: Any) -> None:  # type: ignore
        pass
try:
    from safety.validator import validate_tool_calls
except Exception:
    def validate_tool_calls(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:  # type: ignore
        return calls

# Reuse provider callers from our unified client
try:
    from scripts.ai_chat import (
        call_xai,
        call_google,
        call_anthropic,
        extract_text,
        get_default_model,
        get_default_base,
        get_api_key,
    )
except ModuleNotFoundError:
    # Fallback when run as a script from the scripts/ directory
    from ai_chat import (  # type: ignore
        call_xai,
        call_google,
        call_anthropic,
        extract_text,
        get_default_model,
        get_default_base,
        get_api_key,
    )


AGENT_TEMPLATES = {
    "xai": "You are Grok, a pragmatic senior engineer. Prioritize actionable steps, minimalism, and working code. When unclear, state assumptions and propose a quick experiment.",
    "google": "You are Gemini, a fast researcher. Bring up relevant docs, alternatives, and risks. Prefer concise bullet points and references (no links required).",
    "anthropic": "You are Claude Opus, a careful reviewer. Identify edge cases, safety, and testability. Suggest improvements and point out ambiguities politely.",
}


CONSENSUS_INSTRUCTION = (
    "Synthesize the agents' notes into a single, concise consensus.\n"
    "Output these sections:\n"
    "- Summary: one paragraph\n"
    "- Plan: 3-7 bullet steps\n"
    "- Suggestions: concrete improvements or changes\n"
    "- Risks: 2-4 brief bullets\n"
    "- Decision: continue or stop, with rationale"
)


@dataclass
class Agent:
    provider: str  # 'xai' | 'google' | 'anthropic'
    name: str
    model: str
    base: str
    api_key: str
    temperature: float = 0.2
    system: Optional[str] = None

    def call(self, prompt: str) -> str:
        if self.provider == "xai":
            resp = call_xai(prompt, self.system, self.model, self.base, self.api_key, self.temperature)
        elif self.provider == "google":
            resp = call_google(prompt, self.system, self.model, self.base, self.api_key, self.temperature)
        elif self.provider == "anthropic":
            resp = call_anthropic(prompt, self.system, self.model, self.base, self.api_key, self.temperature, max_tokens=2048)
        else:
            raise RuntimeError(f"Unsupported provider: {self.provider}")
        return extract_text(self.provider, resp)


class ToolExecutor:
    def __init__(self, allow_write: bool = False, root: str = ".", rate_limit_max: int = 20, rate_window_sec: int = 60, timeout_ms: int = 8000) -> None:
        self.allow_write = allow_write
        self.root = Path(root).resolve()
        self.rl_max = rate_limit_max
        self.rl_window = rate_window_sec
        self.timeout_ms = timeout_ms
        self._rl_events: Dict[str, List[float]] = {}

    def _safe_path(self, path: str) -> Path:
        p = (self.root / path).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError("Path escapes workspace")
        return p

    def list_files(self, dir: str = ".", pattern: Optional[str] = None, max_results: int = 200, actor: Optional[str] = None) -> Dict[str, Any]:
        # Rate limiting
        rl = self._rate_check("fs_list", actor)
        if rl:
            return rl

        deadline = time.time() + (self.timeout_ms / 1000.0)
        base = self._safe_path(dir)
        items: List[str] = []
        for root, _, files in os.walk(base):
            for f in files:
                rel = str(Path(root, f).resolve().relative_to(self.root))
                if pattern:
                    # Support simple glob patterns by default; allow regex: prefix for regex
                    if pattern.startswith("regex:"):
                        try:
                            if not re.search(pattern[len("regex:"):], rel):
                                continue
                        except re.error as e:
                            return {"error": f"invalid_regex: {e}", "code": 400}
                    else:
                        if not fnmatch.fnmatch(rel, pattern):
                            continue
                items.append(rel)
                if len(items) >= max_results:
                    break
                if time.time() > deadline:
                    return {"files": items, "count": len(items), "error": "timeout", "code": 408}
            if len(items) >= max_results:
                break
        return {"files": items, "count": len(items)}

    def read_file(self, path: str, max_bytes: int = 50_000, actor: Optional[str] = None) -> Dict[str, Any]:
        rl = self._rate_check("fs_read", actor)
        if rl:
            return rl
        p = self._safe_path(path)
        data = p.read_bytes()[:max_bytes] if p.exists() else b""
        return {"path": str(p.relative_to(self.root)), "bytes": len(data), "content": data.decode("utf-8", errors="replace")}

    def search_text(self, pattern: str, dir: str = ".", max_matches: int = 200, actor: Optional[str] = None) -> Dict[str, Any]:
        rl = self._rate_check("search_text", actor)
        if rl:
            return rl
        deadline = time.time() + (self.timeout_ms / 1000.0)
        base = self._safe_path(dir)
        regex = re.compile(pattern)
        matches: List[Dict[str, Any]] = []
        for root, _, files in os.walk(base):
            for f in files:
                p = Path(root, f)
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for i, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        matches.append({"file": str(p.resolve().relative_to(self.root)), "line": i, "text": line.strip()})
                        if len(matches) >= max_matches:
                            return {"matches": matches}
                    if time.time() > deadline:
                        return {"matches": matches, "error": "timeout", "code": 408}
        return {"matches": matches}

    def stat_file(self, path: str, actor: Optional[str] = None) -> Dict[str, Any]:
        rl = self._rate_check("fs_stat", actor)
        if rl:
            return rl
        p = self._safe_path(path)
        if not p.exists():
            return {"error": "not_found", "code": 404, "path": str(p.relative_to(self.root))}
        st = p.stat()
        return {
            "path": str(p.relative_to(self.root)),
            "size": st.st_size,
            "mtime": st.st_mtime,
            "is_dir": p.is_dir(),
            "is_file": p.is_file(),
        }

    def write_file(self, path: str, content: str, create_dirs: bool = True, allow_overwrite: bool = True, actor: Optional[str] = None) -> Dict[str, Any]:
        rl = self._rate_check("fs_write", actor)
        if rl:
            return rl
        p = self._safe_path(path)
        if not self.allow_write:
            return {"error": "writes_disabled", "code": 423, "path": str(p.relative_to(self.root))}
        if create_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not allow_overwrite:
            return {"error": "exists", "code": 409, "path": str(p.relative_to(self.root))}
        before = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
        p.write_text(content, encoding="utf-8")
        after_len = p.stat().st_size if p.exists() else 0
        return {"applied": True, "path": str(p.relative_to(self.root)), "before_bytes": len(before.encode("utf-8")), "after_bytes": after_len}

    def health_check(self, actor: Optional[str] = None) -> Dict[str, Any]:
        rl = self._rate_check("health_check", actor)
        if rl:
            return rl
        # Non-sensitive environment/ctx info
        return {
            "cwd": str(self.root),
            "allow_write": self.allow_write,
            "env": {
                "has_grok_key": bool(os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")),
                "has_google_key": bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")),
                "has_anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")),
            },
            "tools": ["fs_list", "fs_read", "search_text", "fs_stat", "fs_write", "health_check"],
        }

    def _rate_check(self, tool: str, actor: Optional[str]) -> Optional[Dict[str, Any]]:
        now = time.time()
        key = f"{tool}:{actor or '-'}"
        q = self._rl_events.setdefault(key, [])
        # drop old
        q[:] = [t for t in q if now - t < self.rl_window]
        if len(q) >= self.rl_max:
            reset = 0
            if q:
                oldest = min(q)
                reset = max(0, int(self.rl_window - (now - oldest)))
            remaining = max(0, self.rl_max - len(q))
            return {"error": "rate_limited", "code": 429, "tool": tool, "limit": self.rl_max, "window_sec": self.rl_window, "remaining": remaining, "reset_sec": reset, "scope": actor or "-"}
        q.append(now)
        return None


def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    # Try fenced JSON blocks first
    fences = re.findall(r"```json\s*(\{[\s\S]*?\})\s*```", text)
    blocks = []
    for f in fences:
        try:
            obj = json.loads(f)
            blocks.append(obj)
        except Exception:
            continue
    # Also attempt to parse the whole text as JSON
    if not blocks:
        try:
            obj = json.loads(text)
            blocks.append(obj)
        except Exception:
            pass
    # Normalize to list of tool_calls
    calls: List[Dict[str, Any]] = []
    for b in blocks:
        if isinstance(b, dict):
            if "tool_calls" in b:
                tc = b.get("tool_calls")
                if isinstance(tc, list):
                    calls.extend([c for c in tc if isinstance(c, dict)])
            # Support alternate schema { tool, parameters }
            if "tool" in b and "parameters" in b:
                calls.append({"name": b.get("tool"), "args": b.get("parameters")})
            # Support array of simple calls
            if "calls" in b and isinstance(b["calls"], list):
                for c in b["calls"]:
                    if isinstance(c, dict) and ("name" in c or "tool" in c):
                        calls.append({"name": c.get("name") or c.get("tool"), "args": c.get("args") or c.get("parameters")})
    return calls


def build_agents(args: argparse.Namespace) -> List[Agent]:
    agents: List[Agent] = []

    # xAI / Grok
    if (not args.only or "xai" in args.only) and (not args.disable or "xai" not in args.disable):
        agents.append(Agent(
            provider="xai",
            name="Grok",
            model=args.xai_model or get_default_model("xai"),
            base=args.xai_base or get_default_base("xai"),
            api_key=get_api_key("xai", args.xai_key),
            temperature=args.temperature,
            system=args.xai_system or os.getenv("XAI_SYSTEM", AGENT_TEMPLATES["xai"]),
        ))

    # Google / Gemini
    if (not args.only or "google" in args.only) and (not args.disable or "google" not in args.disable):
        agents.append(Agent(
            provider="google",
            name="Gemini",
            model=args.google_model or get_default_model("google"),
            base=args.google_base or get_default_base("google"),
            api_key=get_api_key("google", args.google_key),
            temperature=args.temperature,
            system=args.google_system or os.getenv("GOOGLE_SYSTEM", AGENT_TEMPLATES["google"]),
        ))

    # Anthropic / Claude
    if (not args.only or "anthropic" in args.only) and (not args.disable or "anthropic" not in args.disable):
        agents.append(Agent(
            provider="anthropic",
            name="Claude",
            model=args.anthropic_model or get_default_model("anthropic"),
            base=args.anthropic_base or get_default_base("anthropic"),
            api_key=get_api_key("anthropic", args.anthropic_key),
            temperature=args.temperature,
            system=args.anthropic_system or os.getenv("ANTHROPIC_SYSTEM", AGENT_TEMPLATES["anthropic"]),
        ))

    # Validate keys
    for a in agents:
        if not a.api_key:
            raise SystemExit(f"Missing API key for {a.name} ({a.provider}). Set env or pass a flag.")
    return agents


def round_prompt(task: str, transcript: List[Dict[str, str]], round_idx: int) -> str:
    history = []
    # Keep last ~2500 chars of transcript for brevity
    acc = ""
    for turn in transcript[-6:]:  # last few entries
        line = f"[{turn['who']}] {turn['content'].strip()}\n"
        history.append(line)
        acc += line
        if len(acc) > 2500:
            break

    history_text = "".join(history)
    return textwrap.dedent(f"""
    Task:
    {task}

    You are one of multiple cooperating agents. Read the recent transcript and provide:
    1) Brief analysis (2-4 bullets)
    2) Proposed next steps (3-5 bullets)
    3) Key risks or open questions (1-3)
    4) Decision: continue or stop, with 1-line rationale

    Recent transcript (latest last):
    {history_text}
    """)


def consensus_prompt(task: str, round_outputs: Dict[str, str]) -> str:
    parts = [f"- {name}:\n{content}\n" for name, content in round_outputs.items()]
    return textwrap.dedent(f"""
    {CONSENSUS_INSTRUCTION}

    Task:
    {task}

    Agents' notes this round:
    {''.join(parts)}
    """)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Coordinate Grok, Gemini, and Claude in consensus rounds.")
    p.add_argument("task", nargs="?", help="Task prompt. If omitted, reads stdin.")
    p.add_argument("--rounds", type=int, default=int(os.getenv("SWARM_ROUNDS", "2")), help="Number of coordination rounds")
    p.add_argument("--temperature", type=float, default=float(os.getenv("SWARM_TEMPERATURE", "0.2")))
    p.add_argument("--only", nargs="*", choices=["xai", "google", "anthropic"], help="Limit to specific providers")
    p.add_argument("--disable", nargs="*", choices=["xai", "google", "anthropic"], help="Disable specific providers")

    # Arbiter settings
    p.add_argument("--arbiter", choices=["xai", "google", "anthropic"], default=os.getenv("SWARM_ARBITER", "anthropic"))
    p.add_argument("--arbiter-model", help="Override arbiter model")

    # Provider-specific config (optional overrides)
    p.add_argument("--xai-key"); p.add_argument("--xai-model"); p.add_argument("--xai-base"); p.add_argument("--xai-system")
    p.add_argument("--google-key"); p.add_argument("--google-model"); p.add_argument("--google-base"); p.add_argument("--google-system")
    p.add_argument("--anthropic-key"); p.add_argument("--anthropic-model"); p.add_argument("--anthropic-base"); p.add_argument("--anthropic-system")

    p.add_argument("--json", action="store_true", help="Print final consensus JSON as well as text")
    p.add_argument("--allow-write", action="store_true", help="Allow applying write-file tool requests after arbiter approval")
    p.add_argument("--config", help="Optional JSON config file (e.g., config/agents.json)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    task = args.task if args.task else (sys.stdin.read().strip() if not sys.stdin.isatty() else None)
    if not task:
        print("Enter task, then Ctrl-D:", file=sys.stderr)
        task = sys.stdin.read().strip()
    if not task:
        raise SystemExit("Empty task")

    agents = build_agents(args)

    # Configure arbiter as a temporary Agent instance
    arb_provider = args.arbiter
    arb = Agent(
        provider=arb_provider,
        name=f"Arbiter-{arb_provider}",
        model=(args.arbiter_model or get_default_model(arb_provider)),
        base=get_default_base(arb_provider),
        api_key=get_api_key(arb_provider, None),
        temperature=args.temperature,
        system="You are the arbiter. Synthesize short, decisive, practical consensus across agents.",
    )

    transcript: List[Dict[str, str]] = []
    final_consensus: Optional[str] = None

    # Load optional config
    cfg_path = args.config or os.getenv("SWARM_CONFIG", "")
    config = {}
    if cfg_path and os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as fh:
                config = json.load(fh)
        except Exception as e:
            print(f"[Config] Failed to load {cfg_path}: {e}")
    cb_threshold = int(str(config.get("limits", {}).get("cb_threshold", os.getenv("SWARM_CB_THRESHOLD", 2))))
    cb_cooldown = int(str(config.get("limits", {}).get("cb_cooldown_sec", os.getenv("SWARM_CB_COOLDOWN", 60))))
    rl_max = int(str(config.get("limits", {}).get("tool_max_per_window", os.getenv("SWARM_TOOL_MAX", 20))))
    rl_window = int(str(config.get("limits", {}).get("tool_window_sec", os.getenv("SWARM_TOOL_WINDOW", 60))))
    tool_timeout_ms = int(str(config.get("limits", {}).get("tool_timeout_ms", os.getenv("SWARM_TOOL_TIMEOUT_MS", 8000))))

    tools = ToolExecutor(allow_write=args.allow_write, root=".", rate_limit_max=rl_max, rate_window_sec=rl_window, timeout_ms=tool_timeout_ms)
    pending_writes: List[Dict[str, Any]] = []
    telemetry: Dict[str, Any] = {"agent_calls": [], "tool_calls": [], "writes": {"proposed": 0, "applied": 0}}
    tool_cache: Dict[str, Any] = {}
    agent_state: Dict[str, Any] = {}
    corr_id = uuid.uuid4().hex[:12]
    context_store: Dict[str, Any] = {}
    context_versions: Dict[str, int] = {}

    for r in range(1, args.rounds + 1):
        # Set phase marker in shared context
        context_store["phase"] = r
        print(f"\n=== Round {r} ===", flush=True)
        rp = round_prompt(task, transcript, r)
        round_outputs: Dict[str, str] = {}

        # Seed queue at start of Round 1 if empty
        if r == 1:
            qkey = "coord:queue"
            q = context_store.get(qkey) or []
            if not q:
                q = [
                    {"kind": "list_code_files", "payload": {"dir": ".", "pattern": "**/*.py"}},
                    {"kind": "scan_docs", "payload": {"dir": "docs"}},
                    {"kind": "review_tools", "payload": {}}
                ]
                context_store[qkey] = q

        for a in agents:
            print(f"\n[{a.name}] thinking...", flush=True)

            # Circuit breaker: skip agent if open
            st = agent_state.get(a.name, {"fail": 0, "open_until": 0})
            now = time.time()
            if st.get("open_until", 0) > now:
                msg = f"Circuit breaker open; skipping until {datetime.utcfromtimestamp(st['open_until']).isoformat()}Z"
                round_outputs[a.name] = msg
                transcript.append({"who": a.name, "content": msg, "meta": {"agent": a.name, "provider": a.provider, "ts": datetime.utcnow().isoformat() + "Z"}})
                print(f"[{a.name}] {msg}")
                continue
            try:
                start = time.time()
                out = a.call(rp)
                took_ms = int((time.time() - start) * 1000)
                round_outputs[a.name] = out
                transcript.append({
                    "who": a.name,
                    "content": out,
                    "meta": {"agent": a.name, "provider": a.provider, "model": a.model, "ts": datetime.utcnow().isoformat() + "Z", "latency_ms": took_ms, "corr_id": corr_id},
                })
                telemetry["agent_calls"].append({"agent": a.name, "provider": a.provider, "ok": True, "ms": took_ms})
                # Reset fail count on success
                agent_state[a.name] = {"fail": 0, "open_until": 0}
                print(f"[{a.name}]\n{out}\n", flush=True)

                # Tool handling (only on successful output)
                parsed_calls = extract_tool_calls(out)
                tool_calls = validate_tool_calls(parsed_calls)
                for call in tool_calls:
                    name = call.get("name") or call.get("tool")
                    args_map = call.get("args") or call.get("parameters") or {}
                    if call.get("error"):
                        err_obj = {"error": call["error"], "code": 400, "tool": name}
                        transcript.append({"who": f"ToolError({a.name})", "content": json.dumps(err_obj)})
                        telemetry["tool_calls"].append({"tool": name or "unknown", "ok": False, "ms": 0, "error": call["error"]})
                        continue
                    try:
                        # Build dedup cache key for read-only tools
                        key = None
                        if name in ("fs_list", "fs_read", "search_text", "fs_stat", "health_check"):
                            key = json.dumps({"tool": name, "args": args_map}, sort_keys=True)
                        if key and key in tool_cache:
                            cached = tool_cache[key]
                            transcript.append({"who": f"ToolCache({a.name})", "content": json.dumps({"tool": name, "cached": True, "result": cached})})
                            print(f"[Tool cache hit for {a.name}] {name}")
                            continue

                        if name == "fs_list":
                            t0 = time.time()
                            res = tools.list_files(dir=args_map.get("dir", "."), pattern=args_map.get("pattern"), max_results=int(args_map.get("max_results", 200)), actor=a.name)
                            msg = f"Tool fs_list result: {res.get('count',0)} files"
                            transcript.append({"who": f"Tool({a.name})", "content": msg + "\n" + json.dumps(res), "meta": {"tool": "fs_list", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "fs_list", "ok": True, "ms": int((time.time()-t0)*1000)})
                            if key: tool_cache[key] = res
                            print(f"[Tool for {a.name}] fs_list -> {res.get('count',0)} files")
                        elif name == "fs_read":
                            t0 = time.time()
                            res = tools.read_file(path=args_map.get("path", ""), max_bytes=int(args_map.get("max_bytes", 50000)), actor=a.name)
                            snippet = res.get("content", "")[:500]
                            transcript.append({"who": f"Tool({a.name})", "content": f"fs_read {res.get('path')}:\n" + snippet, "meta": {"tool": "fs_read", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "fs_read", "ok": True, "ms": int((time.time()-t0)*1000)})
                            if key: tool_cache[key] = res
                            print(f"[Tool for {a.name}] fs_read -> {res.get('path')}")
                        elif name == "search_text":
                            t0 = time.time()
                            res = tools.search_text(pattern=args_map.get("pattern", "."), dir=args_map.get("dir", "."), max_matches=int(args_map.get("max_matches", 100)), actor=a.name)
                            transcript.append({"who": f"Tool({a.name})", "content": "search_text results:\n" + json.dumps(res), "meta": {"tool": "search_text", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "search_text", "ok": True, "ms": int((time.time()-t0)*1000)})
                            if key: tool_cache[key] = res
                            print(f"[Tool for {a.name}] search_text -> {len(res.get('matches',[]))} matches")
                        elif name == "fs_stat":
                            t0 = time.time()
                            res = tools.stat_file(path=args_map.get("path", ""), actor=a.name)
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps(res), "meta": {"tool": "fs_stat", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "fs_stat", "ok": True, "ms": int((time.time()-t0)*1000)})
                            if key: tool_cache[key] = res
                            print(f"[Tool for {a.name}] fs_stat -> {args_map.get('path','')}")
                        elif name == "health_check":
                            t0 = time.time()
                            res = tools.health_check(actor=a.name)
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps(res), "meta": {"tool": "health_check", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "health_check", "ok": True, "ms": int((time.time()-t0)*1000)})
                            if key: tool_cache[key] = res
                            print(f"[Tool for {a.name}] health_check -> ok")
                        elif name == "ctx_put":
                            k = str(args_map.get("key", ""))
                            v = args_map.get("value")
                            mode = str(args_map.get("mode", "set"))
                            expect = args_map.get("expected_version")
                            cur_ver = context_versions.get(k, 0)
                            apply = False
                            if mode == "set":
                                apply = True
                            elif mode == "if_absent":
                                apply = (k not in context_store)
                            elif mode == "if_version":
                                apply = (isinstance(expect, int) and expect == cur_ver)
                            if apply:
                                context_store[k] = v
                                context_versions[k] = cur_ver + 1
                                result = {"ok": True, "key": k, "version": context_versions[k]}
                            else:
                                result = {"ok": False, "key": k, "version": cur_ver, "error": "version_mismatch"}
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps(result), "meta": {"tool": "ctx_put", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "ctx_put", "ok": bool(result.get("ok")), "ms": 0})
                            print(f"[Tool for {a.name}] ctx_put -> {k} v{context_versions.get(k,0)}")
                        elif name == "ctx_get":
                            k = str(args_map.get("key", ""))
                            val = context_store.get(k)
                            ver = context_versions.get(k, 0)
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps({"key": k, "value": val, "version": ver}), "meta": {"tool": "ctx_get", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "ctx_get", "ok": True, "ms": 0})
                            print(f"[Tool for {a.name}] ctx_get -> {k}")
                        elif name == "ctx_keys":
                            prefix = args_map.get("prefix")
                            keys = [k for k in context_store.keys() if (not prefix or str(k).startswith(str(prefix)))]
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps({"keys": keys}), "meta": {"tool": "ctx_keys", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "ctx_keys", "ok": True, "ms": 0})
                            print(f"[Tool for {a.name}] ctx_keys -> {len(keys)} keys")
                        elif name == "coord_enqueue":
                            # In-memory queue with task ids and leases
                            kind = str(args_map.get("kind", "")).strip()
                            payload = args_map.get("payload") or {}
                            if not kind:
                                raise ValueError("missing kind")
                            if not isinstance(payload, dict):
                                payload = {}
                            qkey = "coord:queue"
                            q = context_store.get(qkey) or []
                            tid = uuid.uuid4().hex[:10]
                            item = {
                                "id": tid,
                                "kind": kind,
                                "payload": payload,
                                "status": "queued",
                                "lease_until": None,
                                "claimed_by": None,
                            }
                            q.append(item)
                            context_store[qkey] = q
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps({"enqueued": True, "id": tid, "kind": kind}), "meta": {"tool": "coord_enqueue", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "coord_enqueue", "ok": True, "ms": 0})
                            print(f"[Tool for {a.name}] coord_enqueue -> {kind} ({tid})")
                        elif name == "coord_next":
                            qkey = "coord:queue"
                            q = context_store.get(qkey) or []
                            lease_sec = int(args_map.get("lease_sec", 180))
                            now = time.time()
                            chosen = None
                            for itm in q:
                                exp = itm.get("lease_until") or 0
                                if itm.get("status") in (None, "queued") or now > exp:
                                    chosen = itm
                                    break
                            if chosen is None:
                                data = None
                            else:
                                chosen["status"] = "claimed"
                                chosen["lease_until"] = now + lease_sec
                                chosen["claimed_by"] = a.name
                                data = {"id": chosen["id"], "kind": chosen["kind"], "payload": chosen.get("payload"), "lease_until": chosen["lease_until"], "claimed_by": a.name}
                            context_store[qkey] = q
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps({"item": data}), "meta": {"tool": "coord_next", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "coord_next", "ok": True, "ms": 0})
                            print(f"[Tool for {a.name}] coord_next -> {'none' if data is None else data.get('kind','')}")
                        elif name == "coord_claim":
                            qkey = "coord:queue"
                            q = context_store.get(qkey) or []
                            tid = str(args_map.get("id", ""))
                            lease_sec = int(args_map.get("lease_sec", 180))
                            now = time.time()
                            found = next((itm for itm in q if itm.get("id") == tid), None)
                            if not found:
                                result = {"error": "not_found", "code": 404}
                            else:
                                exp = found.get("lease_until") or 0
                                if found.get("status") == "claimed" and now <= exp and found.get("claimed_by") not in (None, a.name):
                                    result = {"error": "in_use", "code": 423}
                                else:
                                    found["status"] = "claimed"
                                    found["lease_until"] = now + lease_sec
                                    found["claimed_by"] = a.name
                                    result = {"id": found["id"], "kind": found["kind"], "lease_until": found["lease_until"], "claimed_by": a.name}
                            context_store[qkey] = q
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps(result), "meta": {"tool": "coord_claim", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "coord_claim", "ok": True, "ms": 0})
                        elif name == "coord_complete":
                            qkey = "coord:queue"
                            q = context_store.get(qkey) or []
                            tid = str(args_map.get("id", ""))
                            result_payload = args_map.get("result")
                            found = next((itm for itm in q if itm.get("id") == tid), None)
                            if not found:
                                result = {"error": "not_found", "code": 404}
                            else:
                                found["status"] = "done"
                                found["lease_until"] = None
                                found["result"] = result_payload
                                result = {"id": found["id"], "status": "done"}
                            context_store[qkey] = q
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps(result), "meta": {"tool": "coord_complete", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "coord_complete", "ok": True, "ms": 0})
                        elif name == "coord_extend":
                            qkey = "coord:queue"
                            q = context_store.get(qkey) or []
                            tid = str(args_map.get("id", ""))
                            extra_sec = int(args_map.get("extend_sec", 120))
                            now = time.time()
                            found = next((itm for itm in q if itm.get("id") == tid), None)
                            if not found:
                                result = {"error": "not_found", "code": 404}
                            else:
                                exp = found.get("lease_until") or 0
                                if found.get("claimed_by") not in (None, a.name):
                                    result = {"error": "not_owner", "code": 403}
                                elif now > exp:
                                    result = {"error": "expired", "code": 409}
                                else:
                                    found["lease_until"] = exp + extra_sec
                                    result = {"id": found["id"], "lease_until": found["lease_until"]}
                            context_store[qkey] = q
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps(result), "meta": {"tool": "coord_extend", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "coord_extend", "ok": True, "ms": 0})
                        elif name == "coord_status":
                            qkey = "coord:queue"
                            q = context_store.get(qkey) or []
                            front = None if not q else {"id": q[0].get("id"), "kind": q[0].get("kind"), "payload": q[0].get("payload"), "status": q[0].get("status")}
                            counts: Dict[str, int] = {}
                            for itm in q:
                                st = str(itm.get("status") or "queued")
                                counts[st] = counts.get(st, 0) + 1
                            status = {"length": len(q), "front": front, "phase": context_store.get("phase"), "counts": counts}
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps(status), "meta": {"tool": "coord_status", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "coord_status", "ok": True, "ms": 0})
                            print(f"[Tool for {a.name}] coord_status -> {status['length']} items")
                            transcript.append({"who": f"Tool({a.name})", "content": json.dumps(res), "meta": {"tool": "health_check", "ts": datetime.utcnow().isoformat() + "Z", "corr_id": corr_id}})
                            telemetry["tool_calls"].append({"tool": "health_check", "ok": True, "ms": int((time.time()-t0)*1000)})
                            if key: tool_cache[key] = res
                            print(f"[Tool for {a.name}] health_check -> ok")
                        elif name == "fs_write":
                            # Queue for arbiter approval
                            proposal = {
                                "by": a.name,
                                "path": args_map.get("path"),
                                "content": args_map.get("content", ""),
                                "create_dirs": bool(args_map.get("create_dirs", True)),
                                "allow_overwrite": bool(args_map.get("allow_overwrite", True)),
                            }
                            telemetry["writes"]["proposed"] += 1
                            pending_writes.append(proposal)
                            transcript.append({"who": f"ToolProposal({a.name})", "content": json.dumps({"fs_write": proposal})})
                            print(f"[Proposal from {a.name}] fs_write -> {proposal['path']}")
                    except Exception as e:
                        err_obj = {"error": str(e), "code": 500, "tool": name}
                        transcript.append({"who": f"ToolError({a.name})", "content": json.dumps(err_obj)})
                        telemetry["tool_calls"].append({"tool": name or "unknown", "ok": False, "ms": 0, "error": str(e)})
                        print(f"[Tool error for {a.name}] {name}: {e}")
            except SystemExit as e:
                msg = f"Agent error: {e}"
                round_outputs[a.name] = msg
                transcript.append({"who": a.name, "content": msg, "meta": {"agent": a.name, "provider": a.provider, "ts": datetime.utcnow().isoformat() + "Z"}})
                telemetry["agent_calls"].append({"agent": a.name, "provider": a.provider, "ok": False, "error": str(e)})
                # Increment fail and maybe open breaker
                st = agent_state.get(a.name, {"fail": 0, "open_until": 0})
                st["fail"] = st.get("fail", 0) + 1
                if st["fail"] >= cb_threshold:
                    st["open_until"] = time.time() + cb_cooldown
                    print(f"[{a.name}] Circuit breaker opened for {cb_cooldown}s (fails={st['fail']})")
                agent_state[a.name] = st
                print(f"[{a.name}] ERROR: {e}")
            except Exception as e:
                msg = f"Agent exception: {e}"
                round_outputs[a.name] = msg
                transcript.append({"who": a.name, "content": msg, "meta": {"agent": a.name, "provider": a.provider, "ts": datetime.utcnow().isoformat() + "Z"}})
                telemetry["agent_calls"].append({"agent": a.name, "provider": a.provider, "ok": False, "error": str(e)})
                st = agent_state.get(a.name, {"fail": 0, "open_until": 0})
                st["fail"] = st.get("fail", 0) + 1
                if st["fail"] >= cb_threshold:
                    st["open_until"] = time.time() + cb_cooldown
                    print(f"[{a.name}] Circuit breaker opened for {cb_cooldown}s (fails={st['fail']})")
                agent_state[a.name] = st
                print(f"[{a.name}] EXCEPTION: {e}")

        # Arbiter consensus
        cp = consensus_prompt(task, round_outputs)
        print("[Arbiter] synthesizing...")
        consensus = arb.call(cp)
        final_consensus = consensus
        transcript.append({"who": "Arbiter", "content": consensus})
        print(f"\n[Consensus]\n{consensus}\n")

        # If there are pending writes, de-duplicate/conflict note and ask arbiter to approve in strict JSON
        if pending_writes:
            # Detect conflicts (same path proposed by multiple agents)
            path_counts: Dict[str, int] = {}
            for p in pending_writes:
                path_counts[p.get("path") or ""] = path_counts.get(p.get("path") or "", 0) + 1
            conflicts = [path for path, cnt in path_counts.items() if cnt > 1 and path]
            approval_prompt = textwrap.dedent(f"""
            You are the arbiter. The agents have proposed write actions. Decide which to apply.
            Output STRICT JSON with this schema only:
            {{
              "decisions": [
                {{"path": "string", "action": "approve"|"reject", "notes": "short reason"}}
              ]
            }}

            Proposals:
            {json.dumps(pending_writes, indent=2)}
            Detected conflicts for paths: {json.dumps(conflicts)}
            """)
            print("[Arbiter] reviewing write proposals...")
            approval_resp = arb.call(approval_prompt)
            # Extract JSON
            decisions_obj = None
            try:
                blocks = re.findall(r"```json\s*(\{[\s\S]*?\})\s*```", approval_resp)
                src = blocks[0] if blocks else approval_resp
                decisions_obj = json.loads(src)
            except Exception:
                pass
            applied_results: List[Dict[str, Any]] = []
            if decisions_obj and isinstance(decisions_obj.get("decisions"), list):
                for d in decisions_obj["decisions"]:
                    if d.get("action") == "approve":
                        path = d.get("path")
                        match = next((p for p in pending_writes if p.get("path") == path), None)
                        if match:
                            res = tools.write_file(
                                path=match["path"],
                                content=match.get("content", ""),
                                create_dirs=bool(match.get("create_dirs", True)),
                                allow_overwrite=bool(match.get("allow_overwrite", True)),
                            )
                            applied_results.append({"path": path, "result": res, "notes": d.get("notes", "")})
                            if res.get("applied"):
                                telemetry["writes"]["applied"] += 1
                transcript.append({"who": "Arbiter", "content": "Write decisions:\n" + json.dumps(decisions_obj)})
                if applied_results:
                    transcript.append({"who": "System", "content": "Applied writes:\n" + json.dumps(applied_results)})
                    print(f"[System] Applied {len(applied_results)} write(s)")
            else:
                transcript.append({"who": "System", "content": "No valid write decision JSON parsed."})
            pending_writes = []

    # Print telemetry summary
    print("\n=== Telemetry Summary ===")
    print(json.dumps(telemetry, indent=2))

    if args.json:
        result = {"task": task, "transcript": transcript, "consensus": final_consensus}
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
