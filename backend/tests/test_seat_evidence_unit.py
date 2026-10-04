"""Seat evidence (contract V2), the parts that need no database: the record
bounds, the byte budgeter, the signing canonical, the compat outcome, the
statement scan that keeps match results, ratings and gold out of the lane,
the model columns, the worker's role wiring and its log markers, the health
words, the migration's switches and the bot's review line.

Judging is not tested here: it lives in a rules revision outside the
repository. The public machinery that evaluates a revision is tested in
test_review_rules.py over SYNTHETIC revisions."""

import ast
import hashlib
import inspect
import json
import os
import re
import sys
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import seat_evidence as se  # noqa: E402
import seat_evidence_fixtures as fx  # noqa: E402

API = os.path.normpath(os.path.join(HERE, "..", "api"))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
FIXTURE = os.path.join(HERE, "fixtures", "seat_evidence_budget.json")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


# -- the budgeter, worst case, and the shared fixture --------------------------

def test_worst_case_record_budgets_to_valid_json_within_the_limit():
    rec = fx.worst_case_record()
    text = se.budget_record(rec)
    assert len(text.encode("ascii")) <= se.RECORD_MAX_BYTES
    parsed = json.loads(text)
    se.check_record(parsed)
    for k in se.LIST_ORDER:
        assert len(parsed[k]) + parsed["omit"][k] == 400, k
        assert len(parsed[k]) <= se.LIST_CAP
    assert sum(parsed["omit"].values()) > 5 * (400 - se.LIST_CAP)
    assert se.budget_record(rec) == text          # deterministic


def test_the_server_refuses_one_byte_over_and_a_list_over_the_cap():
    rec = fx.base_record()
    body = fx.envelope(rec, text=" " * (se.RECORD_MAX_BYTES + 1))
    with pytest.raises(se.EvidenceRefused) as e:
        se.parse_envelope(body)
    assert e.value.status == 413
    rec = fx.base_record(blk_sent=[[1, 0, 0, 0]] * (se.LIST_CAP + 1))
    body = fx.envelope(rec, text=json.dumps(rec, separators=(",", ":")))
    env = se.parse_envelope(body)
    with pytest.raises(se.EvidenceRefused) as e:
        se.parse_record(env)
    assert (e.value.status, e.value.field) == (422, "blk_sent")


def test_the_attach_key_stays_within_64_bytes():
    rec = fx.base_record()
    body = fx.envelope(rec, stable="k" * 60, rounds=12)
    assert se.parse_envelope(body)["attach"].endswith("_r12")
    body["attach_key"] = "k" * 60 + "_r123"
    with pytest.raises(se.EvidenceRefused) as e:
        se.parse_envelope(body)
    assert e.value.field == "attach_key"


def test_the_shared_budget_fixture_pins_the_bytes_the_client_must_produce():
    with open(FIXTURE, encoding="utf-8") as f:
        fixture = json.load(f)
    text = se.budget_record(fixture["input"])
    assert len(text) <= se.RECORD_MAX_BYTES
    assert hashlib.sha256(text.encode("ascii")).hexdigest() == fixture["sha256"]
    assert len(text) == fixture["bytes"]
    # the fixture is contract-valid: every entry passes the cross-field
    # invariants, and the budgeted record passes the whole record check
    se.check_events(fixture["input"])
    se.check_record(json.loads(text))


# -- M-8: the enumerated and cross-field event invariants ------------------------

EVENT_CASES = [
    ("blk_sent", [1, 0, 0, -1], "blk_sent.own_open"),
    ("blk_sent", [1, 0, 0, 200], "blk_sent.own_open"),
    ("hit_recv", [1, 5, 7, 0, 5, 0, 1, -1], "hit_recv.path"),
    ("hit_recv", [0, 5, 7, 0, 5, 0, 1, -1], "hit_recv.pid"),
    ("hit_sent", [0, 5, 7, 0, -1, 0, 0, -1, 0], "hit_sent.pid"),
    ("hit_sent", [0, 5, 0, 0, -1, 0, 3, -1, 0], "hit_sent.last"),
    ("hit_sent", [0, 5, 0, 0, -1, 0, 0, -1, 4], "hit_sent.last"),
    # round 2 M8: since_ms is -1 if and only if last_* is the no-block tuple
    ("hit_sent", [0, 5, 0, 0, -1, 0, 9, 2, 3], "hit_sent.since_unset_with_block"),
    ("hit_sent", [0, 5, 0, 0, 10, 0, 0, -1, 0], "hit_sent.since_set_without_block"),
    ("hit_sent", [0, 5, 0, 0, 0, 0, 0, -1, 0], "hit_sent.since_set_without_block"),
]
EVENT_CONTROLS = [
    ("blk_sent", [1, 0, 0, 0]), ("blk_sent", [1, 0, 0, -200]),
    ("hit_recv", [0, 5, 0, 0, 5, 0, 1, -1]),
    ("hit_sent", [1, 5, 7, 0, -1, 0, 0, -1, 0]),
    # the two valid since/last pairs: no block (-1 with [0,-1,0]) and a named block
    ("hit_sent", [0, 5, 0, 0, -1, 0, 0, -1, 0]),
    ("hit_sent", [0, 5, 0, 0, 10, 0, 9, 2, 3]),
    ("hit_sent", [0, 5, 0, 0, 0, 0, 9, 2, 3]),
]


@pytest.mark.parametrize("field,entry,name", EVENT_CASES)
def test_m8_an_event_breaking_an_invariant_is_refused_by_name(field, entry, name):
    rec = fx.base_record(**{field: [entry]})
    with pytest.raises(se.EvidenceRefused) as e:
        se.check_record(rec)
    assert (e.value.status, e.value.field) == (422, name)


@pytest.mark.parametrize("field,entry", EVENT_CONTROLS)
def test_m8_control_the_legal_forms_pass(field, entry):
    se.check_record(fx.base_record(**{field: [entry]}))


# -- round 2 new L: the optional `end` key (amendment A1) -------------------------

END_VALUES = ("left", "other_left", "lost", "closing")


def _with_end(value, after="rounds"):
    rec = fx.base_record()
    out = {}
    for k, v in rec.items():
        out[k] = v
        if k == after:
            out["end"] = value
    return out


@pytest.mark.parametrize("value", END_VALUES)
def test_end_each_closed_value_in_its_exact_place_is_accepted(value):
    rec = _with_end(value)
    assert list(rec).index("end") == list(rec).index("rounds") + 1
    se.check_record(rec)


def test_end_control_absent_is_accepted_and_byte_identical_to_v2():
    rec = fx.base_record()
    assert "end" not in rec
    se.check_record(rec)


@pytest.mark.parametrize("value", ["", "won", "LEFT", 1, None, ["left"]])
def test_end_a_value_outside_the_closed_set_is_refused_by_name(value):
    with pytest.raises(se.EvidenceRefused) as e:
        se.check_record(_with_end(value))
    assert (e.value.status, e.value.field) == (422, "end")


@pytest.mark.parametrize("after", ["schema", "build", "omit"])
def test_end_out_of_its_place_is_refused(after):
    with pytest.raises(se.EvidenceRefused) as e:
        se.check_record(_with_end("lost", after=after))
    assert (e.value.status, e.value.field) == (422, "key_order")


def test_end_survives_the_budgeter_and_the_envelope_parse_in_place():
    rec = _with_end("closing")
    body = fx.envelope(rec)
    text = body["record"]
    assert '"rounds":[5,3],"end":"closing","build"' in text           # the budgeter keeps it in place
    env = se.parse_envelope(body)
    parsed = se.parse_record(env)
    assert parsed["end"] == "closing" and list(parsed) == list(rec)
    assert env["record_text"] == text                                # stored bytes = sent bytes
    plain = fx.envelope(fx.base_record())["record"]
    assert '"end"' not in plain and plain == text.replace(',"end":"closing"', "")


def test_the_relayed_build_holds_the_complete_46_character_tuple():
    full = "9" * 16 + "|" + "V" * 16 + "|" + "c" * 12
    assert len(full) == 46
    se.check_record(fx.base_record(other_build=full))
    with pytest.raises(se.EvidenceRefused) as e:
        se.check_record(fx.base_record(other_build=full + "x"))
    assert e.value.field == "other_build"


def test_floats_key_order_and_unknown_keys_are_refused():
    env = se.parse_envelope(fx.envelope(fx.base_record(), text='{"schema": 2.0}'))
    with pytest.raises(se.EvidenceRefused) as e:
        se.parse_record(env)
    assert e.value.field == "record_number"
    rec = fx.base_record()
    with pytest.raises(se.EvidenceRefused):
        se.check_record(dict(reversed(list(rec.items()))))
    with pytest.raises(se.EvidenceRefused):
        se.check_record(dict(rec, extra=1))


def test_a_hash_state_other_than_ok_never_carries_a_digest():
    with pytest.raises(se.EvidenceRefused):
        se.check_record(fx.base_record(dll=["a" * 64, "read_failed"]))
    with pytest.raises(se.EvidenceRefused):
        se.check_record(fx.base_record(dll=["", "ok"]))
    se.check_record(fx.base_record(dll=["", "no_location"]))


def test_the_signing_canonical_is_new_and_separate_from_the_match_hmac():
    env = se.parse_envelope(fx.envelope(fx.base_record()))
    c = se.record_canonical(env)
    assert c.startswith("seat-evidence:v2:%s:%s:" % (fx.SEAT_A, fx.SEAT_B))
    assert len(c.split(":")) == 7 and all(len(p) == 64 for p in c.split(":")[4:])
    assert se.verify_sig(fx.KEY, env) and not se.verify_sig("other", env)
    assert not se.verify_sig("", env)


def test_the_compat_outcome_has_no_pass_and_a_thrown_check_is_not_run():
    ok = {"seat_steam_id": fx.SEAT_A, "outcome": "not_run", "plugins": [], "sig": "0" * 64}
    assert se.check_compat(ok)["outcome"] == "not_run"
    for bad, field in ((dict(ok, outcome="pass"), "outcome"),
                       (dict(ok, plugins=["a.b"] * 17), "plugins"),
                       (dict(ok, plugins=["has space"]), "plugins")):
        with pytest.raises(se.EvidenceRefused) as e:
            se.check_compat(bad)
        assert (e.value.status, e.value.field) == (422, field)
    c = se.check_compat(dict(ok, outcome="finding", plugins=["x.y", "z"]))
    assert se.compat_canonical(c["seat"], c["outcome"], c["plugins"]) == (
        "compat-outcome:v1:%s:finding:%s" % (fx.SEAT_A, hashlib.sha256(b"x.y,z").hexdigest()))


def test_details_are_bounded_and_say_so():
    big = {"items": [{"x": "y" * 100}] * 100}
    out = se.bounded_details(big)
    assert out["truncated"] is True and len(se._dumps(out)) <= se.DETAILS_MAX_BYTES
    small = {"items": [{"x": 1}]}
    assert se.bounded_details(small) is small


# -- A9: every statement of the lane and of the review modules ------------------

PROTECTED = ("matches", "ranked_series", "players", "rating_history", "glicko_ratings",
             "glicko_ratings_2v2", "player_gold", "gold_ledger", "player_items",
             "player_achievements", "team_series", "ffa_lobbies", "ffa_matches")
LANE_WRITES = {"seat_evidence", "seat_evidence_games", "seat_evidence_findings",
               "client_compat_events", "mod_release_digests", "flagged_matches",
               "review_sitting_dirty", "review_cursor", "review_seen"}
_WRITE = re.compile(r"\b(?:INSERT\s+INTO|(?<!DO\s)(?<!FOR\s)UPDATE|DELETE\s+FROM"
                    r"|TRUNCATE(?:\s+TABLE)?|ALTER\s+TABLE)"
                    r"\s+(?:ONLY\s+)?([A-Za-z_][A-Za-z0-9_]*)")
REVIEW_MODULES = ("seat_evidence.py", "review_measures.py", "review_rules.py")


def written_tables(source: str) -> set:
    tree = ast.parse(source)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for m in _WRITE.finditer(node.value):
                out.add(m.group(1).lower())
        if isinstance(node, ast.JoinedStr):
            lit = "".join(v.value for v in node.values
                          if isinstance(v, ast.Constant) and isinstance(v.value, str))
            for m in _WRITE.finditer(lit):
                out.add(m.group(1).lower())
    return out


def _main():
    import main
    return main


def _lane_sources():
    main = _main()
    mods = "\n\n".join(_read(API, m) for m in REVIEW_MODULES)
    routes = "\n\n".join(textwrap.dedent(inspect.getsource(fn)) for fn in (
        main.submit_seat_evidence, main.submit_compat_outcome, main.admin_seat_evidence,
        main.admin_register_release_digest, main.review_worker_loop, main.review_worker_pass,
        main.review_rules_refresh_loop, main._sev_claimed_seat, main._sev_refusal,
        main._sev_header_version))
    return mods, routes


def test_a9_no_statement_of_the_lane_or_the_review_modules_writes_a_match_rating_or_gold_table():
    mods, routes = _lane_sources()
    written = written_tables(mods) | written_tables(routes)
    assert written <= LANE_WRITES, sorted(written - LANE_WRITES)
    assert not (written & set(PROTECTED)), sorted(written & set(PROTECTED))
    reads = " ".join(n.value for n in ast.walk(ast.parse(mods))
                     if isinstance(n, ast.Constant) and isinstance(n.value, str))
    assert "FROM matches" in reads and "JOIN ranked_series" in reads and "JOIN players" in reads


def test_a9_the_statement_scan_sees_a_write_when_there_is_one():
    src = ('x = "UPDATE players SET gold = gold + 1"\n'
           'y = f"INSERT INTO gold_ledger (a) VALUES ({1})"\n')
    assert written_tables(src) == {"players", "gold_ledger"}


_INSERT_COLS = re.compile(r"INSERT\s+INTO\s+([a-z_]+)\s*\(([^)]*)\)")
_SET_COLS = re.compile(r"(?:\bSET|,)\s*([a-z_]+)\s*=(?!=)")
_UPDATE = re.compile(r"(?:^|[^O]\s)UPDATE\s+([a-z_]+)\s+SET\s+(.*?)(?:\bWHERE\b|$)", re.S)
_UPSERT = re.compile(r"INSERT\s+INTO\s+([a-z_]+)(?:(?!INSERT\s|DO\s+NOTHING).)*?DO\s+UPDATE\s+SET\s+"
                     r"(.*?)(?:\bRETURNING\b|(?=\bINSERT\s|(?<!DO\s)\bUPDATE\s+[a-z_]+\s+SET\b)|$)", re.S)


def assigned_columns(source: str) -> dict:
    lits = [n.value for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    out = {}
    for sql in (" ".join(lits[i:i + 12]) for i in range(len(lits))):
        for t, cols in _INSERT_COLS.findall(sql):
            out.setdefault(t, set()).update(c.strip() for c in cols.split(",") if c.strip())
        for pat in (_UPDATE, _UPSERT):
            for t, body in pat.findall(sql):
                out.setdefault(t, set()).update(_SET_COLS.findall(" SET " + body))
    return out


def test_the_models_declare_every_column_the_lane_assigns():
    import models
    got = assigned_columns(_read(API, "seat_evidence.py"))
    assert set(got) == LANE_WRITES, sorted(got)
    for table, cols in got.items():
        declared = set(models.Base.metadata.tables[table].columns.keys())
        assert cols <= declared, (table, sorted(cols - declared))
    assert {"rule_id", "rules_rev"} <= got["seat_evidence_findings"]
    assert "evaluated_rev" in got["seat_evidence_games"]
    assert got["review_cursor"] == {"name", "rules_rev", "updated_at"}
    assert {"match_id", "created_at"} <= got["review_seen"]


def test_the_column_check_sees_an_undeclared_column():
    got = assigned_columns('q = "UPDATE seat_evidence SET reviewed_by = 1 WHERE id = 2"\n')
    assert got == {"seat_evidence": {"reviewed_by"}}


# -- the match path and the worker's role -------------------------------------

def test_the_match_report_path_names_nothing_of_the_lane():
    main = _main()
    for fn in (main.submit_match, main.submit_macro_evidence):
        src = inspect.getsource(fn)
        for word in ("_sev", "seat_evidence", "_review_rules", "review_"):
            assert word not in src, (fn.__name__, word)


def _lifespan_branches(source):
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                and node.test.id == "IS_REPLICA"):
            return (" ".join(ast.unparse(n) for n in node.body),
                    " ".join(ast.unparse(n) for n in node.orelse))
    raise AssertionError("lifespan has no IS_REPLICA branch")


def test_the_worker_starts_on_the_primary_branch_only_and_the_standby_says_so():
    main = _main()
    replica, primary = _lifespan_branches(inspect.getsource(main.lifespan))
    assert "review_worker_loop" in primary and "review_worker_loop" not in replica
    assert "[REVIEW] worker=standby-disabled" in replica
    assert "[REVIEW] worker=primary" in primary
    assert "[REVIEW] worker=standby-disabled" not in primary


def test_the_branch_check_sees_a_worker_on_the_replica():
    src = ("async def f():\n    if IS_REPLICA:\n        go(review_worker_loop)\n"
           "    else:\n        go(review_worker_loop)\n")
    replica, _primary = _lifespan_branches(src)
    assert "review_worker_loop" in replica


def test_the_rules_loader_runs_on_both_roles():
    main = _main()
    src = textwrap.dedent(inspect.getsource(main.lifespan))
    replica, primary = _lifespan_branches(src)
    assert "review_rules_refresh_loop" in src
    assert "review_rules_refresh_loop" not in replica and "review_rules_refresh_loop" not in primary


def test_the_pass_line_names_the_revision_and_counts():
    main = _main()
    assert main._review_pass_line("absent", {"off": 1}, {"evaluated": 0, "fired": 0}) == \
        "[REVIEW] pass rev=absent evaluated=0 fired=0 errors=0"
    line = main._review_pass_line("0123456789ab", {"evaluated": 4, "fired": 2, "rule_errors": 1,
                                                   "error:ValueError": 1},
                                  {"evaluated": 3, "fired": 1, "rule_errors": 0})
    assert line == "[REVIEW] pass rev=0123456789ab evaluated=7 fired=3 errors=2"


# -- the health words -----------------------------------------------------------

def test_the_seat_evidence_word_is_derived_from_the_routing_table(monkeypatch):
    main = _main()
    assert main._seat_evidence_health_word() == 1
    kept = [r for r in main.app.router.routes
            if getattr(r, "endpoint", None) is not main.submit_seat_evidence]
    monkeypatch.setattr(main.app.router, "routes", kept)
    assert main._seat_evidence_health_word() == 0


def test_the_health_words_are_declared_required():
    import schemas
    fields = schemas.HealthResponse.model_fields
    assert fields["seat_evidence"].annotation is int and fields["seat_evidence"].is_required()
    for k in ("review_eval", "review_rules"):
        assert fields[k].annotation is str and fields[k].is_required(), k


def test_both_health_arms_carry_the_review_words():
    main = _main()
    src = inspect.getsource(main.health_check)
    for k in ("seat_evidence=", "review_eval=", "review_rules="):
        assert src.count(k) == 2, k


# -- the migration and the bot -----------------------------------------------------

def test_the_migration_seeds_only_the_operational_switches():
    sql = _read(BACKEND, "sql", "368_seat_evidence.sql")
    seeded = re.findall(r"\('([a-z_]+)',\s*'[01]'\)", sql)
    assert sorted(seeded) == sorted(se.SWITCHES)
    assert "BEGIN;" in sql and "COMMIT;" in sql
    for word in ("rule_id", "rules_rev", "evaluated_rev", "review_sitting_dirty", "review_cursor",
                 "review_seen", "seat_evidence_seeded_keys"):
        assert word in sql, word
    assert not re.search(r"\bkind\s+VARCHAR", sql)
    assert "position_at" not in sql and "position_id" not in sql
    # the seeds are recorded as this file's own, in the same statement
    assert re.search(r"WITH seeded AS \(\s*INSERT INTO runtime_settings.*?RETURNING key\s*\)\s*"
                     r"INSERT INTO seat_evidence_seeded_keys", sql, re.S)


def test_the_rollback_states_its_assumption_and_deletes_only_seeded_keys():
    sql = _read(BACKEND, "sql", "rollback_368_seat_evidence.sql")
    head = sql.split("BEGIN;")[0]
    assert "ASSUMPTION" in head and "seat_evidence_seeded_keys" in head
    body = sql.split("BEGIN;")[1]
    deletes = re.findall(r"DELETE FROM runtime_settings.*?;", body, re.S)
    assert len(deletes) == 1 and "USING seat_evidence_seeded_keys" in deletes[0]
    assert "DROP TABLE IF EXISTS seat_evidence_seeded_keys" in body
    assert body.index("DELETE FROM runtime_settings") < body.index("DROP TABLE IF EXISTS seat_evidence_seeded_keys")


def test_l7_the_compat_route_checks_the_switch_right_after_the_session():
    """Static order inside the route: session, then the switch, then any
    validation, signature work or storage."""
    main = _main()
    src = textwrap.dedent(inspect.getsource(main.submit_compat_outcome))
    i_session = src.index("_strict_steam_session_ok")
    i_switch = src.index('"seat_evidence_accept"')
    assert i_session < i_switch
    for later in ("check_compat", "verify_compat_sig", "store_compat", "select(Player.id)"):
        assert i_switch < src.index(later), later
    assert '"seat_evidence_off"' in src


def test_the_bot_prints_the_rendered_line_and_adds_no_wording():
    src = _read(BACKEND, "discord_bot.py")
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_review_flag_line")
    ns = {"json": json}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "bot", "exec"), ns)
    line = ns["_review_flag_line"]
    assert line({"line": "synthetic 7 of 9", "items": []}) == "synthetic 7 of 9"
    assert line(json.dumps({"line": "x 1"})) == "x 1"
    assert line({"items": [{"a": 1}]}) == "review: no line"
    assert line("not json") == "review: no line"
    assert '"review"' in src and "_review_flag_line(f.get(\"flag_details\"))" in src
