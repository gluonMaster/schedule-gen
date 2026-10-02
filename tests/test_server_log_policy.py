"""Server log policy: no successful polling lines, daily files kept for 30 days."""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gear_xls.log_policy import QuietPollingFilter, server_log_handler


def access(request_line, code):
    # The record werkzeug's request handler produces for one access line.
    return logging.LogRecord("werkzeug", logging.INFO, __file__, 1, '127.0.0.1 - - [02/Oct/2026 11:19:13] "%s" %s %s',
                             (request_line, code, "-"), None)


def test_successful_polls_are_dropped_but_requests_and_failures_stay():
    quiet = QuietPollingFilter()
    for line in ("GET /health HTTP/1.1", "GET /api/status HTTP/1.1", "GET /api/restore/status HTTP/1.1"):
        assert not quiet.filter(access(line, "200"))
    assert quiet.filter(access("GET /health HTTP/1.1", "\x1b[1m\x1b[35m500\x1b[0m"))
    assert quiet.filter(access("GET /api/status HTTP/1.1", "401"))
    assert quiet.filter(access("POST /api/blocks HTTP/1.1", "200"))
    assert quiet.filter(access("GET /schedule HTTP/1.1", "200"))
    assert quiet.filter(logging.LogRecord("server_routes", logging.INFO, __file__, 1, "Запуск Flask-сервера", (), None))


def test_log_rotates_at_midnight_and_keeps_30_days(tmp_path):
    for day in range(1, 32):  # 31 older daily files: one more than kept
        (tmp_path / f"flask_server.log.2026-08-{day:02d}").write_text("old", encoding="utf-8")
    handler = server_log_handler(str(tmp_path / "flask_server.log"))
    try:
        assert (handler.when, handler.backupCount) == ("MIDNIGHT", 30)
        assert [Path(p).name for p in handler.getFilesToDelete()] == ["flask_server.log.2026-08-01"]
    finally:
        handler.close()
