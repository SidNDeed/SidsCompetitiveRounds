"""Seat adapter for both Stage 2 registries (whole backend copies, fail closed).

Select one row with test_srv_registry_row[C-row] or [U-row].  This module
also acts as the child pytest observation plugin; it never changes a test's
assertion expression or message.  Each variant uses one fresh complete backend
copy, removed after its result is recorded.  A child error never counts as a kill.
"""
import ast
import asyncio
import faulthandler
import itertools
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
_CHILD_RUN = {"collected": 0, "collection_errors": [], "reports": [], "events": []}
_STACK_STREAM = None




def _persist_observations(event=None):
    target = os.environ.get("SRV_REGISTRY_REPORT")
    if not target:
        return
    if event is not None:
        event = {"monotonic": time.monotonic(), **event}
        _CHILD_RUN["events"].append(event)
        with open(target + ".events.jsonl", "a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    temporary = Path(target + ".new")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(_CHILD_RUN, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def pytest_sessionstart(session):
    global _STACK_STREAM
    target = os.environ.get("SRV_REGISTRY_REPORT")
    if target:
        _CHILD_RUN["active"] = {"node": None, "phase": "collection"}
        _STACK_STREAM = open(target + ".stack.txt", "w", encoding="utf-8")
        deadline = float(os.environ.get("SRV_REGISTRY_DEADLINE", time.monotonic() + TIMEOUT_S))
        faulthandler.dump_traceback_later(max(1, deadline - time.monotonic() - 10), file=_STACK_STREAM)
        _persist_observations({"event": "session_start"})


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_setup(item):
    _CHILD_RUN["active"] = {"node": item.nodeid, "phase": "setup"}
    _persist_observations({"event": "phase_start", **_CHILD_RUN["active"]})
    yield


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    _CHILD_RUN["active"] = {"node": item.nodeid, "phase": "call"}
    _persist_observations({"event": "phase_start", **_CHILD_RUN["active"]})
    yield


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item):
    _CHILD_RUN["active"] = {"node": item.nodeid, "phase": "teardown"}
    _persist_observations({"event": "phase_start", **_CHILD_RUN["active"]})
    yield


def pytest_collectreport(report):
    if os.environ.get("SRV_REGISTRY_REPORT") and report.failed:
        _CHILD_RUN["collection_errors"].append(report.nodeid)
        _persist_observations({"event": "collection_error", "node": report.nodeid})


def pytest_collection_finish(session):
    if os.environ.get("SRV_REGISTRY_REPORT"):
        _CHILD_RUN["collected"] = len(session.items)
        _persist_observations({"event": "collection_finish", "collected": len(session.items)})


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
    row["seconds"] = report.duration
    _CHILD_RUN["reports"].append(row)
    _persist_observations({"event": "phase_end", "node": item.nodeid, "phase": call.when,
                           "outcome": report.outcome, "seconds": report.duration})


def pytest_sessionfinish(session, exitstatus):
    global _STACK_STREAM
    if os.environ.get("SRV_REGISTRY_REPORT"):
        _CHILD_RUN["exitstatus"] = int(exitstatus)
        _CHILD_RUN.pop("active", None)
        _persist_observations({"event": "session_finish", "exitstatus": int(exitstatus)})
        faulthandler.cancel_dump_traceback_later()
        if _STACK_STREAM is not None:
            _STACK_STREAM.close()
            _STACK_STREAM = None


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
    _check_bounded_constituents()
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




def _phase_evidence(record):
    record = Path(record)
    observed = U.read_registry_run(record)
    pool_events = []
    try:
        for line in Path(str(record) + ".pool.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                pool_events.append(json.loads(line))
            except ValueError:
                pool_events.append({"event": "incomplete_pool_record"})
    except OSError:
        pass
    try:
        stack = Path(str(record) + ".stack.txt").read_text(encoding="utf-8")
    except OSError:
        stack = ""
    return {"active": observed.get("active"), "events": observed.get("events", []),
            "reports": observed.get("reports", []), "pool_events": pool_events, "stack": stack}


def _database_spec(test_file, env):
    pooled = test_file != "test_ffa_quarantine_triage.py"
    variable = "CF_TEST_PG_DSN" if pooled else "RJ_TRIAGE_TEST_PG_DSN"
    return env[variable].replace("postgresql+asyncpg://", "postgresql://"), pooled


def _registry_database_begin(test_file, env, reason):
    import cf_pool
    dsn, pooled = _database_spec(test_file, env)
    lifecycle = asyncio.run(asyncio.wait_for(
        cf_pool.registry_database(dsn, action="begin", pooled=pooled, reason=reason), 120))
    env["CF_POOL_RUN_ID"] = lifecycle["owner"]
    env["CF_POOL_ACTIVE_TOKEN"] = lifecycle["active_token"]
    return lifecycle


def _registry_database_finish(test_file, env, lifecycle):
    import cf_pool
    dsn, pooled = _database_spec(test_file, env)
    return asyncio.run(asyncio.wait_for(cf_pool.registry_database(
        dsn, action="finish", pooled=pooled, active_token=lifecycle["active_token"]), 120))


def _database_waits(env):
    async def observe():
        import asyncpg
        records = []
        for variable in ("CF_TEST_PG_DSN", "RJ_TRIAGE_TEST_PG_DSN"):
            if not env.get(variable):
                continue
            conn = await asyncpg.connect(env[variable].replace("postgresql+asyncpg://", "postgresql://"),
                                         timeout=1, command_timeout=1)
            try:
                rows = await conn.fetch(
                    "SELECT state, wait_event_type, wait_event, cardinality(pg_blocking_pids(pid)) "
                    "AS blockers FROM pg_catalog.pg_stat_activity WHERE datname=current_database() "
                    "AND pid<>pg_backend_pid() AND backend_type='client backend'")
                records += [{"database_kind": variable.split("_TEST", 1)[0], **dict(row)} for row in rows]
            finally:
                await conn.close()
        return records
    try:
        return asyncio.run(asyncio.wait_for(observe(), 3))
    except Exception as error:
        return [{"observation_error": type(error).__name__}]


def _run_registry_child(command, *, cwd, env, force_kill_when=None):
    env = dict(env)
    deadline = time.monotonic() + TIMEOUT_S
    env["SRV_REGISTRY_DEADLINE"] = str(deadline)
    if env.get("SRV_REGISTRY_REPORT"):
        with open(env["SRV_REGISTRY_REPORT"], "w", encoding="utf-8") as stream:
            json.dump({"active": {"node": None, "phase": "process_start"}, "reports": [],
                       "events": [{"phase": "process_start", "monotonic": time.monotonic()}]}, stream)
            stream.flush()
            os.fsync(stream.fileno())
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        start_new_session=os.name != "nt")
    waits = []
    sampled = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            forced = force_kill_when is not None and Path(force_kill_when).exists()
            if remaining <= 0 or forced:
                stdout, stderr = _stop_registry_child(process)
                error = subprocess.TimeoutExpired(command, TIMEOUT_S, output=stdout, stderr=stderr)
                error.database_waits = waits
                error.forced = forced
                raise error
            if not sampled and 3 < remaining <= 5:
                # Observe before the deadline; the child is killed at its unchanged bound.
                waits = _database_waits(env)
                sampled = True
                continue
            try:
                stdout, stderr = process.communicate(timeout=min(0.2 if force_kill_when else 5, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    except subprocess.TimeoutExpired:
        raise
    except BaseException:
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
        env["MATCH_HOLD_SCRATCH"] = str(variant / "nested")
        nodes = U.BOUNDED_NODES.get(mid, (None,)) if family == "U" else (None,)
        constituent_results, outputs, phase_records = [], [], []
        started = time.monotonic()
        for index, node in enumerate(nodes):
            record = variant / ("observations-%02d.json" % index)
            env["SRV_REGISTRY_REPORT"] = str(record)
            env["SRV_REGISTRY_POOL_EVENTS"] = str(record) + ".pool.jsonl"
            command = [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider",
                       "-p", "test_srv_registry_seat", "-q", "-rf", "--rootdir", str(copied),
                       "--basetemp", str(variant / ("temp-%02d" % index)),
                       "-o", "junit_family=xunit1", "--junitxml", str(variant / ("junit-%02d.xml" % index))]
            if family == "C":
                command.append(str(copied / "tests" / row["node"]))
            elif node:
                command.append(str(copied / "tests" / row[4]) + "::" + node)
            else:
                command += [str(copied / "tests" / row[4]), "-k", "census or (" + row[5] + ")"]
            seat_line = _read_seat_hold()
            if seat_line is not None:
                emit({"family": family, "row": mid, "kind": kind, "part": index,
                      "seat_lock_first_line": seat_line})
            lifecycle = _registry_database_begin(_test_file(family, row), env, "%s/%s/%s" % (mid, kind, index))
            emit({"family": family, "row": mid, "kind": kind, "part": index,
                  "database_verified_before": lifecycle["verified"], "recovered": lifecycle["recovered"]})
            part_started = time.monotonic()
            try:
                result = _run_registry_child(command, cwd=copied / "tests", env=env)
            except subprocess.TimeoutExpired as error:
                def decoded(value):
                    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value or ""
                output = decoded(error.stdout) + decoded(error.stderr)
                phases = _phase_evidence(record)
                emit({"family": family, "row": mid, "kind": kind, "part": index,
                      "verdict": "TIMEOUT", "seconds": TIMEOUT_S, "phases": phases,
                      "database_waits": getattr(error, "database_waits", []), "database_unverified": True}, output)
                return "TIMEOUT", {"seconds": TIMEOUT_S, "phases": phases}, output, None
            observations = U.read_registry_run(record)
            output = result.stdout + result.stderr
            phases = _phase_evidence(record)
            try:
                checked = _registry_database_finish(_test_file(family, row), env, lifecycle)
            except BaseException as error:
                emit({"family": family, "row": mid, "kind": kind, "part": index,
                      "phase": "database_finish", "verdict": "ERROR", "phases": phases,
                      "database_unverified": True, "exception": type(error).__name__}, output)
                raise
            outputs.append(output)
            phase_records.append(phases)
            constituent_results.append((result.returncode, observations))
            emit({"family": family, "row": mid, "kind": kind, "part": index, "node": node,
                  "seconds": time.monotonic() - part_started, "returncode": result.returncode,
                  "phases": phases, "database_verified_after": checked["verified"]}, output)
        code, observations = U.combine_registry_runs(constituent_results)
        output = "\n".join(outputs)
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
        emit({"family": family, "row": mid, "kind": kind, "verdict": verdict,
              "detail": detail, "counts": summary, "seconds": time.monotonic() - started,
              "constituents": len(nodes)})
        return verdict, detail, output, summary
    except BaseException as error:
        cleanup_allowed = not isinstance(error, _RegistryScratchRetained)
        emit({"family": family, "row": mid, "kind": kind, "verdict": "ERROR",
              "exception": type(error).__name__, "detail": str(error),
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



def test_srv_registry_forced_kill_requires_verified_pool_recovery(tmp_path, capsys):
    """A killed pending build cannot silently become the next child's database."""
    import cf_pool
    _require_live_case("U", U.MUTANTS["MERGED.FIX1.H4.BIND"])
    scratch = Path(os.environ.get("MATCH_HOLD_SCRATCH") or tmp_path)
    assert scratch.is_absolute() and not scratch.resolve().is_relative_to(BACKEND.parent)
    scratch.mkdir(parents=True, exist_ok=True)
    parent = Path(tempfile.mkdtemp(prefix="kill_", dir=scratch))
    copied = parent / "backend"
    shutil.copytree(BACKEND, copied, ignore=IGNORE)
    cleanup_allowed = True
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SRV_REGISTRY_POOL_EVENTS"] = str(parent / "forced.pool.jsonl")
    ready = parent / "ready"
    env["SRV_REGISTRY_FORCE_READY"] = str(ready)
    script = """
import asyncio, os
from pathlib import Path
import cf_pool
async def partial(case, **kwargs):
    await case.conn.execute('CREATE TABLE ffa_lobbies (id integer)')
    Path(os.environ['SRV_REGISTRY_FORCE_READY']).write_text(case.schema, encoding='ascii')
    await asyncio.Event().wait()
cf_pool.cf_pg.build = partial
cf_pool.build_key = lambda faithful: 'forced_kill_control'
async def run():
    async with cf_pool.checkout():
        raise AssertionError('forced build unexpectedly completed')
asyncio.run(run())
"""
    try:
        line = _read_seat_hold()
        lifecycle = _registry_database_begin("test_match_hold_deletion_pg.py", env, "forced-kill-control")
        try:
            _run_registry_child([sys.executable, "-B", "-c", script], cwd=copied / "tests", env=env, force_kill_when=ready)
        except subprocess.TimeoutExpired as error:
            assert error.forced, "forced kill did not reach its owned pending-build barrier"
            waits = getattr(error, "database_waits", [])
        else:
            raise AssertionError("forced child was not killed")
        schema = ready.read_text(encoding="ascii")
        dsn, _ = _database_spec("test_match_hold_deletion_pg.py", env)
        refused = False
        try:
            asyncio.run(cf_pool.require_registry_verified(dsn))
        except cf_pool.harness.CensusRefusal as error:
            assert str(error) == "registry database is unverified"
            refused = True
        assert refused, "FIX3 F4 quarantined database was reusable"
        line2 = _read_seat_hold()
        recovered = _registry_database_begin("test_match_hold_deletion_pg.py", env, "post-kill-clean-control")
        assert recovered["recovered"] == [schema], "FIX3 F4 cleanup was not the exact owned schema"
        clean = """
import asyncio
import cf_pool
async def run():
    async with cf_pool.checkout() as (case, sm):
        assert await case.conn.fetchval("SELECT to_regclass('ffa_lobbies')") is not None
asyncio.run(run())
print('FIX3 F4 CLEAN CONTROL GREEN', flush=True)
"""
        result = _run_registry_child([sys.executable, "-B", "-c", clean], cwd=copied / "tests", env=env)
        assert result.returncode == 0, ("FIX3 F4 clean control failed", result.stdout, result.stderr)
        assert "FIX3 F4 CLEAN CONTROL GREEN" in result.stdout
        _registry_database_finish("test_match_hold_deletion_pg.py", env, recovered)
        asyncio.run(cf_pool.require_registry_verified(dsn))
        with capsys.disabled():
            print("REGISTRY ISOLATION " + json.dumps({"forced_kill": True, "refused_before_verification": refused,
                  "recovered": recovered["recovered"], "clean_control": "GREEN", "database_waits": waits,
                  "seat_lock_first_lines": [line, line2]}, sort_keys=True), flush=True)
            print((parent / "forced.pool.jsonl").read_text(encoding="utf-8"), flush=True)
    except _RegistryScratchRetained:
        cleanup_allowed = False
        raise
    finally:
        if cleanup_allowed:
            with capsys.disabled():
                phases_path = parent / "forced.pool.jsonl"
                if phases_path.exists():
                    print("REGISTRY ISOLATION PHASES " + phases_path.read_text(encoding="utf-8"), flush=True)
            shutil.rmtree(parent)
            assert not parent.exists()



def _check_bounded_constituents():
    tree = ast.parse((HERE / "test_match_hold_deletion_pg.py").read_text(encoding="utf-8-sig"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    specifications = {
        "test_fix1_h4_each_hold_writer_guards_before_downstream_lock":
            ("MERGED.FIX1.H4.CLAIM_AUDIT", "MERGED.FIX1.H4.BIND", "MERGED.FIX1.H4.END"),
        "test_fix1_h4_beat_deletion_orders_and_survivors": ("MERGED.FIX1.H4.SEEN",),
    }
    assert set(U.BOUNDED_NODES) == {mid for rows in specifications.values() for mid in rows}
    for name, rows in specifications.items():
        axes = [ast.literal_eval(d.args[1]) for d in reversed(functions[name].decorator_list)
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr == "parametrize"]
        expected = tuple(name + "[" + "-".join(map(str, values)) + "]"
                         for values in itertools.product(*axes))
        for mid in rows:
            assert U.BOUNDED_NODES[mid] == expected, ("FIX3 F4 missing constituent", mid)
            assert len(set(expected)) == len(expected)


@pytest.mark.parametrize("route", ["V1", "V2", "D1"])
def test_srv_k21_old_slack_triplet(route, tmp_path, capsys):
    """Expose the frozen old-slack plants through the admitted pytest seat interface."""
    name = "_srv_k21_frozen_registry"
    registry = sys.modules.get(name)
    if registry is None:
        specification = importlib.util.spec_from_file_location(name, HERE / "rj_triage_controls.py")
        registry = importlib.util.module_from_spec(specification)
        # dataclass annotation resolution requires the defining module here.
        sys.modules[name] = registry
        try:
            specification.loader.exec_module(registry)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    names = ("K21-old-slack-restored", "K21-twin-alter-run-subtracted")
    selected = [plant for plant in registry.P if plant.name in names]
    assert len(selected) == 2 and {plant.name for plant in selected} == set(names), "K21 plants missing or duplicate"
    plants = {plant.name: plant for plant in selected}
    node = "test_ffa_quarantine_triage.py::test_pg_k21_a_capture_committing_past_the_bound_is_a_fail[" + route + "]"
    row = {"row": "K21." + route, "node": node, "tag": "FIX2 M5 strict capture bound"}
    for kind, plant_name in zip(("mutant", "twin"), names):
        plant = plants[plant_name]
        assert plant.kind == kind and node in plant.checks, ("K21 frozen plant scope", kind, route)
        assert len(plant.edits) == 1, "K21 expected one frozen verdict edit"
        relative, old, new = plant.edits[0]
        assert relative == "backend/tests/test_ffa_quarantine_triage.py", "K21 unexpected target"
        row[kind] = [(relative, old, new, 1)]
    # The 125 registry identities remain unchanged. This additional seat case
    # uses their same isolated children, strict classification and cleanup.
    test_srv_registry_row("C", row["row"], row, tmp_path, capsys)
