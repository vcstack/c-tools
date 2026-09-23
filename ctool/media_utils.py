import os
import re
import shutil
import subprocess
import sys
import unicodedata

import shlex

from .logging_setup import logger


def run_command(command):
    logger.debug(command)
    if isinstance(command, str):
        command = shlex.split(command)

    sub_params = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "creationflags": subprocess.CREATE_NO_WINDOW
        if sys.platform == "win32"
        else 0,
    }
    process_command = subprocess.Popen(command, **sub_params)
    _output, errors = process_command.communicate()
    if process_command.returncode != 0:
        err = errors.decode(errors.encoding or "utf-8", errors="replace")
        logger.error("Command failed")
        raise RuntimeError(err.strip() or f"Command failed with code {process_command.returncode}")


def sanitize_file_name(file_name):
    normalized_name = unicodedata.normalize("NFKD", file_name)
    return re.sub(r"[^\w\s.-]", "_", normalized_name)


def remove_directory_contents(directory_path):
    if not os.path.exists(directory_path):
        return
    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except OSError as exc:
            logger.error(f"Failed to delete {file_path}: {exc}")
