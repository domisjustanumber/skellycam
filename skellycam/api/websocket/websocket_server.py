import asyncio
import logging
import os

import msgspec
from starlette.websockets import WebSocket, WebSocketState, WebSocketDisconnect
from fastapi import FastAPI

from skellylogs import LogRecordModel, LogLevels
from skellylogs.handlers.websocket_log_queue_handler import get_websocket_log_queue

from skellycam.api.websocket.preview_relay import PreviewRelay
from skellycam.api.websocket.websocket_message_types import WebsocketMessageType
from skellycam.core.camera_group.camera_group_manager import CameraGroupManager, get_or_create_camera_group_manager
from skellycam.core.capture_timings import PreviewTimings
from skellycam.utilities.wait_functions import await_10ms

logger = logging.getLogger(__name__)

CAPTURE_TIMINGS_INTERVAL_S = 1.0  # capture-timings.md 6.4: one `capture_timings` message each interval

# Reusable msgspec JSON encoder for all websocket JSON messages
_ws_json_encoder = msgspec.json.Encoder()


class WebsocketServer:
    def __init__(self, app: FastAPI, websocket: WebSocket):
        self.websocket = websocket
        self.global_kill_flag = app.state.global_kill_flag
        self._cgm: CameraGroupManager = get_or_create_camera_group_manager(app=app)

        self._websocket_should_continue = True
        self.ws_tasks: list[asyncio.Task] = []

        # Serialize all websocket sends — the `websockets` library does not
        # support concurrent writes on the same connection. Without this lock,
        # two tasks calling send_json/send_bytes at the same time hit an
        # internal `assert waiter is None or waiter.cancelled()` in the
        # protocol drain logic.
        self._send_lock = asyncio.Lock()
        self._preview_timings = PreviewTimings()  # the preview steps of this connection (capture-timings.md 6.5)
        # preview-4b.md 4.1: one sender for each connection; its send of the bytes holds the send lock, and its
        # `preview_send` bracket starts after the lock (capture-timings.md 6.5, Q839)
        self._preview = PreviewRelay(self._cgm, self._send_bytes_in_lock, self._send_msgspec_json,
                                     step_set=self._preview_timings.steps, send_lock=self._send_lock)

    async def __aenter__(self):
        logger.debug("Entering WebsocketRunner context manager...")
        self._websocket_should_continue = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.debug("WebsocketRunner context manager exiting...")
        self._websocket_should_continue = False

        # Only close if still connected
        if self.websocket.client_state == WebSocketState.CONNECTED:
            await self.websocket.close()
        # Cancel all tasks
        for task in self.ws_tasks:
            if not task.done():
                task.cancel()
        logger.debug("WebsocketRunner context manager exited.")

    @property
    def should_continue(self) -> bool:
        return (
            not self.global_kill_flag.value
            and self._websocket_should_continue
            and self.websocket.client_state == WebSocketState.CONNECTED
        )

    def _signal_shutdown(self) -> None:
        """Signal all tasks to stop and cancel them."""
        self._websocket_should_continue = False
        for task in self.ws_tasks:
            if not task.done():
                task.cancel()

    async def _send_json(self, data: dict) -> None:
        """Send JSON through the websocket, serialized by the send lock."""
        async with self._send_lock:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.send_json(data)

    async def _send_bytes_in_lock(self, data: bytes | bytearray | memoryview) -> None:
        """Send bytes; the caller holds the send lock."""
        if self.websocket.client_state == WebSocketState.CONNECTED:
            await self.websocket.send_bytes(data)

    async def _send_text(self, data: str) -> None:
        """Send text through the websocket, serialized by the send lock."""
        async with self._send_lock:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(data)

    async def _send_msgspec_json(self, data: object) -> None:
        """Encode any msgspec-compatible object to JSON and send as text.

        Works with msgspec.Struct instances, dicts, lists, and basic types.
        Faster than send_json (which uses stdlib json.dumps internally).
        """
        async with self._send_lock:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(_ws_json_encoder.encode(data).decode("utf-8"))

    async def run(self):
        logger.info("Starting websocket runner...")
        self.ws_tasks = [
            asyncio.create_task(self._preview_relay(), name="WebsocketPreviewRelay"),
            asyncio.create_task(self._logs_relay(), name="WebsocketLogsRelay"),
            asyncio.create_task(self._client_message_handler(), name="WebsocketClientMessageHandler"),
            asyncio.create_task(self._app_state_sender(), name="WebsocketStateSender"),
        ]

        try:
            await asyncio.gather(*self.ws_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.debug("Websocket runner cancelled")
        except Exception as e:
            logger.exception(f"Error in websocket runner: {e.__class__}: {e}")
            raise
        finally:
            for task in self.ws_tasks:
                if not task.done():
                    task.cancel()

    async def _preview_relay(self):
        """The camera messages of this connection (preview-4b.md 4.1 item 2): `PreviewRelay.run`, with the `except`
        clauses of `_logs_relay`."""
        logger.info("Starting preview relay...")
        try:
            await self._preview.run()
        except asyncio.CancelledError:
            logger.debug("Preview relay task cancelled")
        except (WebSocketDisconnect, AssertionError):
            logger.info("Client disconnected, ending preview relay task...")
        except RuntimeError as e:
            if "close" in str(e).lower():
                logger.info("Websocket closed during preview send, ending task...")
            else:
                raise
        except Exception as e:
            logger.exception(f"Error in preview relay: {e.__class__}: {e}")
            self.global_kill_flag.value = True
            raise
        finally:
            self._signal_shutdown()

    async def _logs_relay(self, ws_log_level: int = LogLevels.TRACE.value):
        logger.info("Starting websocket log relay listener...")
        logs_queue = get_websocket_log_queue()
        try:
            while self.should_continue:
                if not logs_queue.empty():
                    log_record: LogRecordModel = LogRecordModel(**logs_queue.get_nowait())
                    if log_record.levelno < ws_log_level:
                        continue
                    log_data = log_record.model_dump()
                    await self._send_msgspec_json(log_data)
                else:
                    await await_10ms()
        except asyncio.CancelledError:
            logger.debug("Log relay task cancelled")
        except (WebSocketDisconnect, AssertionError):
            logger.info("Client disconnected, ending log relay task...")
        except RuntimeError as e:
            if "close" in str(e).lower():
                logger.info("Websocket closed during log relay send, ending task...")
            else:
                raise
        except Exception as e:
            logger.exception(f"Error in websocket log relay: {e.__class__}: {e}")
            self.global_kill_flag.value = True
            raise
        finally:
            self._signal_shutdown()

    async def _app_state_sender(self):
        """
        Periodically send the application state to the frontend.
        """
        logger.info("Starting state sender task...")
        previous_state: dict | None = None
        timings_failed = False  # one log line for a timings message that cannot be built
        try:
            while self.should_continue:
                try:
                    state_dict = self._cgm.to_state_dict()
                except Exception as error:  # one state read: the next tick reads again; no kill of the app for it
                    logger.exception(f"The app state could not be read; the next tick tries again: {error!r}")
                    await asyncio.sleep(1.0)
                    continue
                if previous_state is None or state_dict != previous_state:
                    state_message = {
                        "message_type": WebsocketMessageType.APP_STATE,
                        "server_pid": os.getpid(),
                        "state": state_dict
                    }
                    await self._send_msgspec_json(state_message)
                try:  # capture-timings.md 6.4: a fault of the timings never ends the app, also not during a take
                    timings_text = _ws_json_encoder.encode(self._capture_timings_message()).decode("utf-8")
                except Exception as error:
                    timings_text = None
                    if not timings_failed:
                        timings_failed = True
                        logger.exception(f"The capture timings message could not be built; no message: {error!r}")
                if timings_text is not None:
                    await self._send_text(timings_text)
                await asyncio.sleep(CAPTURE_TIMINGS_INTERVAL_S)
                previous_state = state_dict
        except asyncio.CancelledError:
            logger.debug("State sender task cancelled")
        except (WebSocketDisconnect, AssertionError):
            logger.info("Client disconnected, ending state sender task...")
        except RuntimeError as e:
            if "close" in str(e).lower():
                logger.info("Websocket closed during state send, ending task...")
            else:
                raise
        except Exception as e:
            # A fault of the sender itself (a send that fails, not a disconnect): the client would lose the state
            # with no sign, so the app ends, as for the other tasks of this connection.
            logger.exception(f"Error in state sender: {e.__class__}: {e}")
            self.global_kill_flag.value = True
            raise
        finally:
            self._signal_shutdown()
            logger.info("Ending state sender task...")

    def _capture_timings_message(self) -> dict:
        """capture-timings.md 6.4: the body of `capture_timings()`, with the preview summaries of this connection."""
        body = self._cgm.capture_timings()
        preview = self._preview_timings.summaries(body["log_capture_times"], list(self._cgm.camera_groups))
        return {"message_type": WebsocketMessageType.CAPTURE_TIMINGS, **body, "summaries": body["summaries"] + preview}

    async def _client_message_handler(self):
        """
        Handle messages from the client. Acts as the disconnect sentinel —
        when the client disconnects, this task signals all other tasks to stop.
        """
        logger.info("Starting client message handler...")
        try:
            while self.should_continue:
                message = await self.websocket.receive()

                message_type: str = message.get("type", "")

                # ASGI disconnect message — client is gone
                if message_type == "websocket.disconnect":
                    logger.info(f"Client disconnected (code={message.get('code', 'unknown')}), shutting down websocket tasks...")
                    self._signal_shutdown()
                    return

                if "text" in message:
                    text_content: str = message["text"]
                    if self._preview.handle_text(text_content):  # a ready message (preview-4b.md 4.1 item 3)
                        continue
                    if text_content.strip() == "ping":
                        await self._send_text("pong")
                    elif text_content.strip() == "pong":
                        pass
                    else:
                        logger.info(f"Websocket received message: `{text_content}`")
                elif "bytes" in message:
                    logger.trace(f"Received binary websocket message ({len(message['bytes'])} bytes)")
                else:
                    raise RuntimeError(f"Unexpected ASGI websocket message: {message}")

        except WebSocketDisconnect:
            logger.info("Client disconnected (WebSocketDisconnect), shutting down websocket tasks...")
        except asyncio.CancelledError:
            logger.debug("Client message handler task cancelled")
        except Exception as e:
            logger.exception(f"Error handling client message: {e.__class__}: {e}")
            self.global_kill_flag.value = True
            raise
        finally:
            self._signal_shutdown()
            logger.info("Ending client message handler...")
