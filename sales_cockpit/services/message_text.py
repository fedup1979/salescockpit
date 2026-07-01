from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re
from typing import Any


_FRONT_HTML_TAG_RE = re.compile(
    r"<\s*/?\s*(?:div|p|br|span|img|strong|b|em|i|ul|ol|li|a)\b",
    re.IGNORECASE,
)
_TRAILING_ORPHAN_HTML_CLOSING_TAGS_RE = re.compile(
    r"(?:\r?\n[ \t]*</(?:div|span|p|section|article)>[ \t]*)+\Z",
    re.IGNORECASE,
)


class _FrontHTMLTextParser(HTMLParser):
    BLOCK_TAGS = {"div", "p", "li", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.saw_image = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "br":
            self._newline(force=True)
        elif tag in self.BLOCK_TAGS:
            self._newline()
        elif tag == "img":
            self.saw_image = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self._newline()

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data.replace("\xa0", " "))

    def _newline(self, force: bool = False) -> None:
        if not self.parts:
            return
        if force or not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def text(self) -> str:
        text = "".join(self.parts)
        return _normalize_message_text(text)


def clean_message_body_text(value: Any) -> str:
    text = str(value or "").strip()
    text = _TRAILING_ORPHAN_HTML_CLOSING_TAGS_RE.sub("", text).rstrip()
    if _FRONT_HTML_TAG_RE.search(text):
        converted = front_html_to_text(text)
        if converted:
            return converted
        if re.search(r"<\s*img\b", text, re.IGNORECASE):
            return "Pièce jointe Front"
    return _normalize_message_text(text)


def front_message_body_text(message: dict[str, Any]) -> str:
    raw_text = str(message.get("text") or "").replace("\xa0", " ")
    if raw_text.strip():
        return clean_message_body_text(raw_text)
    raw_body = str(message.get("body") or "")
    if raw_body.strip():
        converted = clean_message_body_text(raw_body)
        if converted:
            return converted
    if message.get("attachments"):
        return "Pièce jointe Front"
    return ""


def front_html_to_text(value: Any) -> str:
    parser = _FrontHTMLTextParser()
    parser.feed(str(value or ""))
    parser.close()
    return parser.text()


def _normalize_message_text(value: str) -> str:
    text = unescape(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    normalized: list[str] = []
    previous_blank = False
    for line in lines:
        blank = line == ""
        if blank and previous_blank:
            continue
        normalized.append(line)
        previous_blank = blank
    return "\n".join(normalized).strip()
