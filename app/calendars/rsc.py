"""Text from a Next.js page's embedded React Server Components data.

Next.js app-router pages ship their full component tree in
`self.__next_f.push([1, "..."])` scripts (the "flight" data), and the
browser renders some of it only on demand: SIFMA's year tabs (2027 and on)
are there and nowhere in the HTML's visible text. `lines()` rebuilds the
tree and returns its text in document order, one line per block element,
like `text.lines()` does for HTML, hidden tabs included.

The flight format: rows `<hex id>:<payload>`, newline-terminated, except
text rows `<hex id>:T<hex byte length>,<text>` with no terminator. JSON
payloads hold React elements `["$", type, key, props]`; strings `$<hex>`,
`$L<hex>` and `$@<hex>` point at other rows, `$$...` is a literal `$...`, and
other `$` strings (`$undefined`, `$Sreact.fragment`) aren't text. Rows
of other kinds (module imports, hints, errors) are skipped.

Pages without flight data give no lines; callers fall back to the HTML.
"""

import json
import re

PUSH = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.DOTALL)
REF = re.compile(r"^\$[L@]?([0-9a-f]+)$")
_BLOCK = {
    "address", "article", "aside", "blockquote", "br", "button", "dd", "div", "dl", "dt",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav",
    "ol", "p", "section", "table", "td", "th", "tr", "ul",
}
_SKIP = {"script", "style", "noscript", "template", "svg", "head", "meta", "link", "title"}
_MAX_DEPTH = 400


def flight(html: str) -> str:
    """The page's concatenated flight data ('' if it has none)."""
    chunks = []
    for raw in PUSH.findall(html):
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if len(item) > 1 and item[0] == 1 and isinstance(item[1], str):
            chunks.append(item[1])
    return "".join(chunks)


def rows(data: str) -> dict[str, object]:
    """Row id -> parsed payload (JSON value or text); other kinds are skipped."""
    b = data.encode("utf-8")
    out: dict[str, object] = {}
    pos = 0
    while pos < len(b):
        colon = b.find(b":", pos)
        if colon < 0:
            break
        rid = b[pos:colon].decode("ascii", "replace").strip()
        if b[colon + 1:colon + 2] == b"T":
            comma = b.find(b",", colon + 2)
            size = int(b[colon + 2:comma], 16)
            out[rid] = b[comma + 1:comma + 1 + size].decode("utf-8", "replace")
            pos = comma + 1 + size
            continue
        nl = b.find(b"\n", colon + 1)
        end = len(b) if nl < 0 else nl
        payload = b[colon + 1:end].decode("utf-8", "replace")
        if payload[:1] in ('[', '{', '"') or payload[:1].isdigit() or payload in ("true", "false", "null"):
            try:
                out[rid] = json.loads(payload)
            except json.JSONDecodeError:
                pass
        pos = end + 1
    return out


def lines(html: str) -> list[str]:
    """The flight tree's text in document order, one line per block element."""
    table = rows(flight(html))
    if "0" not in table:
        return []
    out: list[str] = []
    buf: list[str] = []

    def flush():
        text = " ".join("".join(buf).split())
        if text:
            out.append(text.replace("’", "'").replace("\xa0", " "))
        buf.clear()

    def walk(node, depth: int, stack: frozenset):
        if depth > _MAX_DEPTH:
            return
        if isinstance(node, str):
            if m := REF.match(node):
                rid = m.group(1)
                if rid in table and rid not in stack:
                    walk(table[rid], depth + 1, stack | {rid})
            elif node.startswith("$$"):
                buf.append(node[1:])
            elif not node.startswith("$"):
                buf.append(node)
            return
        if isinstance(node, list):
            if len(node) >= 4 and node[0] == "$" and isinstance(node[3], dict):
                kind = node[1]
                tag = kind if isinstance(kind, str) and not kind.startswith("$") else None
                if tag in _SKIP:
                    return
                block = tag in _BLOCK
                if block:
                    flush()
                walk(node[3].get("children"), depth + 1, stack)
                if block:
                    flush()
                return
            for child in node:
                walk(child, depth + 1, stack)
            return
        if isinstance(node, dict):
            for key in ("children", "f", "b", "P"):  # props, or Next's root envelope
                if key in node:
                    walk(node[key], depth + 1, stack)

    walk(table["0"], 0, frozenset({"0"}))
    flush()
    return out
