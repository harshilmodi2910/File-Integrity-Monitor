import shutil
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent

# lets a plain `pytest` find the fim package without installing it
sys.path.insert(0, str(TESTS_DIR.parent))


@pytest.fixture
def target(tmp_path):
    """A fresh copy of tests/sample_dir, so tests can change files freely."""
    dest = tmp_path / "target"
    shutil.copytree(TESTS_DIR / "sample_dir", dest)
    return dest


@pytest.fixture
def baseline_file(tmp_path):
    """Baseline location outside the target directory."""
    return tmp_path / "baseline.json"
