"""Size policy of the Flask server log: daily files kept for 30 days, no polling noise.

Almost all of the former log (100 of 102 MB in 45 days) were access lines of the tray health
check, which polls /health every 2 seconds. Successful automatic polls are not logged; failed
ones and every other request still are.
"""
import logging
import re
from logging.handlers import TimedRotatingFileHandler

LOG_RETENTION_DAYS = 30
_POLLING_REQUEST = re.compile(r'"GET (?:/health|/api/status|/api/restore/status)(?:\?\S*)? HTTP/[\d.]+" 200 ')
_ANSI_STYLE = re.compile(r"\x1b\[[0-9;]*m")


class QuietPollingFilter(logging.Filter):
    """Drops werkzeug access lines of successful health/status polls."""

    def filter(self, record):
        return not _POLLING_REQUEST.search(_ANSI_STYLE.sub("", record.getMessage()))


def server_log_handler(path):
    """A new file every midnight (old ones as <name>.YYYY-MM-DD); files beyond 30 days are deleted."""
    return TimedRotatingFileHandler(path, when="midnight", backupCount=LOG_RETENTION_DAYS, encoding="utf-8")
