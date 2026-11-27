import multiprocessing

# unix-capture.md 4.12 [ADR-HQE5]: the program entry point sets "spawn" as its first action, before any multiprocessing
# object exists, on each system (no change where spawn is the default). A forked camera process can deadlock at its
# start; the start of a camera process refuses "fork". A spawned child imports this module again as `__mp_main__`,
# with the method already set.
if multiprocessing.get_start_method(allow_none=True) != "spawn":
    multiprocessing.set_start_method("spawn", force=True)

from skellycam.utilities.utf8_console import utf8_console  # noqa: E402

utf8_console()  # first: before an import configures the logging

import asyncio  # noqa: E402
import logging  # noqa: E402
import multiprocessing  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402

logger = logging.getLogger(__name__)

# recorder.md 9.1 [ADR-06PW]: the shutdown of uvicorn waits at most this long for open connections. It starts at the
# SIGTERM of the worker monitor, after each take and each protected save has finished.
SHUTDOWN_CONNECTION_LIMIT_S = 5


async def main() -> None:
    import sys
    import uvicorn
    from skellycam.api.server_constants import HOSTNAME, PORT
    from skellycam.app import create_fastapi_app
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
    from skellycam.core.ipc.process_management.managed_worker import WorkerMode

    # Suppress benign ConnectionResetError from Windows ProactorEventLoop.
    # When browsers close range-request connections early (normal for <video> streaming),
    # the proactor tries to shutdown an already-closed socket and raises ConnectionResetError.
    # These are harmless — the requests complete successfully (HTTP 206).
    if sys.platform == "win32":
        loop = asyncio.get_event_loop()
        _default_handler = loop.get_exception_handler()

        def _suppress_connection_reset(loop: asyncio.AbstractEventLoop, context: dict) -> None:
            exception = context.get("exception")
            if isinstance(exception, ConnectionResetError):
                logger.debug(f"Suppressed a connection reset: {context.get('message')}")  # recorder.md 9.1
                return
            if _default_handler is not None:
                _default_handler(loop, context)
            else:
                loop.default_exception_handler(context)

        loop.set_exception_handler(_suppress_connection_reset)

    global_kill_flag = multiprocessing.Value("b", False, lock=False)  # no lock: main-process writers only (unix 4.10)
    worker_registry = WorkerRegistry(
        global_kill_flag=global_kill_flag,
        worker_mode=WorkerMode.PROCESS,
    )
    worker_registry.start_heartbeat()

    server: uvicorn.Server | None = None

    def handle_signal(signum: int, frame: object) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        global_kill_flag.value = True
        if server:
            server.should_exit = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        app = create_fastapi_app(
            global_kill_flag=global_kill_flag,
            worker_registry=worker_registry,
        )

        config = uvicorn.Config(
            app=app,
            host=HOSTNAME,
            port=PORT,
            log_level="warning",
            reload=False,
            # A JPEG does not compress: deflate cost 12.7 ms of the event loop for each 1080p frame (ADR-HDC9)
            ws_per_message_deflate=False,
            timeout_graceful_shutdown=SHUTDOWN_CONNECTION_LIMIT_S,
        )
        server = uvicorn.Server(config)

        logger.info(f"Starting server on {HOSTNAME}:{PORT}")
        await server.serve()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        global_kill_flag.value = True  # serve() has returned: its connections, tasks and lifespan end are done
        worker_registry.shutdown_all()  # it waits for each worker (kill flag, then terminate, then kill)
        logger.success("Done! Thank you for using SkellyCam 💀📸✨")


def entry_point() -> None:
    """Sync entry point for the `skellycam` console script."""
    from skellylogs import configure_logging, get_websocket_log_queue

    from skellycam import LOG_LEVEL
    from skellycam.system.default_paths import get_log_file_path

    # the app calls logger.api / logger.success, which exist only after this (a host such as freemocap
    # configures logging itself; the standalone server must do it here)
    configure_logging(level=LOG_LEVEL, log_file_path=get_log_file_path())
    # recorder.md 9.1 item 4: only an open websocket reads this queue; no exit waits for its feeder thread
    get_websocket_log_queue().cancel_join_thread()

    multiprocessing.freeze_support()
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        os._exit(1)
    print("Done!")
    os._exit(0)


if __name__ == "__main__":
    entry_point()
