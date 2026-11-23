"""A log file that can't be written (full disk, a file another program holds) never hangs the bot: logging prints that
error to stderr, which the bot also copies to the log file (utils/logs.py _Tee)."""
import io
import logging
import sys
import threading
import unittest

from utils import logs


class BrokenFile(logging.Handler):
    def emit(self, record):
        try:
            raise OSError("No space left on device")
        except OSError:
            self.handleError(record)  # what a real file handler does: prints the error to sys.stderr


class LogFileErrors(unittest.TestCase):
    def test_a_failing_log_file_does_not_hang_the_bot(self):
        logger = logging.getLogger("test_log_file_errors")
        logger.propagate = False
        logger.handlers = [BrokenFile()]
        console = io.StringIO()
        tee = logs._Tee(console, logger, logging.WARNING)
        saved = sys.stderr
        done = threading.Event()

        def write():
            sys.stderr = tee
            try:
                tee.write("the bot prints a line\n")
                logger.warning("and logs one")  # outside the console stream: the error goes to stderr = tee
            finally:
                sys.stderr = saved
                done.set()

        worker = threading.Thread(target=write, daemon=True)
        worker.start()
        self.assertTrue(done.wait(5), "writing hung: the bot would be offline without a trace")
        self.assertIn("the bot prints a line", console.getvalue())
        self.assertIn("No space left on device", console.getvalue(), "the error is still shown in the window")


if __name__ == "__main__":
    unittest.main()
