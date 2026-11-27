"""The real server of `skellycam/__main__.py` for `test_server_exit.py`.

argv: port, base folder, log file. No telemetry, no bytecode pass, the base folder and the log file in a temporary
folder.
"""

import sys

import skellycam.__main__ as skellycam_main
import skellycam.api.server_constants as server_constants
import skellycam.app as app_module
import skellycam.system.default_paths as default_paths

port, base_folder, log_file = sys.argv[1:4]
server_constants.PORT = int(port)
app_module.initialize_telemetry = lambda: None
app_module.shutdown_telemetry = lambda: None
app_module.ensure_bytecode_compiled = lambda: None
app_module.get_default_skellycam_base_folder_path = lambda: base_folder
default_paths.get_log_file_path = lambda: log_file

if __name__ == "__main__":
    skellycam_main.entry_point()
