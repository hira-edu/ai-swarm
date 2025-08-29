import json
import sys
from datetime import datetime
from typing import Any, Dict


def log_json(level: str, event: str, message: str = "", **fields: Any) -> None:
    rec: Dict[str, Any] = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "event": event,
        "message": message,
    }
    rec.update({k: v for k, v in fields.items() if v is not None})
    json.dump(rec, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def info(event: str, message: str = "", **fields: Any) -> None:
    log_json("INFO", event, message, **fields)


def warn(event: str, message: str = "", **fields: Any) -> None:
    log_json("WARN", event, message, **fields)


def error(event: str, message: str = "", **fields: Any) -> None:
    log_json("ERROR", event, message, **fields)

