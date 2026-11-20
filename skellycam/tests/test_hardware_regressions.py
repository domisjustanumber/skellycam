"""Regressions reproduced by Core's physical-camera API harness."""
import multiprocessing
import subprocess
import sys
from unittest.mock import Mock

import pytest

from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry


@pytest.mark.asyncio
async def test_closing_empty_python_manager_does_not_disable_future_streaming():
    manager = CameraGroupManager(multiprocessing.Value('b', False), Mock(spec=WorkerRegistry))
    await manager.close_all_camera_groups()
    assert not manager.closing


def test_worker_monitor_delivers_the_registered_shutdown_handler():
    program = '''
import multiprocessing, signal
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.ipc.process_management.managed_worker import WorkerMode
observed = []
signal.signal(signal.SIGTERM, lambda *_: observed.append(True))
registry = WorkerRegistry(global_kill_flag=multiprocessing.Value('b', True), worker_mode=WorkerMode.PROCESS)
registry._child_monitor_loop()
registry.shutdown_all()
raise SystemExit(0 if observed else 2)
'''
    completed = subprocess.run([sys.executable, '-B', '-c', program], capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
