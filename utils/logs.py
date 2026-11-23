"""The bot's log file: data/logs/bot.log (2 MB per file, the last 5 files are kept).

Everything the bot window shows goes there too (also messages of discord.py, which bot.login()/bot.connect() don't
switch on by themselves), with tokens, keys and user folder names hidden, so the file can be sent to the bot's author.
"""
import logging
import logging.handlers
import os
import sys
import threading

from utils import config_store

LOG_DIR = os.path.join(config_store.DATA_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

_installed = {"done": False}


class _Sanitize(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        from utils import error_reports  # imported late: it needs the config, the log is set up before it
        try:
            message = record.getMessage()
        except Exception:
            return True
        clean = error_reports.sanitize(message)
        if clean != message or record.args:
            record.msg, record.args = clean, None
        if record.exc_info and record.exc_info[1] is not None:
            import traceback
            record.exc_text = error_reports.sanitize("".join(traceback.format_exception(*record.exc_info)))
        return True


class _Tee:
    """A console stream that also writes every complete line to the log file."""

    def __init__(self, stream, logger: logging.Logger, level: int):
        self._stream, self._logger, self._level = stream, logger, level
        self._buffer = ""
        self._lock = threading.Lock()
        self._inside = threading.local()

    def write(self, text):
        written = self._stream.write(text)
        # The log file can't be written (full disk, a file another program holds): logging writes that error to
        # stderr, which is this stream again. Such text goes to the console only; logging it again would wait for the
        # lock this thread already holds and hang the whole bot.
        if getattr(self._inside, "active", False):
            return written
        self._inside.active = True
        try:
            with self._lock:
                self._buffer += str(text)
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    if line.strip():
                        self._logger.log(self._level, line.rstrip("\r"))
        finally:
            self._inside.active = False
        return written

    def flush(self):
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def setup() -> str:
    """Turns on the log file and the console log of discord.py. Returns the path of the log file."""
    if _installed["done"]:
        return LOG_FILE
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5,
                                                        encoding="utf-8", delay=True)
    file_handler.setFormatter(logging.Formatter(FORMAT, "%Y-%m-%d %H:%M:%S"))
    file_handler.addFilter(_Sanitize())

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    console.addFilter(_Sanitize())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

    # print() output of the bot goes to the file as well, but not twice to the console
    printed = logging.getLogger("console")
    printed.propagate = False
    printed.addHandler(file_handler)
    sys.stdout = _Tee(sys.stdout, printed, logging.INFO)
    sys.stderr = _Tee(sys.stderr, printed, logging.WARNING)
    _installed["done"] = True
    return LOG_FILE
