"""Only one copy of the bot may run from one folder at a time.

Two copies would both answer every command and send every change to the game twice, and fight over the same files.
The running bot holds a lock on data/bot.lock; the operating system releases it by itself when the bot stops, even
after a crash, so a leftover file never blocks the next start.
"""
import os

from utils import config_store

LOCK_PATH = os.path.join(config_store.DATA_DIR, "bot.lock")
ALREADY_RUNNING_EXIT_CODE = 4


class InstanceLock:
    def __init__(self, path: str = LOCK_PATH):
        self.path = path
        self._file = None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        handle = open(self.path, "a+b")
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._file = handle
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._file.close()
            self._file = None


def is_running(path: str = LOCK_PATH) -> bool:
    """True when a bot holds the lock of this folder right now."""
    probe = InstanceLock(path)
    if probe.acquire():
        probe.release()
        return False
    return True
