"""The census mode of tools/register_release_digests.py (--census), no database.

  K1  the check the step applies is the server's own module, loaded from
      backend/api of this checkout, and the route steps it mirrors are still
      the route's (a drift test over main.py and card_evidence.py);
  K2  a census dump in the client's format: the dry run prints the one row
      register_census would insert and sends nothing;
  K3  every dump the route refuses (card_census_fixture.REFUSED) is refused
      with exit 3 in the dry run, the real run and --emit-sql, with nothing
      sent and nothing written, naming the field the server names;
  K4  the real run against a recording transport: the route, the signature
      over admin:<id>:card_census:<digest>, the body (the file's bytes), the
      version header, and its reading of every answer;
  K5  a real run missing the secret, the api base, --admin or --mod-version
      sends nothing and exits 2;
  K6  --emit-sql: the one insert, its values, its post-check, and that it
      never replaces a file.

The route's own verdict on every fixture, and the emitted row against the
route's row in PostgreSQL, are test_card_census_register_pg.py.
"""

import hashlib
import hmac
import io
import json
import os
import re
import sys
from contextlib import redirect_stdout
from urllib.parse import parse_qs, urlsplit

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
API = os.path.join(REPO, "backend", "api")
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import card_census_fixture as cf  # noqa: E402
import card_measures as cm  # noqa: E402
import register_release_digests as rrd  # noqa: E402

ADMIN = "7" * 17
SECRET = "census-unit-secret"
ENV = {"ADMIN_HMAC_SECRET": SECRET, "SCR_API_BASE": "http://box:8443/"}


def _run(argv, environ=None, transport=None):
    out = io.StringIO()
    with redirect_stdout(out):
        code = rrd.main(argv, environ=environ if environ is not None else {}, transport=transport)
    return code, out.getvalue()


class Recorder:
    def __init__(self, status=200, text=None, raises=None):
        self.calls, self.status, self.text, self.raises = [], status, text, raises

    def __call__(self, url, headers, body=b""):
        self.calls.append((url, headers, body))
        if self.raises:
            raise self.raises
        return self.status, self.text


def _write(tmp_path, data, name="CompetitiveRounds.card-census.json"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def _expected_row(data):
    doc = json.loads(data)
    c = cm.census_from_dump(doc)
    return {"digest": c.digest, "census": cm.dumps(doc), "card_count": c.count, "slot_count": c.slots,
            "game_dll_sha256": c.game_sha}


def _real(path, extra=()):
    return ["--census", path, "--admin", ADMIN, "--mod-version", "1.41.0"] + list(extra)


# -- K1 -------------------------------------------------------------------------------------------

def test_k1_the_check_is_the_servers_own_module():
    mod = rrd.server_census_check()
    assert mod is cm
    assert os.path.normcase(os.path.abspath(mod.__file__)) == os.path.normcase(os.path.join(API, "card_measures.py"))
    assert os.path.normcase(rrd.API_DIR) == os.path.normcase(API)


def test_k1_a_card_measures_from_elsewhere_is_refused(tmp_path, monkeypatch):
    fake = tmp_path / "card_measures.py"
    fake.write_text("rm = None\n")
    monkeypatch.setitem(sys.modules, "card_measures", type(sys)("card_measures"))
    sys.modules["card_measures"].__file__ = str(fake)
    with pytest.raises(rrd.Refused):
        rrd.server_census_check()
    code, out = _run(["--census", _write(tmp_path, cf.VALID["client_file"]), "--dry-run"])
    assert code == rrd.EXIT_REFUSED and "not the server's" in out


def test_k1_a_checkout_without_the_server_module_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(rrd, "API_DIR", str(tmp_path))
    code, out = _run(["--census", _write(tmp_path, cf.VALID["client_file"]), "--dry-run"])
    assert code == rrd.EXIT_REFUSED and "is not in this checkout" in out


def test_k1_the_server_module_absent_from_its_own_checkout_is_refused(tmp_path, monkeypatch):
    # API_DIR and the cached module stay the server's own, so the loaded-module path check would pass;
    # only the file is absent. The refusal must come from the existence guard itself, so that removing
    # the guard lets the run through (CENSUS-R1 M1: mutant M25 was killed by wording alone before).
    want = os.path.join(rrd.API_DIR, "card_measures.py")
    real_isfile = os.path.isfile
    monkeypatch.setattr(rrd.os.path, "isfile", lambda p: False if rrd._same_file(p, want) else real_isfile(p))
    with pytest.raises(rrd.Refused, match="is not in this checkout"):
        rrd.server_census_check()
    code, out = _run(["--census", _write(tmp_path, cf.VALID["client_file"]), "--dry-run"])
    assert code == rrd.EXIT_REFUSED and "is not in this checkout" in out
    monkeypatch.undo()
    assert rrd.server_census_check() is cm


def _function_source(path, head):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    start = text.index(head)
    nxt = re.compile(r"\n(?:@app\.|async def |def )").search(text, start + len(head))
    return text[start:nxt.start() if nxt else len(text)]


def test_k1_the_route_steps_the_mode_mirrors_are_still_the_routes():
    route = _function_source(os.path.join(API, "main.py"), "async def admin_register_card_census(")
    with open(os.path.join(API, "main.py"), encoding="utf-8") as f:
        main_text = f.read()
    assert '@app.post("%s", tags=["Admin"])\nasync def admin_register_card_census(' % rrd.CENSUS_ROUTE in main_text
    for literal in ('digest: str = Query(..., max_length=%d)' % rrd.CENSUS_DIGEST_MAX,
                    'await _require_admin(db, admin_steam_id, "%s", digest, hmac_signature)' % rrd.CENSUS_ACTION,
                    "doc = _json.loads(await request.body())\n    except Exception:",
                    'if not isinstance(doc, dict) or doc.get("digest") != digest:',
                    "return await _cev.register_census(db, doc)"):
        assert route.count(literal) == 1, literal
    assert re.search(r"^import json as _json$", main_text, re.M)
    assert 'return f"admin:{admin_steam_id}:{action}:{target or \'\'}"' in main_text
    reg = _function_source(os.path.join(API, "card_evidence.py"), "async def register_census(")
    for literal in ("c = cm.census_from_dump(doc)\n    except cm.Refusal as r:",
                    '"INSERT INTO card_pool_registry (digest, census, card_count, slot_count, game_dll_sha256) "',
                    '"VALUES (:d, CAST(:c AS jsonb), :n, :ns, :g) ON CONFLICT (digest) DO NOTHING RETURNING digest"',
                    '{"d": c.digest, "c": cm.dumps(doc), "n": c.count, "ns": c.slots, "g": c.game_sha}',
                    '"status": "registered" if got else "already_registered", "digest": c.digest,',
                    '"card_count": c.count, "slot_count": c.slots}'):
        assert reg.count(literal) == 1, literal


def test_k1_the_fixture_writer_is_the_servers_serialiser():
    d = cf.dump()
    assert cf.client_bytes(d) == cm.dumps(d).encode("ascii")
    assert cf.census_text(cf.cards()) == cm.dumps({"census": 1, "cards": cf.cards()})


# -- K2 -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(cf.VALID))
def test_k2_a_valid_dump_dry_runs_to_its_row_and_sends_nothing(tmp_path, name):
    data = cf.VALID[name]
    path = _write(tmp_path, data)
    rec = Recorder()
    code, out = _run(_real(path, ["--dry-run"]), ENV, rec)
    assert code == rrd.EXIT_OK, out
    assert rec.calls == []
    row = _expected_row(data)
    assert rrd.census_plan(path) == (data, row)
    assert ("WOULD    census    digest=%s cards=%d slots=%d game_dll_sha256=%s"
            % (row["digest"], row["card_count"], row["slot_count"], row["game_dll_sha256"])) in out
    assert "DRY RUN  1 row would be registered; nothing was sent." in out


def test_k2_the_dry_run_names_what_the_real_run_still_needs(tmp_path):
    code, out = _run(["--census", _write(tmp_path, cf.VALID["client_file"]), "--dry-run"], {})
    assert code == rrd.EXIT_OK, out
    assert "The real run also needs: ADMIN_HMAC_SECRET, SCR_API_BASE, --admin, --mod-version." in out


def test_k2_expect_digest(tmp_path):
    data = cf.VALID["client_file"]
    path = _write(tmp_path, data)
    d = _expected_row(data)["digest"]
    assert _run(["--census", path, "--expect-digest", d, "--dry-run"])[0] == rrd.EXIT_OK
    code, out = _run(["--census", path, "--expect-digest", "0" * 64, "--dry-run"])
    assert code == rrd.EXIT_REFUSED and "not --expect-digest" in out
    code, out = _run(["--census", path, "--expect-digest", d.upper(), "--dry-run"])
    assert code == rrd.EXIT_REFUSED and "is not 64 lowercase hex" in out


# -- K3 -------------------------------------------------------------------------------------------

def _server_field(data):
    """What the server would answer, by the server's own functions: the route's two steps, then
    census_from_dump. (None, None) for a registration."""
    try:
        doc = json.loads(data)
    except Exception:
        return 400, "body"
    if not isinstance(doc, dict) or not isinstance(doc.get("digest"), str):
        return 422, "digest"
    if len(doc["digest"]) > 64:
        return 422, None
    try:
        cm.census_from_dump(doc)
    except cm.Refusal as r:
        return 422, r.field
    except Exception:  # noqa: BLE001 - uncaught on the route: a 500
        return 500, None
    return None, None


@pytest.mark.parametrize("name", sorted(cf.REFUSED))
def test_k3_every_refused_dump_exits_3_and_sends_and_writes_nothing(tmp_path, name):
    data, answer = cf.REFUSED[name]
    assert _server_field(data) == answer
    path = _write(tmp_path, data)
    rec = Recorder()
    for extra in (["--dry-run"], [], ["--emit-sql", str(tmp_path / "999_census.sql")]):
        code, out = _run(_real(path, extra), ENV, rec)
        assert code == rrd.EXIT_REFUSED, (extra, out)
        assert out.startswith("REFUSED: ") and "Nothing registered." in out
        assert out.count("(the route would answer %d%s)" % (answer[0], " " + answer[1] if answer[1] else "")) == 1, out
        if answer[1] not in (None, "body", "digest"):
            assert "refuses the dump: %s (the route would answer 422 %s)" % (answer[1], answer[1]) in out
    assert rec.calls == []
    assert not os.path.exists(str(tmp_path / "999_census.sql"))


def test_k3_an_unreadable_file_is_refused(tmp_path):
    code, out = _run(_real(str(tmp_path / "absent.json"), ["--dry-run"]), ENV)
    assert code == rrd.EXIT_REFUSED and "cannot be read" in out


# -- K4 -------------------------------------------------------------------------------------------

def _answer(row, status="registered", **extra):
    a = {"status": status, "digest": row["digest"], "card_count": row["card_count"], "slot_count": row["slot_count"]}
    a.update(extra)
    return json.dumps(a)


def test_k4_the_real_run_signs_the_digest_and_sends_the_files_bytes(tmp_path):
    data = cf.VALID["client_file_bom"]
    path = _write(tmp_path, data)
    row = _expected_row(data)
    rec = Recorder(200, _answer(row))
    code, out = _run(_real(path), ENV, rec)
    assert code == rrd.EXIT_OK, out
    assert len(rec.calls) == 1
    url, headers, body = rec.calls[0]
    parts = urlsplit(url)
    assert url.startswith("http://box:8443/api/v1/admin/card-pool-census?")
    q = parse_qs(parts.query)
    assert q["admin_steam_id"] == [ADMIN] and q["digest"] == [row["digest"]]
    want = hmac.new(SECRET.encode(), ("admin:%s:card_census:%s" % (ADMIN, row["digest"])).encode(),
                    hashlib.sha256).hexdigest()
    assert q["hmac_signature"] == [want]
    assert body == data
    assert headers["X-Mod-Version"] == "1.41.0" and headers["Content-Type"] == "application/json"
    assert "INSERTED census    digest=%s" % row["digest"] in out and "DONE     1 row: 1 inserted." in out


def test_k4_already_registered_is_success_and_says_what_to_check(tmp_path):
    data = cf.VALID["client_file"]
    path = _write(tmp_path, data)
    row = _expected_row(data)
    code, out = _run(_real(path), ENV, Recorder(200, _answer(row, "already_registered")))
    assert code == rrd.EXIT_OK, out
    assert "(already registered)" in out and "read its game_dll_sha256 back" in out


@pytest.mark.parametrize("status,text", [
    (403, '{"detail":"Bad admin signature"}'),
    (422, '{"detail":"card_count"}'),
    (500, "Internal Server Error"),
    (200, "not json"),
    (200, '{"status":"recorded"}'),
    (200, "WRONG_DIGEST"),
    (200, "WRONG_COUNT"),
    (200, "EXTRA_KEY"),
    (200, "WRONG_STATUS"),
    (500, "REGISTERED_BODY"),
])
def test_k4_any_other_answer_exits_1(tmp_path, status, text):
    data = cf.VALID["client_file"]
    path = _write(tmp_path, data)
    row = _expected_row(data)
    text = {"WRONG_DIGEST": _answer(dict(row, digest="0" * 64)),
            "WRONG_COUNT": _answer(dict(row, card_count=row["card_count"] + 1)),
            "EXTRA_KEY": _answer(row, more=1),
            "WRONG_STATUS": _answer(row, "recorded"),
            "REGISTERED_BODY": _answer(row)}.get(text, text)
    code, out = _run(_real(path), ENV, Recorder(status, text))
    assert code == rrd.EXIT_SERVER, out
    assert "FAILED   census" in out


def test_k4_a_transport_failure_exits_1(tmp_path):
    path = _write(tmp_path, cf.VALID["client_file"])
    code, out = _run(_real(path), ENV, Recorder(raises=OSError("down")))
    assert code == rrd.EXIT_SERVER and "OSError" in out


# -- K5 -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("drop", ["ADMIN_HMAC_SECRET", "SCR_API_BASE", "--admin", "--mod-version"])
def test_k5_a_missing_variable_sends_nothing_and_exits_2(tmp_path, drop):
    path = _write(tmp_path, cf.VALID["client_file"])
    env = {k: v for k, v in ENV.items() if k != drop}
    argv = ["--census", path]
    if drop != "--admin":
        argv += ["--admin", ADMIN]
    if drop != "--mod-version":
        argv += ["--mod-version", "1.41.0"]
    rec = Recorder(200, "{}")
    code, out = _run(argv, env, rec)
    assert code == rrd.EXIT_ENV, out
    assert rec.calls == [] and ("NOT SENT %s missing; nothing was sent." % drop) in out


@pytest.mark.parametrize("flag,value", [("--admin", "123"), ("--mod-version", "1.41 0"), ("--mod-version", "")])
def test_k5_a_malformed_argument_is_refused(tmp_path, flag, value):
    path = _write(tmp_path, cf.VALID["client_file"])
    argv = _real(path)
    argv[argv.index(flag) + 1] = value
    rec = Recorder(200, "{}")
    code, out = _run(argv, ENV, rec)
    assert code == rrd.EXIT_REFUSED and rec.calls == [], out


# -- K6 -------------------------------------------------------------------------------------------

def _literal(sql):
    m = re.search(r"^    \('([0-9a-f]{64})', CAST\('((?:[^']|'')*)' AS jsonb\), (\d+), (\d+), '([0-9a-f]{64})'\)$",
                  sql, re.M)
    assert m, sql[:2000]
    return m.group(1), m.group(2).replace("''", "'"), int(m.group(3)), int(m.group(4)), m.group(5)


@pytest.mark.parametrize("name", sorted(cf.VALID))
def test_k6_the_emitted_file_holds_the_one_insert_register_census_performs(tmp_path, name):
    data = cf.VALID[name]
    path = _write(tmp_path, data)
    target = tmp_path / "401_card_pool_census.sql"
    code, out = _run(["--census", path, "--emit-sql", str(target)])
    assert code == rrd.EXIT_OK, out
    sql = target.read_bytes().decode("ascii")
    assert "\r" not in sql
    row = _expected_row(data)
    assert _literal(sql) == (row["digest"], row["census"], row["card_count"], row["slot_count"],
                             row["game_dll_sha256"])
    assert json.loads(_literal(sql)[1]) == json.loads(data)
    assert sql.count("INSERT INTO card_pool_registry (digest, census, card_count, slot_count, game_dll_sha256) "
                     "VALUES") == 1
    assert sql.count("ON CONFLICT (digest) DO NOTHING;") == 1
    code_lines = "\n".join(l for l in sql.splitlines() if not l.startswith("--"))
    assert code_lines.count("INSERT ") == 1 and "UPDATE " not in code_lines and "DELETE " not in code_lines
    assert sql.startswith("-- 401_card_pool_census.sql: card pool census registry row: digest %s" % row["digest"])
    assert "\nBEGIN;\n" in sql and sql.endswith("\nCOMMIT;\n")
    assert ("SELECT count(*) INTO missing FROM (VALUES ('%s', %d, %d, '%s'))"
            % (row["digest"], row["card_count"], row["slot_count"], row["game_dll_sha256"])) in sql
    assert "RAISE NOTICE 'migration 401_card_pool_census.sql: census %s present (%d cards, %d slots)';" % (
        row["digest"], row["card_count"], row["slot_count"]) in sql
    assert "WROTE    %s: 1 row" % target in out


def test_k6_the_writer_never_replaces_a_file_and_takes_only_a_plain_name(tmp_path):
    path = _write(tmp_path, cf.VALID["client_file"])
    target = tmp_path / "401_card_pool_census.sql"
    target.write_text("keep")
    code, out = _run(["--census", path, "--emit-sql", str(target)])
    assert code == rrd.EXIT_REFUSED and "never replaces a file" in out
    assert target.read_text() == "keep"
    with pytest.raises(SystemExit) as e:
        _run(["--census", path, "--emit-sql", str(tmp_path / "401_x'y.sql")])
    assert e.value.code == 2


@pytest.mark.parametrize("name", ["401_search_path.sql", "401_SET_CONFIG.sql"])
def test_k6_a_name_the_landing_refuses_is_refused_before_anything_is_written(tmp_path, capsys, name):
    # The name goes into the header comment and the RAISE literals, and the data-only landing refuses
    # search_path and set_config wherever they appear (CENSUS-R1 H1), so the writer never produces the file.
    path = _write(tmp_path, cf.VALID["client_file"])
    target = tmp_path / name
    with pytest.raises(SystemExit) as e:
        _run(["--census", path, "--emit-sql", str(target)])
    assert e.value.code == 2 and "search_path or set_config" in capsys.readouterr().err
    assert not target.exists()
    with pytest.raises(ValueError):
        rrd.census_migration_text(name, _expected_row(cf.VALID["client_file"]))
    # the release mode shares the argparse type, so the same name is refused there before any DLL is read
    with pytest.raises(SystemExit) as e:
        rrd.main(["--version", "1.41.0", "--skip-game-files", "--emit-sql", str(target)])
    assert e.value.code == 2 and "search_path or set_config" in capsys.readouterr().err
    assert not target.exists()


def test_k6_a_census_naming_search_path_is_refused_for_sql_only(tmp_path):
    data = cf.client_bytes(cf.dump(pool=cf.cards(extra=[["search_path", 0, 1, None, None, 0]])))
    path = _write(tmp_path, data)
    assert _run(["--census", path, "--dry-run"])[0] == rrd.EXIT_OK
    target = tmp_path / "401_card_pool_census.sql"
    code, out = _run(["--census", path, "--emit-sql", str(target)])
    assert code == rrd.EXIT_REFUSED and "search_path or set_config" in out
    assert not target.exists()


def test_k6_the_sql_writer_refuses_values_outside_the_registry():
    row = _expected_row(cf.VALID["client_file"])
    for bad in (dict(row, digest=row["digest"][:-1] + "'"), dict(row, game_dll_sha256="x" * 64),
                dict(row, card_count=True), dict(row, slot_count="5"), dict(row, census=row["census"] + "\x01"),
                dict(row, census=row["census"].replace("Leach", "Leäch"))):
        with pytest.raises(rrd.Refused):
            rrd.census_migration_text("401_card_pool_census.sql", bad)
    with pytest.raises(ValueError):
        rrd.census_migration_text("401_x'y.sql", row)


def test_k6_the_census_flag_in_its_equals_form_selects_the_census_mode(tmp_path):
    path = _write(tmp_path, cf.VALID["client_file"])
    code, out = _run(["--census=" + path, "--dry-run"])
    assert code == rrd.EXIT_OK and "DRY RUN  1 row would be registered" in out, out


def test_k6_the_release_mode_is_untouched_by_the_census_dispatch():
    with pytest.raises(SystemExit) as e:
        _run(["--version", "1.41.0", "--skip-game-files", "--dry-run"])
    assert e.value.code == 2
