"""Phase 6 — FileLogger stays off stdout for STDIO safety."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack.core.context import FileLogger


def test_file_logger_writes_to_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT_TYPE", raising=False)
    monkeypatch.delenv("NITROSTACK_LOG_TO_STDOUT", raising=False)
    log_path = tmp_path / "nitrostack.log"
    logger = FileLogger(log_file=str(log_path), name="phase6-logger")
    logger.info("phase-6 coverage")
    logger.debug("dbg", meta={"k": 1})
    logger.warn("warn-line")
    logger.error("err-line")
    text = log_path.read_text(encoding="utf-8")
    assert "phase-6 coverage" in text
    assert "warn-line" in text
    assert "err-line" in text


def test_file_logger_can_write_stdout(monkeypatch, capsys):
    monkeypatch.setenv("NITROSTACK_LOG_TO_STDOUT", "true")
    logger = FileLogger(name="phase6-stdout")
    logger.info("to-stdout")
    captured = capsys.readouterr()
    assert "to-stdout" in captured.out



def test_file_logger_falls_back_to_stderr_when_file_unwritable(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT_TYPE", raising=False)
    monkeypatch.delenv("NITROSTACK_LOG_TO_STDOUT", raising=False)
    blocked = tmp_path / "no-such-dir" / "nested" / "nitrostack.log"
    logger = FileLogger(log_file=str(blocked), name="phase6-unwritable-logger")
    logger.info("fell-back")
    captured = capsys.readouterr()
    assert "fell-back" in captured.err
    assert not blocked.exists()
