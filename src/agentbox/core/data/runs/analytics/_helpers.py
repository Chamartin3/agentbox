"""Shared helpers for analytics queries — no intra-package imports."""

from sqlalchemy import Integer, cast, func


def _duration_ms_expr(c_started, c_finished):
    epoch_finished = cast(func.strftime("%s", c_finished), Integer)
    epoch_started = cast(func.strftime("%s", c_started), Integer)
    return (epoch_finished - epoch_started) * 1000
