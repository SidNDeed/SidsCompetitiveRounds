"""Install the api image's apt packages from bytes pinned by digest.

`python apt_lock.py install <apt.lock> <work dir> <record>` is the Dockerfile's
apt step (after `apt-get update`). For every line of apt.lock
(`<package> <version> <architecture> <sha256>`) it runs
`apt-get download <package>=<version>` in the work directory, which must be
empty or absent. Then, before dpkg reads anything:

  * the directory must hold exactly the .deb files the lock names
    (`<package>_<version>_<architecture>.deb`, an epoch's ":" written "%3a"
    as apt writes it), no more and no fewer;
  * every file's SHA-256 must be the lock's.

Any difference prints `apt lock refused: ...` and returns 1, and dpkg is never
called. Otherwise `dpkg -i` installs exactly those files, `dpkg-query` must
then report each package at its version and architecture, and the record is
written: one `<package> <version> <architecture> <sha256>` line per installed
file, the SHA-256 taken over the bytes that were handed to dpkg. The .deb
files are removed. build_manifest.py reads the record and compares it with
apt.lock. Standard library only (the base image's Python runs it)."""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

_LINE = re.compile(r"^([a-z0-9][a-z0-9.+-]+) ([0-9A-Za-z.+~:-]+) ([a-z0-9-]+) ([0-9a-f]{64})$")


class Refused(Exception):
    pass


def _run(argv, cwd=None):
    """The one place an external command runs (apt-get, dpkg, dpkg-query)."""
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True, text=True).stdout


def read_lock(text):
    """[(package, version, architecture, sha256)] in file order. A line that
    is not a comment, blank, or exactly that shape refuses; so does a package
    named twice."""
    entries = []
    for number, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE.match(line)
        if not match:
            raise Refused("apt.lock line %d is not '<package> <version> <architecture> <sha256>'" % number)
        entries.append(match.groups())
    names = [e[0] for e in entries]
    if len(set(names)) != len(names):
        raise Refused("apt.lock names a package twice")
    if not entries:
        raise Refused("apt.lock names no package")
    return entries


def deb_name(package, version, arch):
    """The file name `apt-get download` writes for a package."""
    return "%s_%s_%s.deb" % (package, version.replace(":", "%3a"), arch)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fetch_and_verify(entries, work):
    """Download every locked package into `work` and return
    [(package, version, arch, sha256, path)]; Refused on any difference."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise Refused("work directory %s is not empty" % work)
    for package, version, _arch, _sha in entries:
        _run(["apt-get", "download", "%s=%s" % (package, version)], cwd=str(work))
    expected = {deb_name(p, v, a): (p, v, a, s) for p, v, a, s in entries}
    present = sorted(path.name for path in work.iterdir())
    if present != sorted(expected):
        raise Refused("downloaded %s, apt.lock names %s" % (present, sorted(expected)))
    verified = []
    for name in sorted(expected):
        package, version, arch, want = expected[name]
        path = work / name
        if path.is_symlink() or not path.is_file():
            raise Refused("%s is not a regular file" % name)
        got = sha256_file(path)
        if got != want:
            raise Refused("%s has sha256 %s, apt.lock says %s" % (name, got, want))
        verified.append((package, version, arch, got, path))
    return verified


def install(lock_path, work, record):
    entries = read_lock(Path(lock_path).read_text(encoding="utf-8"))
    verified = fetch_and_verify(entries, work)
    # Re-hash immediately before dpkg reads the files: what is recorded is the
    # bytes dpkg was given.
    for package, _v, _a, sha, path in verified:
        if sha256_file(path) != sha:
            raise Refused("%s changed after verification" % path.name)
    _run(["dpkg", "-i"] + [str(path) for *_rest, path in verified])
    for package, version, arch, _sha, _path in verified:
        shown = _run(["dpkg-query", "-W", "-f", "${Version} ${Architecture}", package]).strip()
        if shown != "%s %s" % (version, arch):
            raise Refused("dpkg reports %s as %r after install" % (package, shown))
    record = Path(record)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text("".join("%s %s %s %s\n" % (p, v, a, s) for p, v, a, s, _path in verified),
                      encoding="utf-8")
    for *_rest, path in verified:
        path.unlink()
    return verified


def main(argv):
    if len(argv) != 4 or argv[0] != "install":
        print("usage: apt_lock.py install <apt.lock> <work dir> <record>", file=sys.stderr)
        return 2
    try:
        verified = install(argv[1], argv[2], argv[3])
    except Refused as refusal:
        print("apt lock refused: %s" % refusal, file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as failed:
        print("apt lock refused: %s exited %d: %s"
              % (" ".join(failed.cmd), failed.returncode, (failed.stderr or "").strip()), file=sys.stderr)
        return 1
    for package, version, arch, sha, _path in verified:
        print("apt lock installed %s %s %s sha256 %s" % (package, version, arch, sha))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
