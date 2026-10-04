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
def sifma_archive_html() -> bytes:
    return (FIXTURES / "sifma_us_archive.html").read_bytes()


# Stand-in bytes for SIFMA's historical PDF. That source has no parser yet, so
# only the raw capture matters; the real PDF becomes the fixture with its parser.
SIFMA_HISTORY_PDF = b"%PDF-1.4\n% stand-in for SIFMA's historical recommendations PDF\n%%EOF\n"


@pytest.fixture
def sifma_history_pdf() -> bytes:
    return SIFMA_HISTORY_PDF


@pytest.fixture
def sifma_fetch(sifma_html, sifma_archive_html):
    """A fetcher for calendar SIFMA-US's sources: its page, archive and historical PDF."""
    from app.calendars import sifma

    pages = {
        sifma.URL: (sifma_html, "text/html; charset=utf-8"),
        sifma.ARCHIVE_URL: (sifma_archive_html, "text/html; charset=utf-8"),
        sifma.HISTORY_URL: (SIFMA_HISTORY_PDF, "application/pdf"),
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
