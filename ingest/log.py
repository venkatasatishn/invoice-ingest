from __future__ import annotations
import json
import sys
from datetime import datetime
from typing import Any, Dict


def log(event: str, level: str = "INFO", **fields: Any) -> None:
    """
    Prints one JSON log line per event.

    Benefits:
    - easy to search/filter in logs
    - good for production observability
    """
    payload: Dict[str, Any] = {
        "ts": datetime.utcnow().isoformat(),
        "level": level,
        "event": event,
        **fields,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
