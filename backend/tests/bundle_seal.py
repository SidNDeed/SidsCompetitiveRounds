"""Seal a review bundle: the file list, one sha256 each, and nothing else.

WHY THIS EXISTS
  A privacy sweep proves something about the files it read, at the moment it
  read them. Round 2 swept twelve artifacts and reported no hits; the log that
  RECORDED that sweep was the thirteenth artifact, written afterwards, and no
  sweep had ever read it. The gap is not a missed file. It is an ordering
  problem that reappears every round: the evidence is produced last, so the
  last thing produced is never covered by the evidence.

  The order that closes it is: assemble, then sweep EVERYTHING INCLUDING THE
  SWEEP'S OWN LOG, then seal. The seal is what makes "nothing was added after
  the sweep" checkable rather than asserted, and it has to live OUTSIDE the
  bundle -- a seal inside the set it seals cannot record its own hash.

WHAT A SEAL MAY CONTAIN
  File names, sha256 values, and counts. Nothing else, ever. The seal is an
  artifact like any other and would otherwise need sweeping in its turn, which
  is the regress this is here to stop. Names and hashes cannot carry protected
  content, so the seal is safe BY CONSTRUCTION rather than by having been
  checked.

WHAT VERIFICATION CATCHES
  A file in the bundle that the seal does not name -- something added after the
  sweep. A file the seal names that is gone. A file whose sha256 moved -- the
  same name carrying different bytes. All three are failures; none of them can
  be argued away, because the seal was written before any of them happened.

  And a FOURTH: a seal verified under a name it does not carry. The round-3
  seal log wrote the seal to one path and verified another; both files existed
  and were byte-identical, so every verdict in it was true and none of them
  could be traced to the artifact the section above had produced. The defect
  was traceability, and the answer to a traceability defect is not a promise to
  be careful next time (#302). A seal records the file name it was WRITTEN as,
  inside the body its own hash covers, and verification requires that name to
  be the name it was read from. A copy under another name refuses; the file it
  was written as verifies.

Usage:

    python backend/tests/bundle_seal.py --bundle <dir> --write <seal file>
    python backend/tests/bundle_seal.py --bundle <dir> --verify <seal file>
    python backend/tests/bundle_seal.py --self-test

Exit codes: 0 sealed or verified, 1 verification failed, 2 an input was
unusable or the self-test failed.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

_HEADER = "# bundle seal — file names, sha256 values and counts only"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(bundle: Path) -> dict[str, str]:
    """{path relative to the bundle: sha256}, every file, recursively.

    Recursive and unfiltered on purpose. A seal that skipped a subdirectory
    would be a seal with a hole exactly where a file could be added (#441).
    """
    out = {}
    for p in sorted(bundle.rglob("*")):
        if p.is_file():
            out[p.relative_to(bundle).as_posix()] = digest(p)
    return out


def render(inv: dict[str, str], bundle_name: str, seal_name: str) -> str:
    """The seal text, naming the bundle, the count, the files AND ITSELF.

    A file name is exactly what a seal is allowed to carry, so recording its
    own costs nothing and makes the seal traceable to the step that wrote it.
    It sits above the `seal-sha256` line, so the seal's own hash covers it and
    the name cannot be edited afterwards without the hash refusing.
    """
    lines = [_HEADER, f"bundle: {bundle_name}", f"seal-file: {seal_name}",
             f"files: {len(inv)}"]
    lines += [f"{sha}  {rel}" for rel, sha in sorted(inv.items())]
    body = "\n".join(lines)
    # The seal's own fingerprint, over the lines above it, so a seal edited
    # after the fact does not read as the one that was written.
    return body + "\n" + f"seal-sha256: {hashlib.sha256(body.encode('utf-8')).hexdigest()}\n"


def parse(text: str) -> tuple[dict[str, str], str | None, bool, str | None]:
    """(inventory, recorded digest, whether the body hashes, seal file name)."""
    inv: dict[str, str] = {}
    body_lines: list[str] = []
    recorded = None
    seal_name = None
    for line in text.splitlines():
        if line.startswith("seal-sha256: "):
            recorded = line.split(": ", 1)[1].strip()
            continue
        if line.startswith("seal-file: "):
            seal_name = line.split(": ", 1)[1].strip()
        body_lines.append(line)
        parts = line.split("  ", 1)
        if len(parts) == 2 and len(parts[0]) == 64 and all(
                c in "0123456789abcdef" for c in parts[0]):
            inv[parts[1]] = parts[0]
    body = "\n".join(body_lines)
    intact = recorded is not None and \
        hashlib.sha256(body.encode("utf-8")).hexdigest() == recorded
    return inv, recorded, intact, seal_name


def compare(sealed: dict[str, str], live: dict[str, str]) -> list[str]:
    bad = []
    for rel in sorted(set(live) - set(sealed)):
        bad.append(f"ADDED AFTER THE SEAL: {rel}")
    for rel in sorted(set(sealed) - set(live)):
        bad.append(f"SEALED BUT ABSENT: {rel}")
    for rel in sorted(set(sealed) & set(live)):
        if sealed[rel] != live[rel]:
            bad.append(f"BYTES MOVED SINCE THE SEAL: {rel}")
    return bad


def name_mismatch(recorded: str | None, read_as: str) -> list[str]:
    """Complaints when a seal is verified under a name it does not carry."""
    if recorded is None:
        return ["THE SEAL NAMES NO FILE OF ITS OWN: it cannot be traced to the "
                "step that wrote it"]
    if recorded != read_as:
        return [f"SEAL NAME MISMATCH: this file is {read_as}, the seal was "
                f"written as {recorded} -- the verification below would not be "
                "about the artifact the sealing step produced"]
    return []


def _self_test() -> int:
    """Plant each shape verification must separate, and the twin that must not fire."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        bundle = Path(td) / "bundle"
        (bundle / "sub").mkdir(parents=True)
        (bundle / "a.txt").write_text("alpha\n", encoding="utf-8")
        (bundle / "sub" / "b.txt").write_text("beta\n", encoding="utf-8")
        inv = inventory(bundle)
        seal_text = render(inv, "bundle", "the-seal.txt")
        sealed, _rec, intact, seal_name = parse(seal_text)

        checks = {
            "the seal names every file, subdirectories included": set(sealed) == {
                "a.txt", "sub/b.txt"},
            "the seal's own body hashes back": intact,
            "a sealed bundle verifies clean": not compare(sealed, inventory(bundle)),
        }
        # INERT TWIN: re-stamp a file with its own bytes. Nothing moved.
        (bundle / "a.txt").write_text("alpha\n", encoding="utf-8")
        checks["re-writing identical bytes stays green"] = \
            not compare(sealed, inventory(bundle))
        # MUTATION: a file added after the seal.
        (bundle / "late.txt").write_text("added later\n", encoding="utf-8")
        added = compare(sealed, inventory(bundle))
        checks["a file added after the seal is caught"] = \
            any(c.startswith("ADDED AFTER THE SEAL: late.txt") for c in added)
        (bundle / "late.txt").unlink()
        # MUTATION: the bytes of a sealed file change.
        (bundle / "a.txt").write_text("alpha changed\n", encoding="utf-8")
        checks["a sealed file whose bytes moved is caught"] = \
            any(c.startswith("BYTES MOVED SINCE THE SEAL: a.txt")
                for c in compare(sealed, inventory(bundle)))
        (bundle / "a.txt").write_text("alpha\n", encoding="utf-8")
        # MUTATION: a sealed file removed.
        (bundle / "sub" / "b.txt").unlink()
        checks["a sealed file that is gone is caught"] = \
            any(c.startswith("SEALED BUT ABSENT: sub/b.txt")
                for c in compare(sealed, inventory(bundle)))
        # MUTATION: the seal text itself edited after writing.
        tampered = seal_text.replace("alpha", "alpha")  # no-op: the twin
        checks["an untouched seal text still hashes back"] = parse(tampered)[2]
        broken = seal_text.replace("files: 2", "files: 3")
        checks["a seal edited after writing does not hash back"] = not parse(broken)[2]
        # The traceability shape. MUTATION: the seal read under another name.
        # INERT TWIN at the same site: read under the name it was written as.
        checks["a seal records the name it was written as"] = \
            seal_name == "the-seal.txt"
        checks["a seal read under ANOTHER name is caught"] = \
            bool(name_mismatch(seal_name, "a-copy-of-the-seal.txt"))
        checks["the same seal read under its OWN name is green"] = \
            not name_mismatch(seal_name, "the-seal.txt")
        checks["a seal carrying no name of its own is caught"] = \
            bool(name_mismatch(None, "the-seal.txt"))
        # ...and the name is inside what the seal's hash covers, so it cannot
        # be edited to match afterwards.
        renamed = seal_text.replace("seal-file: the-seal.txt",
                                    "seal-file: a-copy-of-the-seal.txt")
        checks["editing the recorded name breaks the seal's own hash"] = \
            not parse(renamed)[2]
        # A seal may carry names, hashes and counts and nothing longer.
        checks["the seal carries only names, hashes and counts"] = all(
            line.startswith(("#", "bundle:", "files:", "seal-file: ",
                             "seal-sha256: "))
            or (len(line.split("  ", 1)) == 2 and len(line.split("  ", 1)[0]) == 64)
            for line in seal_text.splitlines())
    for k, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {k}")
    bad = [k for k, ok in checks.items() if not ok]
    print("SELF-TEST:", "every shape separated" if not bad else f"FAILED: {bad}")
    return 2 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bundle", type=Path)
    ap.add_argument("--write", type=Path)
    ap.add_argument("--verify", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.bundle or not args.bundle.is_dir():
        ap.error("--bundle must name a directory, or give --self-test")
    if args.write:
        if args.write.resolve().is_relative_to(args.bundle.resolve()):
            print("REFUSING: the seal would live inside the set it seals.")
            return 2
        inv = inventory(args.bundle)
        args.write.write_text(render(inv, args.bundle.name, args.write.name),
                              encoding="utf-8", newline="\n")
        print(f"bundle : {args.bundle.name}")
        print(f"sealed : {len(inv)} files")
        print(f"seal   : {args.write.name}")
        for rel, sha in sorted(inv.items()):
            print(f"  {sha}  {rel}")
        print("SEAL: written")
        return 0
    if args.verify:
        if not args.verify.is_file():
            print(f"REFUSING: not a file: {args.verify.name}")
            return 2
        sealed, recorded, intact, seal_name = parse(
            args.verify.read_text(encoding="utf-8"))
        live = inventory(args.bundle)
        bad = compare(sealed, live)
        bad = name_mismatch(seal_name, args.verify.name) + bad
        if not intact:
            bad.insert(0, "THE SEAL ITSELF DOES NOT HASH BACK: it was edited after writing"
                       if recorded else "THE SEAL CARRIES NO seal-sha256 LINE")
        print(f"bundle : {args.bundle.name}")
        # The file this verdict is ABOUT, printed beside the verdict, so a log
        # section cannot present a green whose subject the reader must infer.
        print(f"seal   : {args.verify.name} (written as {seal_name})")
        print(f"sealed : {len(sealed)} files; live: {len(live)} files")
        for line in bad:
            print(line)
        print("VERIFY:", "the bundle is exactly what was sealed" if not bad
              else f"{len(bad)} discrepancies")
        return 1 if bad else 0
    ap.error("give --write or --verify")


if __name__ == "__main__":
    sys.exit(main())
