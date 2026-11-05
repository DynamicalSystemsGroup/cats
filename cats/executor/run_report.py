"""Optional run report for one one-shot Executor call.

The peer does not open a report. When ``governed_run`` is absent, every
helper returns without doing anything.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar('T')


def open_report():
    """Return a report, or ``None`` when no report module is installed."""
    try:
        from cats.executor.governed_run import GovernedRun
    except ImportError:
        return None
    return GovernedRun.open()


def run_phase(report, name: str, fn: Callable[[], T]) -> T:
    """Run ``fn`` inside a named phase when ``report`` is open."""
    if report is None:
        return fn()
    return report.phase(name, fn)


def note_started(report) -> None:
    if report is None:
        return
    report.started()


def note_finished(report) -> None:
    if report is None:
        return
    report.finished()


def note_failure(report, exc: BaseException) -> None:
    if report is None:
        return
    report.failed(exc)


def closing_line(report) -> dict[str, Any] | None:
    """Extra stdout object, or ``None`` when no report module is installed."""
    try:
        from cats.executor.governed_run import closing_line as _line
    except ImportError:
        return None
    return _line(report)
