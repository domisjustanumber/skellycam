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
def check_main_process_heartbeat(*,
                                 heartbeat_timestamp: Synchronized,
                                 global_kill_flag: Synchronized) -> bool:
    """Check if main process is still alive based on heartbeat."""
    current_time: float = time.perf_counter()
    last_heartbeat: float = heartbeat_timestamp.value

    time_since_heartbeat: float = current_time - last_heartbeat

    if time_since_heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
        logger.error(
            f"Main process heartbeat timeout! "
            f"Last heartbeat was {time_since_heartbeat:.1f}s ago "
            f"(timeout: {HEARTBEAT_TIMEOUT_SECONDS}s)"
        )
        global_kill_flag.value = True
        return False

    return True
