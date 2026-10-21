"""Make a gate run prove that its tests actually ran.

pyproject's addopts deselects gate tests by default (-m 'not gate and not live'), and `make gate`
relies on a later -m gate overriding that. When FATHOM_GATE=1 (set by `make gate`), the run fails
if any gate test was deselected or skipped, or if no gate test ran at all.
"""

import os
from pathlib import Path

import pytest

GATES_DIR = Path(__file__).resolve().parent

_deselected: list[str] = []
_outcomes: dict[str, str] = {}


def _is_gate_test(item_or_report) -> bool:
    path = Path(str(getattr(item_or_report, "fspath", ""))).resolve()
    return path.parent == GATES_DIR


def pytest_deselected(items: list[pytest.Item]) -> None:
    _deselected.extend(item.nodeid for item in items if _is_gate_test(item))


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if not _is_gate_test(report):
        return
    if report.when == "call" or (report.when == "setup" and not report.passed):
        _outcomes[report.nodeid] = report.outcome


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if os.environ.get("FATHOM_GATE") != "1":
        return
    problems = []
    if _deselected:
        problems.append(f"{len(_deselected)} gate test(s) deselected: {', '.join(_deselected)}")
    skipped = [nodeid for nodeid, outcome in _outcomes.items() if outcome == "skipped"]
    if skipped:
        problems.append(f"{len(skipped)} gate test(s) skipped: {', '.join(skipped)}")
    ran = [nodeid for nodeid, outcome in _outcomes.items() if outcome in ("passed", "failed")]
    if not ran:
        problems.append("no gate tests ran")

    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if problems:
        for problem in problems:
            reporter.write_line(f"GATE CHECK FAILED: {problem}", red=True, bold=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    else:
        reporter.write_line(f"GATE CHECK: {len(ran)} gate tests ran, 0 deselected, 0 skipped")
