"""A web page's visible text, one line per block element.

Shared by parsers that read pages as text rather than by CMS markup (SIFMA),
and by the job API's capture-text endpoint. Scripts, styles and the like are
skipped; curly apostrophes and non-breaking spaces are normalised.
"""

from html.parser import HTMLParser

_BLOCK = {
    "address", "article", "aside", "blockquote", "br", "button", "dd", "div", "dl", "dt",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav",
    "ol", "p", "section", "table", "td", "th", "tr", "ul",
}
_SKIP = {"script", "style", "noscript", "template", "svg"}


class _Lines(HTMLParser):
    """The page's visible text, one line per block element."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._buf: list[str] = []
        self._skip = 0

    def _flush(self):
        text = " ".join("".join(self._buf).split())
        if text:
            self.lines.append(text)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self._flush()

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def lines(html: str) -> list[str]:
    p = _Lines()
    p.feed(html)
    p.close()
    # Undo curly quotes so names compare cleanly ("New Year’s Day").
    return [ln.replace("’", "'").replace(" ", " ") for ln in p.lines]
