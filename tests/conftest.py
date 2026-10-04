from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app import db
from app.config import Settings

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fed_html() -> bytes:
    return (FIXTURES / "fed_k8_2026.html").read_bytes()


@pytest.fixture
def sifma_html() -> bytes:
    return (FIXTURES / "sifma_us_2026.html").read_bytes()


@pytest.fixture
def sifma_page_capture3() -> bytes:
    """SIFMA's schedule page as the hub captured it (#3, 2026-10-04), byte for byte.

    Unlike sifma_us_2026.html (its visible text in simple markup), this has the
    page's embedded React data, where the 2027 tab lives.
    """
    return (FIXTURES / "sifma_us_page_capture3.html").read_bytes()


@pytest.fixture
def sifma_archive_html() -> bytes:
    return (FIXTURES / "sifma_us_archive.html").read_bytes()


@pytest.fixture
def sifma_history_pdf() -> bytes:
    """SIFMA's 1996-2019 PDF: the hub's capture #5, byte for byte."""
    return (FIXTURES / "sifma_us_history_1996_2019.pdf").read_bytes()


@pytest.fixture
def sifma_fetch(sifma_html, sifma_archive_html, sifma_history_pdf):
    """A fetcher for calendar SIFMA-US's sources: its page, archive and historical PDF."""
    from app.calendars import sifma

    pages = {
        sifma.URL: (sifma_html, "text/html; charset=utf-8"),
        sifma.ARCHIVE_URL: (sifma_archive_html, "text/html; charset=utf-8"),
        sifma.HISTORY_URL: (sifma_history_pdf, "application/pdf"),
    }
    return lambda url: (200, pages[url][1], pages[url][0])


@pytest.fixture
def nyse_html() -> bytes:
    return (FIXTURES / "nyse_hours_2026.html").read_bytes()


@pytest.fixture
def migrated_db(tmp_path, monkeypatch):
    """A throwaway SQLite database at the head migration, used by db.session()."""
    url = f"sqlite:///{tmp_path / 'app.db'}"
    monkeypatch.setattr(db, "settings", Settings(database_url=url))
    db._engine.cache_clear()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    yield url
    db._engine.cache_clear()


def pytest_configure(config):
    config.addinivalue_line("markers", "projections: keep the projected sources (FED/SIFMA-US/NYSE-PROJECTED)")


@pytest.fixture(autouse=True)
def _no_projections(request, monkeypatch):
    """Tests run without the projected sources unless marked `projections`.

    The projections fill every year to 2100, which would change the counts and
    "not covered" answers that the other tests are about.
    """
    if request.node.get_closest_marker("projections"):
        return
    from dataclasses import replace

    from app.calendars import service

    for name, spec in list(service.CALENDARS.items()):
        kept = tuple(src for src in spec.sources if not src.projected)
        monkeypatch.setitem(service.CALENDARS, name, replace(spec, sources=kept))
