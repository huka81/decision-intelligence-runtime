"""DFID logging context (Filter + ContextVar)."""

from __future__ import annotations

import io
import logging

from dir_core.utils.logging_utils import (
    CONSOLE_FORMAT,
    DEFAULT_DFID,
    DfidContextFilter,
    log_context,
)


def _logger_with_buffer() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(DfidContextFilter())
    handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    logger = logging.getLogger("test.dfid.context")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_filter_defaults_to_placeholder() -> None:
    record = logging.LogRecord("n", logging.INFO, __file__, 1, "msg", (), None)
    assert DfidContextFilter().filter(record) is True
    assert record.dfid == DEFAULT_DFID


def test_log_context_binds_dfid_on_records() -> None:
    logger, stream = _logger_with_buffer()
    with log_context(dfid="flow-abc"):
        logger.info("KERNEL_GATES_PASSED")
    assert "[DFID=flow-abc] KERNEL_GATES_PASSED" in stream.getvalue()


def test_log_context_resets_after_exit() -> None:
    logger, stream = _logger_with_buffer()
    with log_context(dfid="flow-abc"):
        logger.info("inside")
    logger.info("outside")
    text = stream.getvalue()
    assert "[DFID=flow-abc] inside" in text
    assert "[DFID=-] outside" in text
