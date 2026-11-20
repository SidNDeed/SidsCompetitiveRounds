"""A module logger's info lines reach the api's container log.

The api's own diagnostic lines are print() calls to stdout (Dockerfile, the
note above CMD; compose sets PYTHONUNBUFFERED). uvicorn configures only its
own loggers (uvicorn, uvicorn.error, uvicorn.access) and nothing in the api
gives the ROOT logger a handler, so a module logger made with
logging.getLogger(name) propagates to a root that has none: Python's
last-resort printer then writes its WARNING records to stderr and DROPS every
info record. print_info_lines(logger) gives ONE module logger a handler that
writes each record through print() as its own line, at INFO.

Per module, never the root: a root at INFO would also print the info lines
of the libraries (the HTTP client's request lines carry full URLs). The
logger keeps propagating, so a handler on the root (pytest's caplog, any
later one) still sees its records; and because a handler now exists in the
chain, the last-resort printer is not used, so nothing prints twice.
Standard library only.
"""
import logging


class _PrintHandler(logging.Handler):
    """Writes a record's message as one print() line (sys.stdout read at
    emit time, as every print() of the api does)."""

    def emit(self, record):
        try:
            print(self.format(record), flush=True)
        except Exception:
            self.handleError(record)


def print_info_lines(logger):
    """Give `logger` (a module logger, never the root) one print handler at
    INFO and return it. Calling it again adds no second handler."""
    if logger is logging.getLogger():
        raise ValueError("print_info_lines is per module; the root logger is not one")
    if not any(isinstance(h, _PrintHandler) for h in logger.handlers):
        handler = _PrintHandler(level=logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
