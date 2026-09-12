"""Deployment wiring for the Player Cards face renderer.

The renderer needs six font files that are deliberately NOT in the repository
(gitignored, ~30 MB). Both backend boxes deploy by pulling a git clone and
building the image from it, so a font that only exists on a developer's disk
reaches production as an absence. main.py imports the renderer inside a
try/except, which means that absence does not crash anything: the api boots
normally and every face route answers 503. The feature would ship completely
inert behind clean logs -- the #438/#443 shape.

These tests are the positive signal. They read the real Dockerfile, the real
lock file and the renderer's own font table, and fail if the three ever stop
agreeing.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
API = os.path.join(REPO, "backend", "api")
FONTS = os.path.join(API, "assets", "fonts")
DOCKERFILE = os.path.join(API, "Dockerfile")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _lock():
    with open(os.path.join(FONTS, "fonts.lock.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _renderer_font_values():
    """The font FILE NAMES the renderer asks for, read from its source.

    Read as source text rather than by importing pc_face: this test must fail
    on a machine where the renderer cannot import at all, which is exactly the
    machine the test exists for.
    """
    src = _read(os.path.join(API, "pc_face.py"))
    block = re.search(r"_FONT_FILES\s*=\s*\{(.*?)\}", src, re.S)
    assert block, "pc_face.py no longer defines _FONT_FILES"
    return set(re.findall(r'"([^"]+\.(?:ttf|otf|ttc))"', block.group(1)))


def _fetcher():
    """fetch_fonts.py as a module, loaded from its path."""
    import importlib.util
    path = os.path.join(FONTS, "fetch_fonts.py")
    spec = importlib.util.spec_from_file_location("scr_fetch_fonts", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _serving(payloads):
    """A urlopen stand-in serving `payloads[url]` as a readable response."""
    class _R:
        def __init__(self, data):
            self.data = data

        def read(self, n=-1):
            out, self.data = self.data[:n if n >= 0 else len(self.data)], self.data[n if n >= 0 else len(self.data):]
            return out

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url not in payloads:
            raise AssertionError("fetcher asked for an unpinned url: " + url)
        return _R(payloads[url])
    return urlopen


def test_the_fetcher_actually_downloads_every_locked_font_and_verifies_it(tmp_path, monkeypatch):
    """Reading the Dockerfile's command text proves the step is CALLED. This
    runs it: a fetcher rewritten to exit 0 without downloading anything, or one
    that accepts bytes whose digest does not match the lock, passes every other
    test in this file and leaves the container with no fonts (#465)."""
    import json as _json
    import hashlib as _hashlib
    mod = _fetcher()
    lock = _lock()
    bodies = {name: ("%s-bytes" % name).encode() * 3 for name in lock}
    # a lock that matches the bytes we are about to serve
    fake_lock = {name: {"sha256": _hashlib.sha256(body).hexdigest(), "bytes": len(body),
                        "url": lock[name]["url"]}
                 for name, body in bodies.items()}
    lock_path = tmp_path / "fonts.lock.json"
    lock_path.write_text(_json.dumps(fake_lock), encoding="utf-8")
    monkeypatch.setattr(mod, "HERE", str(tmp_path))
    monkeypatch.setattr(mod, "LOCK", str(lock_path))
    monkeypatch.setattr(mod.urllib.request, "urlopen",
                        _serving({lock[n]["url"]: bodies[n] for n in bodies}))

    assert mod.main([]) == 0
    for name, body in bodies.items():
        assert (tmp_path / name).read_bytes() == body, name   # it really wrote them

    # served bytes that do not match the lock must FAIL, not pass quietly
    for name in list(bodies)[:1]:
        (tmp_path / name).unlink()
        monkeypatch.setattr(mod.urllib.request, "urlopen",
                            _serving({lock[n]["url"]: (b"tampered" if n == name else bodies[n])
                                      for n in bodies}))
        assert mod.main([]) == 1, name

    # a lock that does not list exactly FONTS is refused before any download
    lock_path.write_text(_json.dumps({k: v for k, v in list(fake_lock.items())[:2]}), encoding="utf-8")
    monkeypatch.setattr(mod.urllib.request, "urlopen",
                        _serving({}))       # any request at all would raise
    assert mod.main([]) == 2


def test_the_image_fetches_the_fonts_before_it_copies_the_code():
    """A build that skips the fetch produces an api that 503s every face."""
    df = _read(DOCKERFILE)
    fetch = re.search(r"^RUN .*fetch_fonts\.py.*$", df, re.M)
    assert fetch, ("the Dockerfile has no RUN step that executes "
                   "fetch_fonts.py, so the built image has no fonts")
    copy_lock = re.search(r"^COPY .*fonts\.lock\.json.*$", df, re.M)
    assert copy_lock, "fonts.lock.json is never copied, so the fetch cannot verify"
    copy_all = re.search(r"^COPY \. \.\s*$", df, re.M)
    assert copy_all, "the Dockerfile no longer copies the application code"
    # Order is the point: the lock and the fetch above the code copy keep the
    # 30 MB download in a layer that a code-only rebuild reuses.
    assert copy_lock.start() < fetch.start() < copy_all.start(), (
        "the font fetch must sit between the lock copy and the code copy; "
        "found lock@%d fetch@%d code@%d"
        % (copy_lock.start(), fetch.start(), copy_all.start()))


def test_every_font_the_renderer_asks_for_is_pinned_in_the_lock():
    """A seventh font added to the renderer would be missing in the container."""
    wanted = _renderer_font_values()
    locked = set(_lock())
    assert wanted, "no font file names were found in _FONT_FILES"
    missing = sorted(wanted - locked)
    assert not missing, (
        "pc_face asks for %s, which fonts.lock.json does not pin -- the fetch "
        "would not download them and the container would not have them"
        % ", ".join(missing))


def test_the_fetcher_and_the_lock_name_the_same_fonts():
    """fetch_fonts.py refuses to run when these disagree; fail here instead."""
    src = _read(os.path.join(FONTS, "fetch_fonts.py"))
    block = re.search(r"^FONTS\s*=\s*\{(.*?)^\}", src, re.S | re.M)
    assert block, "fetch_fonts.py no longer defines a FONTS table"
    declared = set(re.findall(r'^\s{4}"([^"]+)":', block.group(1), re.M))
    assert declared == set(_lock()), (
        "fetch_fonts.py fetches %s but the lock pins %s"
        % (sorted(declared), sorted(_lock())))


def test_every_locked_font_carries_a_commit_pinned_url_and_a_digest():
    """A moving branch URL would let two builds of one ref draw differently."""
    for name, entry in sorted(_lock().items()):
        url = entry.get("url", "")
        assert len(entry.get("sha256", "")) == 64, "%s: no sha256 in the lock" % name
        assert isinstance(entry.get("bytes"), int) and entry["bytes"] > 0, (
            "%s: no byte count in the lock" % name)
        assert url.startswith("https://"), "%s: %r is not https" % (name, url)
        # raw.githubusercontent.com/<owner>/<repo>/<ref>/... -- the ref must be
        # a 40-char commit sha, never "main" or a tag that can be moved.
        ref = re.match(r"https://raw\.githubusercontent\.com/[^/]+/[^/]+/([^/]+)/", url)
        assert ref, "%s: %r is not a raw.githubusercontent.com URL" % (name, url)
        assert re.fullmatch(r"[0-9a-f]{40}", ref.group(1)), (
            "%s: pinned to %r, which is not a commit sha -- the bytes behind "
            "this URL can change without the lock changing"
            % (name, ref.group(1)))


def test_the_font_binaries_stay_out_of_the_repository():
    """The whole reason the fetch exists. If they get committed, drop it."""
    ignore = _read(os.path.join(REPO, ".gitignore"))
    for suffix in (".ttf", ".otf", ".ttc"):
        assert "backend/api/assets/fonts/*%s" % suffix in ignore, (
            "%s files under the renderer's font directory are no longer "
            "gitignored" % suffix)

def test_the_image_installs_the_text_shaper_the_renderer_loads_at_runtime():
    """Pillow's wheel bundles libraqm but loads libfribidi at runtime. Without
    the package the renderer runs the basic engine, health reports
    pc_raqm=false and every face route refuses with text_shaping_unavailable
    -- production on 2026-09-12: both boxes healthy, first pack open refused."""
    df = _read(DOCKERFILE)
    apt = re.search(r"^RUN .*apt-get install .*libfribidi0.*$", df, re.M)
    assert apt, "the Dockerfile installs no libfribidi0, so the renderer cannot shape text"
    copy_all = re.search(r"^COPY \. \.\s*$", df, re.M)
    assert copy_all and apt.start() < copy_all.start(), (
        "the shaper layer must sit above the code copy so a code-only rebuild reuses it")
