from skellycam.utilities.utf8_console import utf8_console

utf8_console()  # first: before an import configures the logging

import asyncio  # noqa: E402
import logging  # noqa: E402
import multiprocessing  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402

logger = logging.getLogger(__name__)


async def main() -> None:
    import sys
    import uvicorn
    from skellycam.api.server_constants import HOSTNAME, PORT
    from skellycam.app import create_fastapi_app
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.utilities.wait_functions import await_1s

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
                return
            if _default_handler is not None:
                _default_handler(loop, context)
            else:
                loop.default_exception_handler(context)

        loop.set_exception_handler(_suppress_connection_reset)

    global_kill_flag = multiprocessing.Value("b", False)
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
        global_kill_flag.value = True
        if server:
            server.should_exit = True
            await await_1s()

        worker_registry.shutdown_all()
        logger.success("Done! Thank you for using SkellyCam 💀📸✨")


def entry_point() -> None:
    """Sync entry point for the `skellycam` console script."""
    from skellylogs import configure_logging

    from skellycam import LOG_LEVEL
    from skellycam.system.default_paths import get_log_file_path

    # the app calls logger.api / logger.success, which exist only after this (a host such as freemocap
    # configures logging itself; the standalone server must do it here)
    configure_logging(level=LOG_LEVEL, log_file_path=get_log_file_path())

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
