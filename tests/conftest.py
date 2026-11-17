import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings
from data.seed import build


@pytest.fixture
def settings(tmp_path):
    db = tmp_path / "shop.db"
    build(db)
    return load_settings().with_(db_path=db)
