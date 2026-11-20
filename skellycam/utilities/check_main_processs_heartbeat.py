import multiprocessing
from multiprocessing.sharedctypes import Synchronized
import time

import logging
from typing import Final

logger = logging.getLogger(__name__)
HEARTBEAT_INTERVAL_SECONDS: Final[float] = 1.0
# Decision L of the user (2026-11-20): the camera processes notice a dead server after 10 s, not 300 s.
# The writer is a thread of its own (WorkerRegistry), not the event loop: a busy main process still beats.
HEARTBEAT_TIMEOUT_SECONDS: Final[float] = 10.0
_last_report = 0.0


def check_main_process_heartbeat(*, heartbeat_timestamp: Synchronized) -> bool:
    """Check if main process is still alive based on heartbeat. A lost heartbeat ends only the cameras (each
    camera loop ends itself, decision L): it sets no global kill flag, so a live main process stays up."""
    global _last_report
    current_time: float = time.perf_counter()
    last_heartbeat: float = heartbeat_timestamp.value

    time_since_heartbeat: float = current_time - last_heartbeat

    if time_since_heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
        if current_time - _last_report > HEARTBEAT_TIMEOUT_SECONDS:  # one line for each stall, not one each call
            _last_report = current_time
            logger.warning(  # one line for each stall; the camera then reports its reason
                f"Main process heartbeat timeout! "
                f"Last heartbeat was {time_since_heartbeat:.1f}s ago "
                f"(timeout: {HEARTBEAT_TIMEOUT_SECONDS}s)"
            )
        return False

    return True
