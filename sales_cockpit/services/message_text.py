from __future__ import annotations

import re
from typing import Any


_TRAILING_ORPHAN_HTML_CLOSING_TAGS_RE = re.compile(
    r"(?:\r?\n[ \t]*</(?:div|span|p|section|article)>[ \t]*)+\Z",
    re.IGNORECASE,
)


def clean_message_body_text(value: Any) -> str:
    text = str(value or "").strip()
    return _TRAILING_ORPHAN_HTML_CLOSING_TAGS_RE.sub("", text).rstrip()
