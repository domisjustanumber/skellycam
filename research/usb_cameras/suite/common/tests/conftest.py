"""Put the suite directory on sys.path so tests import ``common`` exactly as the suites do."""
import sys
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent
for p in (str(SUITE_DIR), str(TESTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)
