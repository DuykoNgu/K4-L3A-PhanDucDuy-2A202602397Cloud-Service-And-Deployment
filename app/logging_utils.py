"""Log JSON một dòng trên stdout để platform thu thập."""

import json
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(event: str, level: str = "info", **fields: Any) -> str:
    record = {
        **fields,
        "event": event,
        "level": level.lower(),
        "timestamp": utc_now_iso(),
    }
    line = json.dumps(record, ensure_ascii=False)
    print(line, flush=True)
    return line
