"""Text from a Next.js page's embedded React data (app/calendars/rsc.py)."""

import json

from app.calendars import rsc


def _page(*chunks: str) -> str:
    pushes = "".join(f"<script>self.__next_f.push({json.dumps([1, c])})</script>" for c in chunks)
    return f"<html><body><p>visible</p>{pushes}</body></html>"


def test_rows_and_references_in_document_order():
    tree = [
        "$", "div", None, {"children": [
            ["$", "h2", None, {"children": "Heading"}],
            "$L2",
            ["$", "p", None, {"children": ["one ", "$3"]}],
        ]},
    ]
    html = _page(
        "0:" + json.dumps(tree) + "\n",
        "2:" + json.dumps(["$", "section", None, {"children": [["$", "h3", None, {"children": "Hidden tab"}]]}]) + "\n",
        "3:" + json.dumps("two") + "\n",
    )
    assert rsc.lines(html) == ["Heading", "Hidden tab", "one two"]


def test_text_rows_are_length_prefixed_in_utf8_bytes():
    text = "caf\u00e9 \u2019quoted\u2019"  # multi-byte characters
    n = len(text.encode("utf-8"))
    html = _page("0:" + json.dumps(["$", "p", None, {"children": "$1"}]) + "\n", f"1:T{n:x},{text}", "4:" + json.dumps("x") + "\n")
    assert rsc.lines(html) == ["caf\u00e9 'quoted'"]


def test_dollar_strings_that_arent_text_are_skipped_and_escapes_kept():
    html = _page("0:" + json.dumps(["$", "p", None, {"children": ["$undefined", "$Sreact.fragment", "$$5 off"]}]) + "\n")
    assert rsc.lines(html) == ["$5 off"]


def test_scripts_and_templates_are_skipped_and_cycles_stop():
    html = _page(
        "0:" + json.dumps(["$", "div", None, {"children": [["$", "script", None, {"children": "x()"}], "$L1"]}]) + "\n",
        "1:" + json.dumps(["$", "p", None, {"children": ["loop", "$L1"]}]) + "\n",
    )
    assert rsc.lines(html) == ["loop"]


def test_a_page_without_embedded_data_has_no_lines():
    assert rsc.lines("<html><body><p>plain</p></body></html>") == []


def test_sifmas_real_page_has_both_year_tabs(sifma_page_capture3):
    lines = rsc.lines(sifma_page_capture3.decode("utf-8"))
    us = lines[lines.index("U.S. Holiday Recommendations"):lines.index("U.K. Holiday Recommendations")]
    assert "Friday, June 18, 2027" in us and "Monday, January 19, 2026" in us
