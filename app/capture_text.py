"""A raw capture as numbered text lines: what a parser reads, without downloading the page.

An HTML page's visible text (one line per block element), or with `embedded` a Next.js page's embedded React
data (rsc.py: what SIFMA's parser reads); JSON pretty-printed one value per line; anything else textual (CSV,
XML) line by line. Shared by GET /jobs/captures/{id}/text (home-mcp's mkt_data_capture_text) and the gRPC
SourceStatus.GetCaptureText (mkt-ui's Sources screen).
"""

import json

from app.calendars import rsc, text


class NoTextView(ValueError):
    """The capture has no text of the kind asked for: a binary file, or no embedded data."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status  # the HTTP status the job API answers with (404 or 415)


def lines(capture_id: int, body: bytes, ctype: str, embedded: bool = False) -> tuple[str, list[str]]:
    """(view, lines): view is visible, embedded, json or text."""
    is_html = "html" in ctype.lower() or body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html"))
    if is_html:
        html = body.decode("utf-8", errors="replace")
        out = rsc.lines(html) if embedded else text.lines(html)
        if embedded and not out:
            raise NoTextView(f"capture {capture_id} has no embedded React data; use the default view", 404)
        return ("embedded" if embedded else "visible"), out
    if embedded:
        raise NoTextView(f"capture {capture_id} is {ctype or 'not HTML'}; only HTML has embedded data", 415)
    binary_type = any(t in ctype.lower() for t in ("pdf", "octet-stream", "zip", "image/", "excel", "spreadsheet"))
    if binary_type or body.startswith(b"%PDF") or b"\x00" in body[:4096]:
        raise NoTextView(f"capture {capture_id} is {ctype or 'binary'}; no text view", 415)
    raw = body.decode("utf-8", errors="replace")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return "text", raw.splitlines()
    return "json", json.dumps(doc, indent=1, ensure_ascii=False).splitlines()


def select_lines(all_lines: list[str], contains: str = "", context: int = 0) -> tuple[list[int], int | None]:
    """The indexes to show (every line, or those containing `contains`, case-insensitive, with `context` either
    side) and how many lines matched (None without `contains`)."""
    if not contains:
        return list(range(len(all_lines))), None
    hits = [i for i, ln in enumerate(all_lines) if contains.lower() in ln.lower()]
    keep = sorted({j for i in hits for j in range(max(0, i - context), min(len(all_lines), i + context + 1))})
    return keep, len(hits)
