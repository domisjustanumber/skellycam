"""Put suite/, suite/macos/, suite/macos/helpers/ and this folder on sys.path, as the macOS suite does."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MACOS = HERE.parent
SUITE = MACOS.parent
for p in (str(SUITE), str(MACOS), str(MACOS / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
