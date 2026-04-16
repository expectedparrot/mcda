from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from .errors import UserError

ID_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_id(value: str, label: str = "id") -> str:
    if not ID_RE.match(value):
        raise UserError(
            f"Invalid {label}: {value!r}. IDs must match ^[a-zA-Z_][a-zA-Z0-9_]*$.",
            {"value": value, "label": label},
        )
    return value


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def local_iso_now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def uuid8() -> str:
    return uuid.uuid4().hex[:8]


def record_id(descriptor: str) -> str:
    return f"{utc_timestamp()}_{uuid8()}_{descriptor}"
