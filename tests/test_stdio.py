"""Phase 3 gap — stdio wrapper keeps the binary buffer, text goes to stderr."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack.transports.stdio import SafeStdoutWrapper, safe_stdio_transport


def test_safe_stdout_writes_text_to_stderr(capsys):
    original = sys.stdout
    wrapper = SafeStdoutWrapper(original)
    wrapper.write("hello-stdio")
    wrapper.flush()
    captured = capsys.readouterr()
    assert "hello-stdio" in captured.err
    assert wrapper.buffer is original.buffer


def test_safe_stdio_transport_restores_stdout():
    original = sys.stdout
    with safe_stdio_transport():
        assert isinstance(sys.stdout, SafeStdoutWrapper)
        sys.stdout.write("during")
    assert sys.stdout is original


def test_safe_stdout_getattr_forwards_unknown_attrs():
    class Fake:
        buffer = object()
        encoding = "utf-8"

    wrapper = SafeStdoutWrapper(Fake())
    assert wrapper.encoding == "utf-8"
