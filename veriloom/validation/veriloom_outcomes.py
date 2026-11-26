"""pytest plugin: record the outcome of every test node id to $VERILOOM_OUTCOMES_FILE.

Self-contained (standard library + pytest only) because the same file is shipped
inside every Harbor task's tests/ directory and loaded with `-p veriloom_outcomes`.
Outcomes: "passed", "failed" (any phase failed, or a collection error) or "skipped".
"""

import json
import os

_results = {}


def pytest_collectreport(report):
    if report.failed:
        _results[report.nodeid or "<collection>"] = "failed"


def pytest_runtest_logreport(report):
    prev = _results.get(report.nodeid)
    if report.failed:
        _results[report.nodeid] = "failed"
    elif report.skipped:
        if prev != "failed":
            _results[report.nodeid] = "skipped"
    elif report.when == "call" and prev is None:
        _results[report.nodeid] = "passed"


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("VERILOOM_OUTCOMES_FILE")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_results, f, indent=0, sort_keys=True)


def feature_key(nodeid):
    """Location-independent id for a hidden feature test: '<file name>::<test>'.

    Hidden tests live outside the repository (a temp dir in the sandbox,
    /tests/feature in Harbor), so their node ids differ only in the directory part.
    """
    path, sep, rest = nodeid.partition("::")
    return path.replace("\\", "/").rsplit("/", 1)[-1] + sep + rest
