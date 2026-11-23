
"""Top-level package for skellycam."""

__author__ = """Skelly FreeMoCap"""
__email__ = "info@freemocap.org"
__version__ = "v2.0.0-alpha.6"

__description__ = "A simple python API for efficiently connecting to and recording synchronized videos from one or multiple cameras 💀📸"
__package_name__ = "skellycam"
__repo_url__ = f"https://github.com/freemocap/{__package_name__}"
__repo_issues_url__ = f"{__repo_url__}/issues"
__pypi_url__ = f"https://pypi.org/project/{__package_name__}"

__package_root__ = str(__import__("pathlib").Path(__file__).parent)

from beartype.claw import beartype_this_package
beartype_this_package()

# Before any module loads OpenCV: a camera process on Windows takes the warning pipe of the main process (5.6).
from skellycam.core.camera.capture.warning_pipe import attach_stderr_pipe
attach_stderr_pipe()

import multiprocessing

multiprocessing.freeze_support()

from skellylogs import LogLevels


LOG_LEVEL = LogLevels.TRACE


def certify(level: str, progress=None, cancel=None, *, cameras=None, recording_folder=None, test_media_dir=None,
            abandon=None) -> dict:
    """The certify run of skellycam (specs/certify.md 1; contract `report-format.md` 2.1, 2.4). Imported on call."""
    from skellycam.core.certify.run import certify as run
    return run(level, progress, cancel, cameras=cameras, recording_folder=recording_folder,
               test_media_dir=test_media_dir, abandon=abandon)


def certify_plan(level: str, *, cameras=None, recording_folder=None, test_media_dir=None) -> dict:
    """The plan of a certify run (specs/certify.md 9.1; contract 2.6). It opens no camera."""
    from skellycam.core.certify.run import certify_plan as plan
    return plan(level, cameras=cameras, recording_folder=recording_folder, test_media_dir=test_media_dir)


__all__ = [
    "__author__",
    "__email__",
    "__version__",
    "__description__",
    "__package_name__",
    "__repo_url__",
    "__repo_issues_url__",
    "__pypi_url__",
    "certify",
    "certify_plan",
]
