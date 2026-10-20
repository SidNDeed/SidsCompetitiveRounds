"""Seat adapter for both Stage 2 registries (whole backend copies, fail closed).

Select one row with test_srv_registry_row[C-row] or [U-row].  This module
also acts as the child pytest observation plugin; it never changes a test's
assertion expression or message.  Each variant uses one fresh complete backend
copy, removed after its result is recorded.  A child error never counts as a kill.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import time
import subprocess
import sys
import tempfile

import pytest

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".env*", "*.env")
TIMEOUT_S = 900


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C = _load("_srv_seat_controls", HERE / "srv_stage_controls.py")
U = _load("_srv_seat_runner", HERE / "evidence" / "match-hold-mutation-runner.py")
CASES = [("C", row["row"], row) for row in C.ROWS]
CASES += [("U", mid, row) for mid, row in U.MUTANTS.items()]

BASE_C = frozenset(('L1.BOUND',
 'F1.M2.ROSTER',
 'MERGED.FIX1.M1.ROLLBACK',
 'MERGED.FIX1.H3.RESELECT',
 'F1.H1.NEW',
 'F1.H1.GAME',
 'M1.5',
 'M1.6',
 'M3.4',
 'M3.13',
 'M3.14',
 'M3.15',
 'M5.1',
 'M6.1',
 'H3.rq.G',
 'H3.rq.R',
 'H3.tq.G',
 'H3.tq.R',
 'H3.tr.G',
 'H3.tr.R',
 'H3.oq.G',
 'H3.oq.R',
 'H3.le.G',
 'H3.le.R',
 'H3.ts.G',
 'H3.ts.R',
 'H3.os.G',
 'H3.os.R',
 'H3.fe.G',
 'H3.fe.R',
 'H3.fl.G',
 'H3.fl.R',
 'H3.fq.G',
 'H3.fq.R',
 'F1.H4.RECEIPT',
 'F1.H4.DELETE_WINDOW',
 'F1.H4.RETRY',
 'F1.H4.RECEIPT_BOUND'))
BASE_U = frozenset(('FIX1B.R1.SAVEPOINT',
 'F1.L2.BASELINE',
 'F1.L2.INVERSE',
 'M5.10',
 'MERGED.FIX1.H2.CAUSAL',
 'MERGED.FIX1.H2.EXPIRY',
 'MERGED.FIX1.H1.RECEIPT',
 'F1.H1',
 'F1.H2.OMIT',
 'F1.H2.STALE',
 'F1.H3.GATE',
 'F1.H3.RECHECK',
 'F1.M3',
 'F1.M2.CHECKOUT',
 'F1.M2.LOCK',
 'F1.H4',
 'F1.H6',
 'F1.M5',
 'F1.M4',
 'F1.H5',
 'F1.M8.LITERAL.DEFAULT',
 'F1.M8.LITERAL.CONSTRAINT',
 'F1.M8.LITERAL.INDEX',
 'F1.M8.COL',
 'F1.M8.DEFAULT',
 'F1.M8.CONSTRAINT',
 'F1.M8.INDEX',
 'F1.M1',
 'F1.M6.TUPLE',
 'F1.M6.SIG',
 'NX0a',
 'F1.M7',
 'F1.L1',
 'M1.7',
 'M1.8',
 'M1.L1',
 'M1.L2',
 'M2.1',
 'M2.2',
 'M2.3',
 'M2.4',
 'M2.5',
 'M2.6',
 'M2.7',
 'M2.14',
 'M3.1',
 'M3.2',
 'M3.3',
 'M3.18',
 'M5.4',
 'M5.5',
 'M5.6',
 'M5.7',
 'M6.1',
 'MERGED.FIX1.H4.BEAT',
 'MERGED.FIX1.H4.OPEN_FINAL',
 'MERGED.FIX1.H4.OPEN_CLAIM',
 'MERGED.FIX1.H4.ATTEMPT',
 'MERGED.FIX1.H4.MINE',
 'MERGED.FIX1.H4.CLAIM',
 'MERGED.FIX1.H4.CLAIM_AUDIT',
 'MERGED.FIX1.H4.BIND',
 'MERGED.FIX1.H4.ENTERED',
 'MERGED.FIX1.H4.END',
 'MERGED.FIX1.H4.SEEN',
 'MERGED.FIX1.H4.WINDOW_RECEIVE',
 'MERGED.FIX1.H4.WINDOW_SETTLE',
 'MERGED.FIX1.H4.WINDOW_RELEASE',
 'MERGED.FIX1.H4.WINDOW_SUPERSEDE',
 'MERGED.FIX1.H4.WINDOW_FINISH',
 'MERGED.FIX1.H4.JOURNAL',
 'MERGED.FIX1.H4.MARK',
 'MERGED.FIX1.H4.TERMINAL_ATTRIBUTION'))


def _assertion_at(path, line):
    """The innermost failing frame must itself be an actual assert statement."""
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, SyntaxError):
        return None
    for owner in tree.body:
        if not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not owner.lineno <= line <= owner.end_lineno:
            continue
        for node in ast.walk(owner):
            if isinstance(node, ast.Assert) and node.lineno <= line <= node.end_lineno:
                expression = ast.unparse(node.test)
                message = ast.unparse(node.msg) if node.msg else None
                siblings = sorted((other for other in ast.walk(owner)
                                   if isinstance(other, ast.Assert)
                                   and ast.unparse(other.test) == expression
                                   and (ast.unparse(other.msg) if other.msg else None) == message),
                                  key=lambda other: other.lineno)
                return {"file": Path(path).name, "function": owner.name,
                        "expression": expression, "message_source": message,
                        "occurrences": len(siblings), "ordinal": siblings.index(node)}
    return None


# The parent does not set this variable.  Only child pytest invocations write
# these observations, inside that variant's scratch directory.
_CHILD_RUN = {"collected": 0, "collection_errors": [], "reports": []}


def pytest_collectreport(report):
    if os.environ.get("SRV_REGISTRY_REPORT") and report.failed:
        _CHILD_RUN["collection_errors"].append(report.nodeid)


def pytest_collection_finish(session):
    if os.environ.get("SRV_REGISTRY_REPORT"):
        _CHILD_RUN["collected"] = len(session.items)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if not os.environ.get("SRV_REGISTRY_REPORT"):
        return
    report = outcome.get_result()
    row = {"node": item.nodeid, "phase": call.when, "outcome": report.outcome}
    if call.excinfo is not None:
        error = call.excinfo.value
        row["exception"] = type(error).__module__ + "." + type(error).__name__
        row["message"] = type(error).__name__ + ": " + str(error)
        # Pytest rewriting turns tuple assertion messages into strings with
        # an appended assertion explanation; use the registry's exact parser.
        row["tag"] = C.rc.first_tag(row["message"]) if isinstance(error, AssertionError) else None
        if call.excinfo.traceback:
            entry = call.excinfo.traceback[-1]
            row["assertion"] = _assertion_at(entry.path, entry.lineno + 1)
    _CHILD_RUN["reports"].append(row)


def pytest_sessionfinish(session, exitstatus):
    target = os.environ.get("SRV_REGISTRY_REPORT")
    if target:
        _CHILD_RUN["exitstatus"] = int(exitstatus)
        Path(target).write_text(json.dumps(_CHILD_RUN, sort_keys=True), encoding="utf-8")


def _test_file(family, row):
    return row["node"].split("::", 1)[0] if family == "C" else row[4]


def _selector(family, row):
    return row["node"].split("::", 1)[1] if family == "C" else row[5]


def _adverse(family, mid, row):
    return ({"tag": row["tag"]} if family == "C" else
            {"tags": U.INTENDED_ASSERTIONS[mid]} if mid in U.INTENDED_ASSERTIONS else U.RUNNER_ASSERTIONS[mid])


def _require_live_case(family, row):
    # Same deliberate opt-out form as cf_pg: an absent DSN otherwise fails.
    prefix = "RJ_TRIAGE_TEST_PG" if _test_file(family, row) == "test_ffa_quarantine_triage.py" else "CF_TEST_PG"
    dsn, optout = prefix + "_DSN", prefix + "_OPTOUT"
    if os.environ.get(dsn) and importlib.util.find_spec("asyncpg") is not None:
        return
    if os.environ.get(optout) == "1":
        pytest.skip(dsn + " is unset and " + optout + "=1: registry live coverage is deliberately waived")
    pytest.fail(dsn + " is unset or asyncpg is unavailable: registry live coverage did not run")


def _source(cache, relative):
    if relative not in cache:
        cache[relative] = (BACKEND.parent / relative).read_text(encoding="utf-8-sig")
    return cache[relative]


def _preflight(family, mid, row, cache):
    """Check each sequential plant's exact occurrence count without making copies."""
    anchors = 0
    for kind in ("mutant", "twin"):
        if family == "C":
            changed = {}
            for relative, old, new, count in row[kind]:
                original = changed.get(relative, _source(cache, relative))
                found = original.count(old)
                assert found == count, ("STALE", family, mid, kind, relative, found, count)
                changed[relative] = original.replace(old, new)
                anchors += count
            for relative, source in changed.items():
                if relative.endswith(".py"):
                    ast.parse(source, filename=relative)
        else:
            module = row[1]
            relative = "backend/" + ("sql/" if module.endswith(".sql") else "api/") + module
            edits = row[2] if kind == "mutant" else row[3]
            try:
                planted = U._plant(_source(cache, relative), edits, mid, kind)
            except SystemExit as error:
                raise AssertionError(("STALE", family, mid, kind, str(error))) from None
            if module.endswith(".py"):
                ast.parse(planted, filename=module)
            anchors += len(edits)
    return anchors


def _check_intended_sources():
    assert set(U.RUNNER_ASSERTIONS).isdisjoint(U.INTENDED_ASSERTIONS), "duplicate U assertion specification"
    assert set(U.RUNNER_ASSERTIONS) | set(U.INTENDED_ASSERTIONS) == set(U.MUTANTS), "every U row must name its exact adverse assertion"
    assert all(tags and all(isinstance(tag, str) and tag for tag in tags)
               for tags in U.INTENDED_ASSERTIONS.values()), "empty intended assertion tags"
    trees = {}
    for mid, assertions in U.RUNNER_ASSERTIONS.items():
        assert assertions, ("no intended assertion", mid)
        for expected in assertions:
            filename = expected["file"]
            if filename not in trees:
                trees[filename] = ast.parse((HERE / filename).read_text(encoding="utf-8-sig"))
            matches = []
            for owner in trees[filename].body:
                if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)) and owner.name == expected["function"]:
                    matches += [node for node in ast.walk(owner) if isinstance(node, ast.Assert)
                                and ast.unparse(node.test) == expected["expression"]
                                and (ast.unparse(node.msg) if node.msg else None) == expected["message_source"]]
            assert len(matches) == expected["occurrences"] and 0 <= expected["ordinal"] < len(matches), ("STALE intended assertion", mid, expected, len(matches))


def test_srv_registry_census(capsys):
    c_ids = [row["row"] for row in C.ROWS]
    u_ids = list(U.MUTANTS)
    assert len(c_ids) == len(set(c_ids)) and len(u_ids) == len(set(u_ids))
    assert BASE_C <= set(c_ids) and BASE_U <= set(u_ids), "a pre-existing registry row disappeared"
    assert len(BASE_C) == 38 and len(BASE_U) == 73
    assert len(CASES) == len(c_ids) + len(u_ids)
    assert len({(family, mid) for family, mid, row in CASES}) == len(CASES)
    _check_intended_sources()
    cache, counts = {}, {"C": 0, "U": 0}
    for family, mid, row in CASES:
        counts[family] += _preflight(family, mid, row, cache)
        with capsys.disabled():
            print("REGISTRY ADVERSE " + json.dumps({"family": family, "row": mid,
                                                    "intended": _adverse(family, mid, row)}, sort_keys=True), flush=True)
    # The parser must see the real rewritten message shape, including the
    # assertion explanation pytest appends after an explicit message.
    for argument, expected_tag in ((("REGISTRY tuple tag", 1), "REGISTRY tuple tag"),
                                   ("REGISTRY plain tag", "REGISTRY plain tag")):
        try:
            assert False, argument
        except AssertionError as error:
            assert C.rc.first_tag("AssertionError: " + str(error)) == expected_tag
    # Q14 adverse probes use the actual classifier and synthetic observation
    # records; they cannot pass by changing a child test or its assertion.
    mid = next(iter(U.RUNNER_ASSERTIONS))
    wanted = U.RUNNER_ASSERTIONS[mid][0]
    failure = {"node": "test_target", "phase": "call", "outcome": "failed",
               "exception": "builtins.AssertionError", "assertion": dict(wanted),
               "tag": wanted["tag"]}
    observed = {"collected": 1, "collection_errors": [], "reports": [failure]}
    assert U.registry_run_verdict(1, observed, mid=mid)[0] == "RED-NAMED"
    assert U.registry_run_verdict(1, observed, mid=mid,
                                  selector="test_target and not unmatched")[0] == "RED-NAMED"
    assert U.registry_run_verdict(1, observed, mid=mid,
                                  selector="(unmatched or test_target) and not absent")[0] == "RED-NAMED"
    assert U.registry_run_verdict(1, observed, mid=mid,
                                  selector="test_target and unmatched")[0] == "EMPTY"
    literal = {**observed, "reports": [{**failure, "node": "test_file.py::test_target[route,legacy(foo)]",
                                       "tag": "literal node"}]}
    assert U.registry_run_verdict(1, literal, tag="literal node", selector_is_node=True,
                                  selector="test_target[route,legacy(foo)]")[0] == "RED-NAMED"
    for exception in ("builtins.KeyError", "builtins.TypeError", "_pytest.outcomes.Failed"):
        bad = {**observed, "reports": [{**failure, "exception": exception}]}
        assert U.registry_run_verdict(1, bad, mid=mid)[0] == "RED-EXCEPTION"
    bad = {**observed, "reports": [{**failure, "assertion": {**wanted, "expression": "False"}}]}
    assert U.registry_run_verdict(1, bad, mid=mid)[0] == "RED-OTHER"
    assert U.registry_run_verdict(1, {**observed, "collection_errors": ["collection"]}, mid=mid)[0] == "ERROR"
    assert U.registry_run_verdict(1, {**observed, "reports": [{**failure, "phase": "setup"}]}, mid=mid)[0] == "ERROR"
    assert U.registry_run_verdict(0, {"collected": 0, "reports": []}, mid=mid)[0] == "EMPTY"
    with capsys.disabled():
        print("REGISTRY CENSUS " + json.dumps({"C": len(c_ids), "U": len(u_ids), "rows": len(CASES),
                                                "plants": len(CASES) * 2, "anchors": counts,
                                                "preexisting": 111, "bad": 0}, sort_keys=True), flush=True)


def _read_seat_hold():
    """Optional caller-supplied VM hold: read only, immediately before each run."""
    lock = os.environ.get("SRV_REGISTRY_SEAT_LOCK")
    holder = os.environ.get("SRV_REGISTRY_SEAT_HOLDER")
    if not lock and not holder:
        return None
    assert lock and holder, "both registry seat lock and holder must be supplied"
    try:
        with open(lock, encoding="utf-8") as stream:
            line = stream.readline().strip()
    except OSError as error:
        raise AssertionError(("LEFT", "seat lock unavailable", type(error).__name__)) from None
    assert line.split() and line.split()[0] == holder, ("LEFT", "seat hold belongs to another holder", line)
    return line


class _RegistryScratchRetained(RuntimeError):
    """Child termination was not proved; no containing scratch may be removed."""


def _stop_registry_child_impl(process):
    """Bounded cleanup of this invocation's own pytest process tree only."""
    if os.name == "nt":
        # An exited root PID no longer identifies its descendants to taskkill.
        # Retain the whole copy rather than infer that those descendants died.
        if process.poll() is not None:
            raise _RegistryScratchRetained("child root exited before descendant termination was proved")
        try:
            killed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise _RegistryScratchRetained("owned child tree termination failed: " + type(error).__name__) from None
        if killed.returncode != 0:
            raise _RegistryScratchRetained("taskkill did not prove owned child tree termination")
    else:
        # The child has its own session, so its group remains addressable even
        # if the original parent exited while a descendant kept its pipes open.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as error:
            raise _RegistryScratchRetained("owned child group termination failed: " + type(error).__name__) from None
    try:
        stdout, stderr = process.communicate(timeout=15)
        process.wait(timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise _RegistryScratchRetained("owned child pipes did not close after termination: " + type(error).__name__) from None
    if os.name != "nt":
        deadline = time.monotonic() + 5
        while True:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            except OSError as error:
                raise _RegistryScratchRetained("owned child group absence was not proved: " + type(error).__name__) from None
            if time.monotonic() >= deadline:
                raise _RegistryScratchRetained("owned child group remains after termination")
            time.sleep(0.05)
    return stdout, stderr


def _stop_registry_child(process):
    try:
        return _stop_registry_child_impl(process)
    except _RegistryScratchRetained as error:
        error.owned_child_pid = process.pid
        raise
    except BaseException as error:
        # Interrupted cleanup is itself an unknown liveness result.
        retained = _RegistryScratchRetained("owned child cleanup was interrupted: " + type(error).__name__)
        retained.owned_child_pid = process.pid
        raise retained from None


def _run_registry_child(command, *, cwd, env):
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        start_new_session=os.name != "nt")
    try:
        stdout, stderr = process.communicate(timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        stdout, stderr = _stop_registry_child(process)
        raise subprocess.TimeoutExpired(command, TIMEOUT_S, output=stdout, stderr=stderr) from None
    except BaseException:
        # An interrupted communicate must receive the same bounded cleanup as
        # a timeout before either surrounding scratch directory can disappear.
        _stop_registry_child(process)
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _run_variant(family, mid, row, kind, parent, emit):
    variant = Path(tempfile.mkdtemp(prefix=kind[0] + "_", dir=parent))
    cleanup_allowed = True
    try:
        copied = variant / "backend"
        shutil.copytree(BACKEND, copied, ignore=IGNORE)
        if kind != "control":
            if family == "C":
                C.rc.apply_edits(str(variant), row[kind])
            else:
                module = row[1]
                target = copied / ("sql" if module.endswith(".sql") else "api") / module
                with target.open(encoding="utf-8", newline="") as stream:
                    original = stream.read()
                edits = row[2] if kind == "mutant" else row[3]
                planted = U._plant(original, edits, mid, kind)
                with target.open("w", encoding="utf-8", newline="") as stream:
                    stream.write(planted)
        env = dict(os.environ)
        for name in ("PYTHONPATH", "MATCH_HOLD_SRC", "SRV_REGISTRY_REPORT", *U.SQL_ENV.values()):
            env.pop(name, None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        record = variant / "observations.json"
        env["SRV_REGISTRY_REPORT"] = str(record)
        env["MATCH_HOLD_SCRATCH"] = str(variant / "nested")
        command = [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider",
                   "-p", "test_srv_registry_seat", "-q", "-rf",
                   "--rootdir", str(copied), "--basetemp", str(variant / "temp"),
                   "-o", "junit_family=xunit1", "--junitxml", str(variant / "junit.xml")]
        if family == "C":
            command.append(str(copied / "tests" / row["node"]))
        else:
            command += [str(copied / "tests" / row[4]), "-k", "census or (" + row[5] + ")"]
        try:
            seat_line = _read_seat_hold()
            if seat_line is not None:
                emit({"family": family, "row": mid, "kind": kind, "seat_lock_first_line": seat_line})
            result = _run_registry_child(command, cwd=copied / "tests", env=env)
            observations = U.read_registry_run(record)
            code = result.returncode
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired as error:
            def decoded(value):
                return value.decode("utf-8", "replace") if isinstance(value, bytes) else value or ""
            output = decoded(error.stdout) + decoded(error.stderr)
            emit({"family": family, "row": mid, "kind": kind,
                  "verdict": "TIMEOUT", "seconds": TIMEOUT_S}, output)
            return "TIMEOUT", {"seconds": TIMEOUT_S}, output, None
        verdict, detail = U.registry_run_verdict(
            code, observations, mid=mid if family == "U" else None,
            tag=row["tag"] if family == "C" else None, selector=_selector(family, row),
            selector_is_node=family == "C")
        if family == "C" and kind == "mutant" and verdict == "RED-NAMED":
            first = next(r for r in observations["reports"]
                         if r["phase"] == "call" and r["outcome"] == "failed")
            rdm_verdict, rdm_detail = C.rc.verdict_mutant(("failed", first["message"]), row["tag"])
            if rdm_verdict != "RED-NAMED":
                verdict, detail = rdm_verdict, rdm_detail
        if verdict == "RED-NAMED" and isinstance(detail, dict):
            detail = {key: detail.get(key) for key in ("node", "exception", "tag", "assertion")}
        summary = {"collected": observations.get("collected", 0),
                   "collection_errors": len(observations.get("collection_errors", [])),
                   "setup_errors": sum(r["phase"] != "call" and r["outcome"] == "failed"
                                       for r in observations.get("reports", [])),
                   "skipped": sum(r["outcome"] == "skipped" for r in observations.get("reports", []))}
        emit({"family": family, "row": mid, "kind": kind,
              "verdict": verdict, "detail": detail, "counts": summary}, output)
        return verdict, detail, output, summary
    except BaseException as error:
        cleanup_allowed = not isinstance(error, _RegistryScratchRetained)
        emit({"family": family, "row": mid, "kind": kind,
              "verdict": "ERROR", "exception": type(error).__name__, "detail": str(error),
              "scratch_retained": not cleanup_allowed,
              "owned_child_pid": getattr(error, "owned_child_pid", None)})
        raise
    finally:
        if cleanup_allowed:
            shutil.rmtree(variant)
            assert not variant.exists(), "variant scratch directory remains"
        emit({"family": family, "row": mid, "kind": kind,
              "scratch_removed": cleanup_allowed, "scratch_retained": not cleanup_allowed,
              "directory": variant.name})


@pytest.mark.parametrize("family,mid,row", CASES, ids=[family + "-" + mid for family, mid, row in CASES])
def test_srv_registry_row(family, mid, row, tmp_path, capsys):
    _require_live_case(family, row)
    _preflight(family, mid, row, {})
    scratch = Path(os.environ.get("MATCH_HOLD_SCRATCH") or tmp_path)
    assert scratch.is_absolute(), "MATCH_HOLD_SCRATCH must be absolute"
    scratch.mkdir(parents=True, exist_ok=True)
    backend_root = BACKEND.resolve()
    assert not scratch.resolve().is_relative_to(backend_root.parent), "scratch must be outside the worktree"
    parent = Path(tempfile.mkdtemp(prefix="seat_", dir=scratch))
    results = {}
    cleanup_allowed = True

    def emit(record, output=None):
        nonlocal cleanup_allowed
        if record.get("scratch_retained") is True:
            # Set the containing-tree guard before I/O can itself fail.
            cleanup_allowed = False
        # Every child transcript is printed before its tree is removed.
        with capsys.disabled():
            print("\nREGISTRY RUN " + json.dumps(record, sort_keys=True), flush=True)
            if output is not None:
                print(output, flush=True)

    try:
        for kind in ("control", "mutant", "twin"):
            verdict, detail, output, summary = _run_variant(family, mid, row, kind, parent, emit)
            results[kind] = verdict
            if kind == "control":
                assert verdict == "GREEN", ("control must be green before planting", family, mid, verdict)
        assert results == {"control": "GREEN", "mutant": "RED-NAMED", "twin": "GREEN"}, results
    except _RegistryScratchRetained:
        cleanup_allowed = False
        raise
    finally:
        if cleanup_allowed:
            shutil.rmtree(parent)
            assert not parent.exists(), "case scratch directory remains"
        else:
            emit({"family": family, "row": mid, "kind": "case",
                  "scratch_retained": True, "directory": parent.name})
