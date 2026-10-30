"""The release digest step (tools/register_release_digests.py), no database.

  D1  the step's mirror of the client (the game-file list and its order, the
      survey caps, the variant words, the commit rule, the plug-in GUID) equals
      the client's C# source, and its mirror of the server's acceptance rules
      equals the server modules;
  D2  the build tuple read from a synthetic assembly written from ECMA-335
      (release_digests_fixture.build_assembly) across PE32/PE32+, 2/4-byte
      heap indexes and a 4-byte coded index: version, variant, commit and the
      DLL digest, plus every case of PeerBuild's commit rule;
  D3  the refusals of a DLL: a wrong embedded version, commit or variant, no
      or two BepInPlugin attributes, a foreign GUID, two variant markers or
      none, and bytes that are no assembly; every refusal sends nothing;
  D4  the game-file digests against a fixture install: every listed file by
      its client file id, digest equal to SHA-256 of its bytes (chunk-boundary,
      multi-chunk and empty files), the survey's caps and file states;
  D5  the dry run prints every row and sends nothing; a real run without the
      admin secret sends nothing and exits 2;
  D6  idempotence of the step's own accounting against a recording server
      (the live route is test_release_digests_pg.py);
  D7  the --emit-sql file: its shape, and that it never replaces a file.

RELEASE_DIGESTS_REAL_DLL, when set, names a built CompetitiveRounds.dll for
one more case: the reader against a real Roslyn image, cross-checked by a raw
byte search that shares nothing with the reader.
"""

import hashlib
import hmac
import io
import math
import os
import re
import sys
from contextlib import redirect_stdout

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import register_release_digests as rrd  # noqa: E402
import release_digests_fixture as fx  # noqa: E402

SECRET = "test-secret-" + hashlib.sha256(os.urandom(16)).hexdigest()[:16]


def _admin():
    """A generated 17-digit id (no fixed literal)."""
    return "9" + str(int.from_bytes(os.urandom(8), "big")).zfill(16)[:16]


def _src(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


def _run(argv, environ=None, transport=None):
    out = io.StringIO()
    with redirect_stdout(out):
        code = rrd.main(argv, environ={} if environ is None else environ, transport=transport)
    return code, out.getvalue()


class _Recorder:
    """A transport that must not be called."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        raise AssertionError("the step sent a request: " + url)


@pytest.fixture()
def install(tmp_path):
    root, expected = fx.make_install(str(tmp_path / "lib"))
    return root, expected


def _dll(tmp_path, name="CompetitiveRounds.dll", **kw):
    path = tmp_path / name
    data = fx.build_assembly(**kw)
    path.write_bytes(data)
    return str(path), data


# -- D1: the mirrors ----------------------------------------------------------------------

def test_d1_game_file_list_order_and_survey_caps_equal_the_client():
    game, loader, door = fx.client_lists()
    assert (rrd.GAME_FILES, rrd.LOADER_FILES, rrd.DOORSTOP_FILE) == (game, loader, door)
    src = _src("plugin", "IdentityClockEvidence.cs")
    body = re.search(r"private static IList<I\.FileTarget> FileList\(string managed, string root\)\s*\{(.*?)\n        \}",
                     src, re.S).group(1)
    order = [body.index(s) for s in ("foreach (var f in GAME_FILES)", "foreach (var f in LOADER_FILES)",
                                     "Path.Combine(root, DOORSTOP_FILE)")]
    assert order == sorted(order) and "Id = id++" in body
    core = _src("plugin", "IdentityClockCore.cs")

    def const(name):
        found = re.findall(r"\bconst (?:int|long) (?:[A-Z_]+ = [^,;]+, )*%s = ([^,;]+)[,;]" % name, core)
        assert len(found) == 1, (name, found)
        return math.prod(int(x.strip().rstrip("L")) for x in found[0].split("*"))

    assert const("CHUNK_BYTES") == rrd.CHUNK_BYTES
    assert const("FILE_BYTES_MAX") == rrd.FILE_BYTES_MAX
    assert const("JOB_BYTES_MAX") == rrd.JOB_BYTES_MAX
    assert const("JOB_UNITS_MAX") == rrd.JOB_UNITS_MAX
    assert const("GDIG_MAX") == rrd.GDIG_MAX
    assert len(game) + len(loader) + 1 <= rrd.GDIG_MAX
    assert "if (_fileBytes > FILE_BYTES_MAX) { R.Truncated = true; NextFile(READ_FAILED" in core
    assert "if (R.Units >= JOB_UNITS_MAX || R.Bytes >= JOB_BYTES_MAX) { Stop(); return false; }" in core
    # BepInEx's paths, as the client asks for them.
    assert "game = Paths.ManagedPath; root = Paths.GameRootPath;" in src
    assert "string core = SafePath(() => Paths.BepInExAssemblyDirectory);" in src


def _if_chain(src, anchor):
    """The string literals of the #if THUNDERSTORE / #elif SCR_G3 / #else chain after `anchor`."""
    tail = src[src.index(anchor):]
    m = re.search(r'#if THUNDERSTORE\s*"([^"]+)";\s*#elif SCR_G3\s*"([^"]+)";\s*#else\s*"([^"]+)";\s*#endif', tail)
    return m.groups()


def test_d1_variant_words_commit_rule_and_guid_equal_the_client():
    words = _if_chain(_src("plugin", "PeerBuild.cs"), "internal static string BuildValue()")
    markers = _if_chain(_src("plugin", "ApiClient.cs"), "internal const string BuildVariantMarker =")
    assert tuple(zip(markers, words)) == rrd.VARIANT_MARKERS
    peer = _src("plugin", "PeerBuild.cs")
    for line in ('string sha = "nosha";',
                 "typeof(PeerBuild).Assembly, typeof(AssemblyInformationalVersionAttribute));",
                 "int plus = iv != null ? iv.IndexOf('+') : -1;",
                 "if (plus >= 0 && plus + 1 < iv.Length)",
                 "sha = s.Length > 12 ? s.Substring(0, 12) : s;",
                 'return Plugin.ModVersion + "|" + variant + "|" + sha;'):
        assert line in peer, line
    plugin = _src("plugin", "Plugin.cs")
    assert '[BepInPlugin(ModId, ModName, ModVersion)]' in plugin
    assert 'public const string ModId = "%s";' % rrd.PLUGIN_GUID in plugin
    core = _src("plugin", "SeatEvidenceCore.cs")
    assert "return IsBuildPart(version, 16) && IsBuildPart(variant, 16) && IsBuildPart(commit, 12);" in core
    seat = _src("plugin", "SeatEvidence.cs")
    assert "try { sha = C.Sha256Hex(File.ReadAllBytes(path)); state = \"ok\"; }" in seat
    assert '_ownPath = LocationOf(typeof(SeatEvidence));' in seat


def test_d1_server_rules_equal_the_server_modules():
    import identity_clock_evidence as ice
    import seat_evidence as se
    assert se._BUILD_PART.pattern == rrd.BUILD_PART.pattern
    assert se._HEX64.pattern == rrd.HEX64.pattern
    assert tuple(se.RELEASE_SOURCES) == rrd.SOURCES
    assert ice.W["id_max"] >= len(rrd.GAME_FILES) + len(rrd.LOADER_FILES)
    main_src = _src("backend", "api", "main.py")
    assert '@app.post("%s", tags=["Admin"])' % rrd.RELEASE_ROUTE in main_src
    assert '@app.post("%s", tags=["Admin"])' % rrd.GAME_FILE_ROUTE in main_src
    assert 'return f"admin:{admin_steam_id}:{action}:{target or \'\'}"' in main_src


# -- D2: the build tuple from an assembly image --------------------------------------------

@pytest.mark.parametrize("pe32plus,wide_heaps,pad", [(False, False, 0), (True, False, 0),
                                                     (False, True, 0), (True, True, 3000)])
def test_d2_build_identity_reads_the_fixture(pe32plus, wide_heaps, pad):
    data = fx.build_assembly(version="1.41.0", pe32plus=pe32plus, wide_heaps=wide_heaps, pad_typerefs=pad)
    got = rrd.build_identity(data)
    assert (got["version"], got["variant"], got["commit"]) == ("1.41.0", "standalone", fx.FULL_SHA[:12])
    assert got["dll_sha256"] == hashlib.sha256(data).hexdigest()
    assert got["guid"] == fx.GUID and got["plugin_type"] == ("CompetitiveRounds", "Plugin")
    assert got["informational"] == "1.0.0+" + fx.FULL_SHA


@pytest.mark.parametrize("informational,infos,commit", [
    ("1.0.0+" + fx.FULL_SHA, 1, fx.FULL_SHA[:12]),
    ("1.0.0+abc123", 1, "abc123"),
    ("1.0.0+", 1, "nosha"),
    ("1.0.0", 1, "nosha"),
    (None, 1, "nosha"),
    ("1.0.0+" + fx.FULL_SHA, 0, "nosha"),
    ("1.0.0+" + fx.FULL_SHA, 2, "nosha"),
])
def test_d2_commit_follows_peerbuild(informational, infos, commit):
    got = rrd.build_identity(fx.build_assembly(informational=informational, infos=infos))
    assert got["commit"] == commit


def test_d2_variant_follows_the_marker():
    got = rrd.build_identity(fx.build_assembly(markers=(fx.THUNDERSTORE,)))
    assert got["variant"] == "thunderstore"


# -- D3: refusals send nothing --------------------------------------------------------------

@pytest.mark.parametrize("kw,words", [
    (dict(plugins=0), "0 BepInPlugin attributes"),
    (dict(plugins=2), "2 BepInPlugin attributes"),
    (dict(guid="com.example.other"), "not the Competitive Rounds plug-in"),
    (dict(markers=()), "no SCR_BUILD_VARIANT marker"),
    (dict(markers=(fx.STANDALONE, fx.THUNDERSTORE)), "exactly one SCR_BUILD_VARIANT marker"),
    (dict(version="1.41.0 beta"), "empty build tuple"),
])
def test_d3_build_identity_refusals(kw, words):
    with pytest.raises(rrd.Refused) as e:
        rrd.build_identity(fx.build_assembly(**kw))
    assert words in str(e.value)


def test_d3_bytes_that_are_no_assembly_are_refused():
    good = fx.build_assembly()
    for data in (b"", b"MZ" + os.urandom(300), good[:0x180], good[: len(good) // 2]):
        with pytest.raises(rrd.Refused):
            rrd.build_identity(data)


def _argv(dll, version, root=None, *extra):
    argv = ["--dll", dll, "--version", version]
    argv += ["--game-root", root] if root else ["--skip-game-files"]
    return argv + list(extra)


def test_d3_version_mismatch_refuses_and_sends_nothing(tmp_path, install):
    root, _expected = install
    dll, _data = _dll(tmp_path, version="1.40.3")
    rec = _Recorder()
    code, out = _run(_argv(dll, "1.41.0", root, "--admin", _admin()),
                     {"ADMIN_HMAC_SECRET": SECRET, "SCR_API_BASE": "http://t"}, rec)
    assert code == rrd.EXIT_REFUSED and rec.calls == []
    assert "REFUSED: the DLL's embedded version is 1.40.3, not 1.41.0. Nothing registered." in out


@pytest.mark.parametrize("extra,words", [
    (("--commit", "fedcba9"), "embedded commit is 0123456789ab, which is not fedcba9"),
    (("--commit", "01234"), "is not a 7 to 40 character hex sha"),
    (("--variant", "thunderstore"), "the DLL is the standalone variant, not thunderstore"),
    (("--version", "1.41.0|x"), "is not a version the registry accepts"),
])
def test_d3_commit_variant_and_argument_refusals(tmp_path, extra, words):
    dll, _data = _dll(tmp_path)
    argv = _argv(dll, "1.41.0") + ["--admin", _admin()] + list(extra)
    rec = _Recorder()
    code, out = _run(argv, {"ADMIN_HMAC_SECRET": SECRET, "SCR_API_BASE": "http://t"}, rec)
    assert code == rrd.EXIT_REFUSED and rec.calls == [], out
    assert words in out


def test_d3_matching_commit_prefixes_pass(tmp_path):
    dll, _data = _dll(tmp_path)
    for given in (fx.FULL_SHA[:7], fx.FULL_SHA[:12], fx.FULL_SHA, fx.FULL_SHA.upper()):
        code, out = _run(_argv(dll, "1.41.0", None, "--commit", given, "--dry-run"))
        assert code == rrd.EXIT_OK, out


def test_d3_a_dll_without_a_commit_refuses_any_commit(tmp_path):
    dll, _data = _dll(tmp_path, informational="1.0.0")
    code, out = _run(_argv(dll, "1.41.0", None, "--commit", fx.FULL_SHA, "--dry-run"))
    assert code == rrd.EXIT_REFUSED and "embedded commit is nosha" in out


# -- D4: the game files ---------------------------------------------------------------------

def test_d4_every_listed_file_is_read_like_the_client(install):
    root, expected = install
    read = rrd.survey(rrd.game_targets(root))
    assert [e["file_id"] for e in read] == sorted(expected)
    for e in read:
        assert e["state"] == rrd.OK
        assert (e["name"], e["sha256"]) == expected[e["file_id"]]
        assert e["size"] == os.path.getsize(e["path"])
    assert read[2]["sha256"] == hashlib.sha256(b"").hexdigest()
    assert os.path.dirname(read[0]["path"]) == os.path.join(root, "ROUNDS_Data", "Managed")
    assert os.path.dirname(read[8]["path"]) == os.path.join(root, "BepInEx", "core")
    assert read[16]["path"] == os.path.join(root, "winhttp.dll")


def test_d4_survey_states_and_caps(install, monkeypatch):
    root, expected = install
    targets = rrd.game_targets(root)
    os.remove(targets[4][2])
    os.remove(targets[5][2])
    os.mkdir(targets[5][2])
    monkeypatch.setattr(rrd, "FILE_BYTES_MAX", 150_000)
    read = rrd.survey(targets)
    states = {e["file_id"]: e["state"] for e in read}
    assert states[0] == rrd.READ_FAILED            # 200,003 bytes > the patched cap
    assert states[1] == rrd.OK and states[3] == rrd.OK   # 65,536 and 131,072: at or under it
    assert states[4] == rrd.NO_FILE and states[5] == rrd.READ_FAILED
    assert all(e["sha256"] == "" for e in read if e["state"] != rrd.OK)
    # The cap is "read past": a file of exactly the cap is ok, one byte more is not.
    monkeypatch.setattr(rrd, "FILE_BYTES_MAX", 65_536)
    states = {e["file_id"]: e["state"] for e in rrd.survey(targets)}
    assert (states[1], states[3], states[6]) == (rrd.OK, rrd.READ_FAILED, rrd.READ_FAILED)
    # The job's byte cap: a file is finished only while the total stays under
    # it at every unit; the files after the stop are not_yet.
    monkeypatch.setattr(rrd, "FILE_BYTES_MAX", 64 * 1024 * 1024)
    monkeypatch.setattr(rrd, "JOB_BYTES_MAX", 200_003 + 65_536)
    read = rrd.survey(rrd.game_targets(root))
    states = [e["state"] for e in read]
    assert states[:2] == [rrd.OK, rrd.NOT_YET] and set(states[2:]) == {rrd.NOT_YET}
    monkeypatch.setattr(rrd, "JOB_BYTES_MAX", 200_003 + 65_536 + 1)
    assert [e["state"] for e in rrd.survey(rrd.game_targets(root))][:3] == [rrd.OK, rrd.OK, rrd.OK]
    monkeypatch.setattr(rrd, "JOB_BYTES_MAX", 192 * 1024 * 1024)
    monkeypatch.setattr(rrd, "JOB_UNITS_MAX", 5)      # file 0 takes 1 open + 4 reads + 1 finish = 6
    states = [e["state"] for e in rrd.survey(rrd.game_targets(root))]
    assert states[0] == rrd.NOT_YET and set(states) == {rrd.NOT_YET}
    monkeypatch.setattr(rrd, "JOB_UNITS_MAX", 6)
    assert [e["state"] for e in rrd.survey(rrd.game_targets(root))][:2] == [rrd.OK, rrd.NOT_YET]


def test_d4_a_missing_file_refuses_the_run(tmp_path, install):
    root, _expected = install
    os.remove(os.path.join(root, "BepInEx", "core", "HarmonyXInterop.dll"))
    dll, _data = _dll(tmp_path)
    code, out = _run(_argv(dll, "1.41.0", root, "--dry-run"))
    assert code == rrd.EXIT_REFUSED
    assert "the client would report no digest for 12 HarmonyXInterop.dll (no_file)" in out


def test_d4_steam_label_and_explicit_files(tmp_path, install):
    root, expected = install
    assert rrd.steam_label(root) == "steam." + fx.BUILD_ID
    other, _e = fx.make_install(str(tmp_path / "lib2"), installdir="ROUNDS")
    os.rename(other, other + "-moved")
    with pytest.raises(rrd.Refused):
        rrd.steam_label(other + "-moved")
    dll, _data = _dll(tmp_path)
    targets = rrd.game_targets(root)
    wrong = ["--game-file", "1=" + targets[0][2]]
    code, out = _run(["--dll", dll, "--version", "1.41.0"] + wrong + ["--game-version", "x1", "--dry-run"])
    assert code == rrd.EXIT_REFUSED and "--game-file 1 is Assembly-CSharp-firstpass.dll" in out
    pick = ["--game-file", "8=" + targets[8][2], "--game-file", "0=" + targets[0][2]]
    code, out = _run(["--dll", dll, "--version", "1.41.0"] + pick + ["--dry-run"])
    assert code == rrd.EXIT_REFUSED and "--game-file needs --game-version" in out
    code, out = _run(["--dll", dll, "--version", "1.41.0"] + pick + ["--game-version", "pack.5.4.19", "--dry-run"])
    assert code == rrd.EXIT_OK, out
    assert "game_file id=0  game_version=pack.5.4.19 sha256=%s" % expected[0][1] in out
    assert "game_file id=8  game_version=pack.5.4.19 sha256=%s" % expected[8][1] in out
    assert "DRY RUN  3 rows would be registered" in out


# -- D5: the dry run, and a real run without its environment ---------------------------------

def test_d5_dry_run_prints_every_row_and_sends_nothing(tmp_path, install):
    root, expected = install
    dll, data = _dll(tmp_path)
    rec = _Recorder()
    code, out = _run(_argv(dll, "1.41.0", root, "--variant", "standalone", "--commit", fx.FULL_SHA,
                           "--dry-run"), {}, rec)
    assert code == rrd.EXIT_OK and rec.calls == []
    sha = hashlib.sha256(data).hexdigest()
    assert ("WOULD    release   version=1.41.0 variant=standalone commit=%s dll_sha256=%s source=release"
            % (fx.FULL_SHA[:12], sha)) in out
    assert "signs target 1.41.0|standalone|%s|%s\n" % (fx.FULL_SHA[:12], sha) in out
    for fid, (name, digest) in expected.items():
        assert "game_file id=%-2d game_version=steam.%s sha256=%s  %s" % (fid, fx.BUILD_ID, digest, name) in out
        assert "signs target %d|steam.%s|%s\n" % (fid, fx.BUILD_ID, digest) in out
    assert out.count("WOULD    ") == 18
    assert "ADMIN_HMAC_SECRET is NOT SET" in out
    assert ("DRY RUN  18 rows would be registered; nothing was sent. The real run also needs: "
            "ADMIN_HMAC_SECRET, SCR_API_BASE, --admin.") in out


def test_d5_dry_run_with_the_environment_set_names_no_value(tmp_path, install):
    root, _expected = install
    dll, _data = _dll(tmp_path)
    code, out = _run(_argv(dll, "1.41.0", root, "--admin", _admin(), "--dry-run"),
                     {"ADMIN_HMAC_SECRET": SECRET, "SCR_API_BASE": "http://t"}, _Recorder())
    assert code == rrd.EXIT_OK
    assert "ADMIN_HMAC_SECRET is set (value not printed)" in out and SECRET not in out
    assert "nothing was sent.\n" in out


@pytest.mark.parametrize("environ,admin,missing", [
    ({}, True, "ADMIN_HMAC_SECRET, SCR_API_BASE missing"),
    ({"SCR_API_BASE": "http://t"}, True, "ADMIN_HMAC_SECRET missing"),
    ({"ADMIN_HMAC_SECRET": SECRET}, True, "SCR_API_BASE missing"),
    ({"ADMIN_HMAC_SECRET": SECRET, "SCR_API_BASE": "http://t"}, False, "--admin missing"),
])
def test_d5_a_real_run_without_its_environment_sends_nothing(tmp_path, environ, admin, missing):
    dll, _data = _dll(tmp_path)
    rec = _Recorder()
    code, out = _run(_argv(dll, "1.41.0", None, *(["--admin", _admin()] if admin else [])), environ, rec)
    assert code == rrd.EXIT_ENV and rec.calls == []
    assert "NOT SENT %s; nothing was sent." % missing in out


# -- D6: idempotence of the step's own accounting ---------------------------------------------

class _Server:
    """A recording stand-in for the two routes: it checks the signature the
    way main._verify_admin_hmac does and answers as the inserts do (ON
    CONFLICT DO NOTHING on the primary key). The live routes are
    test_release_digests_pg.py's."""

    def __init__(self, secret, admin):
        self.secret, self.admin, self.rows, self.headers = secret, admin, set(), []

    def __call__(self, url, headers):
        from urllib.parse import parse_qs, urlsplit
        self.headers.append(headers)
        parts = urlsplit(url)
        q = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        if parts.path == rrd.RELEASE_ROUTE:
            action, key = "release_digest", (q["version"], q["variant"], q["commit"], q["dll_sha256"])
            target = "|".join(key) + ("" if q.get("source", "release") == "release" else "|" + q["source"])
        else:
            action, key = "game_file_digest", (int(q["file_id"]), q["game_version"], q["sha256"])
            target = "%d|%s|%s" % key
        expected = hmac.new(self.secret.encode(), ("admin:%s:%s:%s" % (q["admin_steam_id"], action, target)).encode(),
                            hashlib.sha256).hexdigest()
        if q["admin_steam_id"] != self.admin or not hmac.compare_digest(q["hmac_signature"], expected):
            return 403, '{"detail":"Bad admin signature"}'
        new = (parts.path, key) not in self.rows
        self.rows.add((parts.path, key))
        return 200, '{"status":"%s"}' % ("registered" if new else "already_registered")


def test_d6_a_second_run_inserts_nothing_and_says_so(tmp_path, install):
    root, _expected = install
    dll, _data = _dll(tmp_path)
    admin = _admin()
    server = _Server(SECRET, admin)
    env = {"ADMIN_HMAC_SECRET": SECRET, "SCR_API_BASE": "http://t"}
    code, out = _run(_argv(dll, "1.41.0", root, "--admin", admin), env, server)
    assert code == rrd.EXIT_OK and "DONE     18 rows: 18 inserted, 0 already registered." in out
    assert len(server.rows) == 18 and out.count("INSERTED ") == 18
    assert all(h["X-Mod-Version"] == "1.41.0" for h in server.headers)
    code, out = _run(_argv(dll, "1.41.0", root, "--admin", admin), env, server)
    assert code == rrd.EXIT_OK and len(server.rows) == 18
    assert "DONE     18 rows: nothing inserted, every row was already registered." in out
    assert out.count("(already registered)") == 18


def test_d6_a_refused_row_stops_the_run(tmp_path, install):
    root, _expected = install
    dll, _data = _dll(tmp_path)
    server = _Server("another-secret", _admin())
    code, out = _run(_argv(dll, "1.41.0", root, "--admin", server.admin),
                     {"ADMIN_HMAC_SECRET": SECRET, "SCR_API_BASE": "http://t"}, server)
    assert code == rrd.EXIT_SERVER and server.rows == set() and len(server.headers) == 1
    assert "HTTP 403" in out and "Stopped; rows before it stand, a re-run is safe." in out


def test_d6_beta_source_signs_its_source(tmp_path):
    dll, _data = _dll(tmp_path)
    admin = _admin()
    server = _Server(SECRET, admin)
    code, out = _run(_argv(dll, "1.41.0", None, "--admin", admin, "--source", "beta"),
                     {"ADMIN_HMAC_SECRET": SECRET, "SCR_API_BASE": "http://t"}, server)
    assert code == rrd.EXIT_OK and "source=beta" in out and len(server.rows) == 1


# -- D7: the emitted migration ----------------------------------------------------------------

def test_d7_emit_sql_shape_and_no_overwrite(tmp_path, install):
    root, expected = install
    dll, data = _dll(tmp_path)
    target = tmp_path / "fixture_release_digests.sql"
    code, out = _run(_argv(dll, "1.41.0", root, "--emit-sql", str(target)), {}, _Recorder())
    assert code == rrd.EXIT_OK and "WROTE    " in out and "ADMIN_HMAC_SECRET" not in out
    sql = target.read_text(encoding="ascii")
    assert sql.startswith("-- fixture_release_digests.sql: digest registry rows: v1.41.0 standalone commit "
                          "%s; 17 game-file digests under steam.%s." % (fx.FULL_SHA[:12], fx.BUILD_ID))
    statements = [s for s in re.split(r";\s*\n", re.sub(r"--[^\n]*", "", sql)) if s.strip()]
    assert [s.split()[0] for s in statements] == ["BEGIN", "INSERT", "INSERT", "COMMIT"]
    assert sql.count("ON CONFLICT DO NOTHING;") == 2
    assert ("('1.41.0', 'standalone', '%s', '%s', 'release')" % (fx.FULL_SHA[:12], hashlib.sha256(data).hexdigest())
            in sql)
    for fid, (name, digest) in expected.items():
        assert "(%d, 'steam.%s', '%s')" % (fid, fx.BUILD_ID, digest) in sql
    before = target.read_bytes()
    code, out = _run(_argv(dll, "1.41.0", root, "--emit-sql", str(target)))
    assert code == rrd.EXIT_REFUSED and "exists; the writer never replaces a file" in out
    assert target.read_bytes() == before
    code, out = _run(_argv(dll, "1.41.0", root, "--emit-sql", str(tmp_path / "x.txt")))
    assert code == rrd.EXIT_REFUSED and not (tmp_path / "x.txt").exists()


# -- a real Roslyn image, when one is named ----------------------------------------------------

def test_real_dll_when_named():
    path = os.environ.get("RELEASE_DIGESTS_REAL_DLL")
    if not path:
        pytest.skip("RELEASE_DIGESTS_REAL_DLL is not set: no built CompetitiveRounds.dll was named")
    with open(path, "rb") as f:
        data = f.read()
    got = rrd.build_identity(data)
    # An independent reading: the BepInPlugin value blob and the
    # InformationalVersion suffix found by a raw byte search.
    guid = rrd.PLUGIN_GUID.encode()
    m = re.search(re.escape(b"\x01\x00" + bytes([len(guid)]) + guid) + rb"(.)", data, re.S)
    rest = data[m.end(1):]
    name, rest = rest[:m.group(1)[0]], rest[m.group(1)[0]:]
    version = rest[1:1 + rest[0]].decode()
    assert name == b"Competitive ROUNDS" and got["version"] == version
    full = re.findall(rb"\+([0-9a-f]{40})\x00\x00", data)
    assert len(set(full)) == 1 and got["commit"] == full[0].decode()[:12]
    assert got["variant"] == "standalone" and got["dll_sha256"] == hashlib.sha256(data).hexdigest()
    print("real DLL: version %s variant %s commit %s sha256 %s"
          % (got["version"], got["variant"], got["commit"], got["dll_sha256"]))
