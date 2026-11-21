"""
Clean shutdown endpoint with proper async handling.
"""
import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from skellycam.core.camera_group.camera_group_manager import close_camera_groups_before_exit


logger = logging.getLogger(__name__)

shutdown_router = APIRouter(tags=["App"])


@shutdown_router.get(
    "/shutdown",
    summary="Gracefully shutdown the server",
    response_model=dict[str, str]
)
async def shutdown_server(
        request: Request,
) -> JSONResponse:
    """
    Initiate graceful server shutdown.

    This endpoint triggers a graceful shutdown of the entire SkellyCam system,
    including all camera groups and the server itself.

    Returns:
        JSON response confirming shutdown initiation
    """
    logger.api(f"Shutdown requested via API - {request.url}")

    # Answer at once (the Electron app waits 5 s at most), then, in the background, end a running take through
    # the take level (recorder.md 8.1) and close the groups before the kill flag. The worker monitor then waits
    # for active saves before signaling the server; self-termination would bypass that.
    async def close_then_kill() -> None:
        try:
            await close_camera_groups_before_exit()
        finally:
            request.app.state.global_kill_flag.value = True
            logger.info("Requested shutdown after the camera groups closed")

    running = getattr(request.app.state, "shutdown_task", None)
    if running is None or running.done():  # a second request starts no second close (the lifespan end waits for it)
        request.app.state.shutdown_task = asyncio.create_task(close_then_kill())  # a reference keeps the task
    return JSONResponse(
        content={
            "status": "shutdown_initiated",
            "message": "Server shutting down. Goodbye! 👋"
        },
        status_code=200
    )
