"""The api image's build manifest: what this image was built from, written
once by the image build and answered on /api/v1/health as `build_manifest`.

`python build_manifest.py write` is the Dockerfile's last step (after the code
copy and the font verification). It writes build-manifest.json beside this
file, JSON with sorted keys, holding every part of PARTS:

  format             FORMAT.
  context_digest     SHA-256 over the build context exactly as this image
                     received it: every file under this directory except the
                     build's own outputs (the fonts fonts.lock.json names, and
                     the manifest itself), each path given as backend/api/<path>,
                     sorted, each file framed as an 8-byte big-endian path
                     length, the UTF-8 path, an 8-byte big-endian content
                     length, the content. That is the framing the route
                     manifest gate (backend/tests/test_route_manifest_net_seat.py)
                     uses; over the context's members alone it is the gate's
                     context digest, which the gate prints and checks against
                     this function. requirements.lock and apt.lock are members.
  python             one line per installed Python distribution, sorted:
                     `<name>==<version> wheel=<sha256> record=<sha256>`.
                     `wheel` is the SHA-256 of the archive pip verified and
                     installed, read from the build's `pip install --report`
                     (PIP_REPORT), or `base` for a distribution the base image
                     supplied (pip itself), which no build step installed.
                     `record` is the SHA-256 of the distribution's RECORD file
                     (pip's list of every installed file with its own
                     SHA-256); every RECORD row inside the distribution's site
                     directory is re-hashed against the file on disk when the
                     manifest is written, and a difference refuses.
  apt                one line per installed dpkg package, sorted:
                     `<package>=<version>:<architecture> deb=<sha256>`, where
                     `deb` is the SHA-256 of the .deb file dpkg was given, read
                     from apt_lock.py's record (APT_RECORD), or `base` for a
                     package the base image (pinned by its registry digest)
                     already carried, which no build step installed.
  python_sha256, apt_sha256
                     SHA-256 over that part's lines joined by newlines with a
                     final newline.

VALIDATION (`problems`) compares the identities with the locks, not only with
themselves: the distributions with a `wheel` hash must be EXACTLY
requirements.lock (each name, version and its one hash; a lock line with any
other number of hashes is itself a problem) and no locked name may be `base`;
the packages with a `deb` hash must be EXACTLY apt.lock (package, version,
architecture, SHA-256) and no locked package may be `base`. So a substituted
artifact -- another wheel of a locked version, a same-version .deb with other
bytes -- changes the manifest's bytes AND fails validation.

/health `build_manifest` answers the SHA-256 of the file's exact bytes when
every part is present, each list matches its hash and the identities match
the locks this image carries; "absent" when there is no file (a process not
started from a built image: tests, a local run); "refused" otherwise. The
word is therefore derived from the validated identities. Standard library
only.
"""
import base64
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

FORMAT = "scr-build-manifest/2"
PARTS = ("format", "context_digest", "python", "python_sha256", "apt", "apt_sha256")
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "build-manifest.json"
REQUIREMENTS_LOCK = HERE / "requirements.lock"
APT_LOCK = HERE / "apt.lock"
# Written by the build OUTSIDE /app, so the code copy can never replace them.
PIP_REPORT = Path("/var/lib/scr-build/pip-report.json")
APT_RECORD = Path("/var/lib/scr-build/apt-installed.lock")
CONTEXT_PREFIX = "backend/api/"
BASE = "base"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_PY_LINE = re.compile(r"^([a-z0-9-]+)==(\S+) wheel=(base|[0-9a-f]{64}) record=([0-9a-f]{64})$")
_APT_LINE = re.compile(r"^([a-z0-9][a-z0-9.+-]+)=(\S+):([a-z0-9-]+) deb=(base|[0-9a-f]{64})$")
_WORD = {}


class Refused(Exception):
    pass


def list_sha256(lines):
    """SHA-256 over sorted lines joined by newlines, with a final newline."""
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def norm(name):
    """A distribution name as PEP 503 compares it."""
    return re.sub(r"[-_.]+", "-", name).lower()


def framed(files):
    """The gate's framing over [(path, bytes)], sorted by path."""
    ordered = sorted(files)
    paths = [path for path, _data in ordered]
    if len(set(paths)) != len(paths):
        raise ValueError("a path occurs twice")
    out = bytearray()
    for path, data in ordered:
        raw = path.encode("utf-8")
        out += len(raw).to_bytes(8, "big") + raw + len(data).to_bytes(8, "big") + data
    return bytes(out)


def build_outputs(root):
    """Paths under `root`, relative, that the build writes itself."""
    lock = json.loads((root / "assets" / "fonts" / "fonts.lock.json").read_text(encoding="utf-8"))
    return {"assets/fonts/" + name for name in lock} | {MANIFEST.name}


def context_files(root):
    """[(backend/api/<path>, bytes)] for every regular file under `root` that
    the build did not write. Anything else under `root` -- a link, a socket --
    raises: the image's context holds regular files only."""
    root = Path(root)
    skip = build_outputs(root)
    files = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            if rel in skip:
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError("not a regular file: %s" % rel)
            files.append((CONTEXT_PREFIX + rel, path.read_bytes()))
    return files


def context_digest(root):
    return hashlib.sha256(framed(context_files(root))).hexdigest()


# -- the locks ----------------------------------------------------------------

def requirements_locked(text):
    """{name: (version, [sha256...])} from requirements.lock's text."""
    joined = re.sub(r"\\\n", " ", text.replace("\r\n", "\n"))
    locked = {}
    for line in joined.split("\n"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        head, *options = line.split()
        name, _sep, version = head.partition("==")
        hashes = [o[len("--hash=sha256:"):] for o in options if o.startswith("--hash=sha256:")]
        if not version or len(hashes) != len(options) or norm(name) in locked:
            raise Refused("requirements.lock line is not one pinned, hashed package: %r" % line)
        locked[norm(name)] = (version, hashes)
    return locked


def apt_locked(text):
    """{package: (version, arch, sha256)} from apt.lock's text (apt_lock.py's
    reading, repeated here so this module stays standalone)."""
    locked = {}
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 4 or not _HEX.match(fields[3]) or fields[0] in locked:
            raise Refused("apt.lock line is not '<package> <version> <architecture> <sha256>': %r" % line)
        locked[fields[0]] = (fields[1], fields[2], fields[3])
    return locked


# -- what the image installed -------------------------------------------------

def report_wheels(report):
    """{(name, version): sha256} for every archive pip's installation report
    says it verified and installed."""
    document = json.loads(Path(report).read_text(encoding="utf-8"))
    wheels = {}
    for item in document.get("install", []):
        meta = item["metadata"]
        archive = item.get("download_info", {}).get("archive_info", {})
        digest = archive.get("hashes", {}).get("sha256")
        if digest is None and str(archive.get("hash", "")).startswith("sha256="):
            digest = archive["hash"][len("sha256="):]
        if not (isinstance(digest, str) and _HEX.match(digest)):
            raise Refused("pip's report carries no sha256 for %s" % meta.get("name"))
        key = (norm(meta["name"]), meta["version"])
        if key in wheels:
            raise Refused("pip's report installs %s==%s twice" % key)
        wheels[key] = digest
    return wheels


def verify_record(dist, site):
    """Re-hash every RECORD row of `dist` whose path lies inside `site` (the
    directory its modules import from); rows outside it (console scripts in
    a bin directory) are covered by the RECORD digest only. Every row inside
    `site` must carry a SHA-256, except the RECORD file's own row and the
    `__pycache__/*.pyc` bytecode pip compiles at install (which it lists
    without one: not re-hashed). Returns the RECORD file's bytes."""
    text = dist.read_text("RECORD")
    if text is None:
        raise Refused("%s has no RECORD" % dist.metadata["Name"])
    site = Path(site).resolve()
    for row in csv.reader(text.splitlines()):
        if not row:
            continue
        path = Path(dist.locate_file(row[0])).resolve()
        if site not in path.parents:
            continue
        if row[0].endswith(".dist-info/RECORD"):
            continue
        algorithm, _sep, want = (row[1] if len(row) > 1 else "").partition("=")
        if not algorithm and "/__pycache__/" in "/" + row[0] and row[0].endswith(".pyc"):
            # Bytecode pip compiled at install from the verified sources; pip
            # lists it without a hash, so nothing here can compare it.
            continue
        if algorithm != "sha256" or not path.is_file():
            raise Refused("%s RECORD row %s: %s" % (dist.metadata["Name"], row[0],
                                                     "file missing" if algorithm == "sha256"
                                                     else "no sha256 (%r)" % (algorithm,)))
        got = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).rstrip(b"=").decode()
        if got != want:
            raise Refused("%s file %s does not match its RECORD" % (dist.metadata["Name"], row[0]))
    return text.encode("utf-8")


def python_lines(site_paths=None, report=PIP_REPORT):
    """The `python` part: every distribution on `site_paths` (default: this
    interpreter's sys.path), each joined with the wheel pip verified."""
    from importlib import metadata
    wheels = report_wheels(report)
    lines, seen = [], set()
    for dist in metadata.distributions(**({} if site_paths is None else {"path": list(site_paths)})):
        name, version = norm(dist.metadata["Name"]), dist.version
        if name in seen:
            raise Refused("distribution %s is installed twice" % name)
        seen.add(name)
        record = hashlib.sha256(verify_record(dist, dist.locate_file(""))).hexdigest()
        wheel = wheels.pop((name, version), BASE)
        lines.append("%s==%s wheel=%s record=%s" % (name, version, wheel, record))
    if wheels:
        raise Refused("pip's report installed %s, which is not on the path"
                      % ", ".join("%s==%s" % k for k in sorted(wheels)))
    return sorted(lines)


def _dpkg_installed():
    out = subprocess.run(["dpkg-query", "-W", "-f",
                          "${db:Status-Abbrev}|${Package}=${Version}:${Architecture}\n"],
                         capture_output=True, check=True, text=True).stdout
    return [line.split("|", 1)[1].strip() for line in out.splitlines()
            if line.startswith("ii") and "|" in line]


def apt_lines(dpkg=None, record=APT_RECORD):
    """The `apt` part: every installed dpkg package (`dpkg`, default from
    dpkg-query), each joined with the .deb SHA-256 apt_lock.py recorded."""
    installed = _dpkg_installed() if dpkg is None else list(dpkg)
    debs = {}
    for line in Path(record).read_text(encoding="utf-8").splitlines():
        if line.strip():
            package, version, arch, digest = line.split()
            debs["%s=%s:%s" % (package, version, arch)] = digest
    lines = ["%s deb=%s" % (item, debs.pop(item, BASE)) for item in installed]
    if debs:
        raise Refused("apt_lock.py recorded %s, which dpkg does not list" % ", ".join(sorted(debs)))
    return sorted(lines)


def collect(root=HERE, site_paths=None, report=PIP_REPORT, dpkg=None, record=APT_RECORD):
    """The manifest document for the image this process runs in."""
    python = python_lines(site_paths, report)
    apt = apt_lines(dpkg, record)
    return {"format": FORMAT, "context_digest": context_digest(root),
            "python": python, "python_sha256": list_sha256(python),
            "apt": apt, "apt_sha256": list_sha256(apt)}


def encode(document):
    return (json.dumps(document, sort_keys=True, indent=1) + "\n").encode("utf-8")


# -- validation ---------------------------------------------------------------

def _locks():
    return (REQUIREMENTS_LOCK.read_text(encoding="utf-8"), APT_LOCK.read_text(encoding="utf-8"))


def identity_problems(document, requirements_text, apt_text):
    """Every way the manifest's identities differ from the locks."""
    try:
        pylock = requirements_locked(requirements_text)
        aptlock = apt_locked(apt_text)
    except Refused as refusal:
        return [str(refusal)]
    found = ["requirements.lock locks %s==%s to %d artifacts, not one" % (name, version, len(hashes))
             for name, (version, hashes) in sorted(pylock.items()) if len(hashes) != 1]
    installed = {}
    for line in document["python"]:
        match = _PY_LINE.match(line)
        if not match:
            found.append("python line %r is not '<name>==<version> wheel=<sha256|base> record=<sha256>'" % line)
            continue
        installed[match.group(1)] = (match.group(2), match.group(3))
    for name, (version, hashes) in sorted(pylock.items()):
        got = installed.get(name)
        if got is None:
            found.append("%s==%s is locked but not installed" % (name, version))
        elif got[1] == BASE:
            found.append("%s is locked but installed without a verified wheel" % name)
        elif len(hashes) != 1 or got != (version, hashes[0]):
            found.append("%s installed as %s from wheel %s; requirements.lock locks %s to %s"
                         % (name, got[0], got[1], version, ",".join(hashes)))
    for name, (version, wheel) in sorted(installed.items()):
        if wheel != BASE and name not in pylock:
            found.append("%s==%s installed from wheel %s, which requirements.lock does not name"
                         % (name, version, wheel))
    debs = {}
    for line in document["apt"]:
        match = _APT_LINE.match(line)
        if not match:
            found.append("apt line %r is not '<package>=<version>:<arch> deb=<sha256|base>'" % line)
            continue
        debs[match.group(1)] = (match.group(2), match.group(3), match.group(4))
    for package, (version, arch, digest) in sorted(aptlock.items()):
        got = debs.get(package)
        if got is None:
            found.append("%s %s is locked but not installed" % (package, version))
        elif got[2] == BASE:
            found.append("%s is locked but installed without a verified .deb" % package)
        elif got != (version, arch, digest):
            found.append("%s installed as %s:%s from .deb %s; apt.lock locks %s:%s to %s"
                         % (package, got[0], got[1], got[2], version, arch, digest))
    for package, (version, arch, digest) in sorted(debs.items()):
        if digest != BASE and package not in aptlock:
            found.append("%s=%s:%s installed from .deb %s, which apt.lock does not name"
                         % (package, version, arch, digest))
    return found


def problems(document, locks=None):
    """Every way `document` is not a complete manifest whose identities are
    the locks' (`locks`: (requirements.lock text, apt.lock text), default
    the files beside this module); [] when it is one."""
    if not isinstance(document, dict):
        return ["not an object"]
    found = ["missing " + part for part in PARTS if part not in document]
    if found:
        return found
    if document["format"] != FORMAT:
        found.append("format %r" % (document["format"],))
    digest = document["context_digest"]
    if not (isinstance(digest, str) and _HEX.match(digest)):
        found.append("context_digest is not 64 lowercase hex digits")
    lists_ok = True
    for part in ("python", "apt"):
        lines = document[part]
        if not (isinstance(lines, list) and lines and all(isinstance(x, str) and x for x in lines)):
            found.append(part + " is not a non-empty list of lines")
            lists_ok = False
        elif lines != sorted(set(lines)):
            found.append(part + " is not sorted and unique")
        elif list_sha256(lines) != document[part + "_sha256"]:
            found.append(part + "_sha256 does not match " + part)
    extra = sorted(set(document) - set(PARTS))
    if extra:
        found.append("unknown parts " + ", ".join(extra))
    if lists_ok:
        try:
            requirements_text, apt_text = _locks() if locks is None else locks
        except OSError as error:
            return found + ["a lock is unreadable: %s" % error]
        found += identity_problems(document, requirements_text, apt_text)
    return found


def word_for(raw, locks=None):
    """The /health word for manifest file bytes (None: no file)."""
    if raw is None:
        return "absent"
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "refused"
    return "refused" if problems(document, locks) else hashlib.sha256(raw).hexdigest()


def health_word():
    """/health `build_manifest`, read once per process (the file is written
    at image build and never changes in a running container)."""
    if "word" not in _WORD:
        try:
            raw = MANIFEST.read_bytes()
        except FileNotFoundError:
            raw = None
        except OSError:
            # present but unreadable (a permission, a directory in its place): the
            # word is refused, never an error escaping into /health
            raw = b""
        _WORD["word"] = word_for(raw)
    return _WORD["word"]


def main(argv):
    if argv != ["write"]:
        print("usage: build_manifest.py write", file=sys.stderr)
        return 2
    try:
        document = collect()
    except (Refused, OSError, ValueError, subprocess.CalledProcessError) as refusal:
        print("build manifest refused: %s" % refusal, file=sys.stderr)
        return 1
    found = problems(document)
    if found:
        print("build manifest refused: " + "; ".join(found), file=sys.stderr)
        return 1
    raw = encode(document)
    MANIFEST.write_bytes(raw)
    print("build manifest %s: context %s, %d python (%d from verified wheels), %d apt (%d from verified .debs)"
          % (hashlib.sha256(raw).hexdigest(), document["context_digest"], len(document["python"]),
             sum(" wheel=base " not in line for line in document["python"]), len(document["apt"]),
             sum(not line.endswith(" deb=base") for line in document["apt"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
