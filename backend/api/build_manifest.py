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
                     this function.
  pip_freeze         `python -m pip freeze --all`, one `name==version` per
                     line, sorted; pip_freeze_sha256 is SHA-256 over those
                     lines joined by newlines with a final newline.
  dpkg               `dpkg-query -W` as `package=version` lines, sorted;
                     dpkg_sha256 likewise.

/health `build_manifest` answers the SHA-256 of the file's exact bytes when
every part is present and each list matches its hash; "absent" when there is no
file (a process not started from a built image: tests, a local run); "refused"
when a part is missing or does not match. Standard library only.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

FORMAT = "scr-build-manifest/1"
PARTS = ("format", "context_digest", "pip_freeze", "pip_freeze_sha256", "dpkg", "dpkg_sha256")
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "build-manifest.json"
CONTEXT_PREFIX = "backend/api/"
_WORD = {}


def list_sha256(lines):
    """SHA-256 over sorted lines joined by newlines, with a final newline."""
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


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


def _lines(command):
    out = subprocess.run(command, capture_output=True, check=True, text=True).stdout
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def collect(root=HERE):
    """The manifest document for the image this process runs in."""
    pip = _lines([sys.executable, "-m", "pip", "freeze", "--all"])
    dpkg = _lines(["dpkg-query", "-W", "-f", "${Package}=${Version}\n"])
    return {"format": FORMAT, "context_digest": context_digest(root),
            "pip_freeze": pip, "pip_freeze_sha256": list_sha256(pip),
            "dpkg": dpkg, "dpkg_sha256": list_sha256(dpkg)}


def encode(document):
    return (json.dumps(document, sort_keys=True, indent=1) + "\n").encode("utf-8")


def problems(document):
    """Every way `document` is not a complete manifest; [] when it is one."""
    if not isinstance(document, dict):
        return ["not an object"]
    found = []
    for part in PARTS:
        if part not in document:
            found.append("missing " + part)
    if found:
        return found
    if document["format"] != FORMAT:
        found.append("format %r" % (document["format"],))
    digest = document["context_digest"]
    if not (isinstance(digest, str) and len(digest) == 64
            and all(c in "0123456789abcdef" for c in digest)):
        found.append("context_digest is not 64 lowercase hex digits")
    for part in ("pip_freeze", "dpkg"):
        lines = document[part]
        if not (isinstance(lines, list) and lines and all(isinstance(x, str) and x for x in lines)):
            found.append(part + " is not a non-empty list of lines")
        elif lines != sorted(lines):
            found.append(part + " is not sorted")
        elif list_sha256(lines) != document[part + "_sha256"]:
            found.append(part + "_sha256 does not match " + part)
    extra = sorted(set(document) - set(PARTS))
    if extra:
        found.append("unknown parts " + ", ".join(extra))
    return found


def word_for(raw):
    """The /health word for manifest file bytes (None: no file)."""
    if raw is None:
        return "absent"
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "refused"
    return "refused" if problems(document) else hashlib.sha256(raw).hexdigest()


def health_word():
    """/health `build_manifest`, read once per process (the file is written
    at image build and never changes in a running container)."""
    if "word" not in _WORD:
        try:
            raw = MANIFEST.read_bytes()
        except FileNotFoundError:
            raw = None
        _WORD["word"] = word_for(raw)
    return _WORD["word"]


def main(argv):
    if argv != ["write"]:
        print("usage: build_manifest.py write", file=sys.stderr)
        return 2
    document = collect()
    found = problems(document)
    if found:
        print("build manifest refused: " + "; ".join(found), file=sys.stderr)
        return 1
    raw = encode(document)
    MANIFEST.write_bytes(raw)
    print("build manifest %s: context %s, %d pip, %d dpkg"
          % (hashlib.sha256(raw).hexdigest(), document["context_digest"],
             len(document["pip_freeze"]), len(document["dpkg"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
