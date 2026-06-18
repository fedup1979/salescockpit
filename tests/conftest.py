from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from sales_cockpit.config import get_settings


@pytest.fixture(autouse=True)
def isolated_test_database(monkeypatch):
    temp_dir = Path(tempfile.mkdtemp(prefix="sales_cockpit_test_"))
    monkeypatch.setenv("SALES_COCKPIT_DB_PATH", str(temp_dir / "sales_cockpit_test.db"))
    monkeypatch.setenv("SALES_COCKPIT_STORAGE_PATH", str(temp_dir / "storage"))
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
        shutil.rmtree(temp_dir, ignore_errors=True)
