# /// script
# requires-python = "==3.12.*"
# dependencies = ["pyarrow==25.0.0", "numpy==2.4.6", "pandas==2.3.3"]
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""Same checks as read_check.py with pyarrow 25.0.0 (the freemocap .venv version): pyarrow and pandas readers.

  uv run --script read_check_pa25.py
"""
import sys

import read_check

sys.argv = [sys.argv[0], "--readers", "pyarrow,pandas", "--tag", "pa25"]
read_check.main()
