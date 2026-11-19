import sys


def utf8_console() -> None:
    """Write the console streams as UTF-8 (user, 2026-11-19).

    skellylogs starts each console line with a box-drawing character. A piped stdout or stderr on
    Windows is cp1252, and each log line then fails with "--- Logging error ---". Call this before
    the logging is configured.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
