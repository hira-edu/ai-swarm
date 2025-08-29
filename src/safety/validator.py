from typing import Any, Dict, List, Tuple


ALLOWED_TOOLS = {
    "fs_list": {"dir": str, "pattern": (str, type(None)), "max_results": (int, type(None))},
    "fs_read": {"path": str, "max_bytes": (int, type(None))},
    "search_text": {"pattern": str, "dir": (str, type(None)), "max_matches": (int, type(None))},
    "fs_stat": {"path": str},
    "fs_write": {"path": str, "content": str, "create_dirs": (bool, type(None)), "allow_overwrite": (bool, type(None))},
    "health_check": {},
}


def validate_tool_call(name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    if name not in ALLOWED_TOOLS:
        return False, f"unknown_tool:{name}"
    spec = ALLOWED_TOOLS[name]
    # required keys are those with non-optional types
    for key, typ in spec.items():
        if isinstance(typ, tuple):
            # optional-like union
            if key not in args:
                continue
            if not isinstance(args[key], typ):
                return False, f"bad_type:{key}"
        else:
            if key not in args:
                return False, f"missing:{key}"
            if not isinstance(args[key], typ):
                return False, f"bad_type:{key}"
    # unknown extra keys are allowed but discouraged
    return True, "ok"


def validate_tool_calls(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return only valid calls; attach error fields to invalid ones."""
    valid: List[Dict[str, Any]] = []
    for c in calls:
        name = c.get("name") or c.get("tool")
        args = c.get("args") or c.get("parameters") or {}
        ok, reason = validate_tool_call(str(name), args if isinstance(args, dict) else {})
        if ok:
            valid.append({"name": name, "args": args})
        else:
            valid.append({"name": name, "args": args, "error": reason})
    return valid

