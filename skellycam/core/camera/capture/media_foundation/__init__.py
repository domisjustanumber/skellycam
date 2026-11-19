"""The Media Foundation source of Windows (specs/windows-capture.md, section 6). Windows only (U18)."""

import sys

# comtypes joins the multithreaded apartment (MTA) at import only when this is set first (agent 43).
# Python runs this file before each module of the package, so before any comtypes import here.
sys.coinit_flags = 0
