"""Build-time check: the api image holds no loadable bytecode cache.

The review closure modules execute only from their source bytes
(review_boot.py), so no cache can run in their place. Every module the
interpreter imports BEFORE review_boot is installed -- review_boot itself,
main.py and whatever main imports first -- is loaded by the ordinary import
system, which runs a valid bytecode cache when one exists; nothing at run time
can prove which bytes ran for those. The image therefore must contain no
cache: the build context excludes every cache (.dockerignore), the image
writes none (PYTHONDONTWRITEBYTECODE), and the Dockerfile runs this check
after the code copy, failing the build if any exists.

  python -B build_no_bytecode.py <root>

Exit 0 when no __pycache__ directory and no .pyc or .pyo file exists under
<root>; 1 when any does (the count is printed, never a name or a byte); 2 on
usage or a directory that cannot be read (never read as "none found").
"""

from __future__ import annotations

import os
import sys


def _raise(e):
    raise e


def caches(root: str) -> int:
    """How many cache directories and cache files exist under root."""
    n = 0
    for _top, dirs, files in os.walk(root, onerror=_raise):
        n += sum(1 for d in dirs if d == "__pycache__")
        n += sum(1 for f in files if f.endswith((".pyc", ".pyo")))
    return n


def main(argv) -> int:
    if len(argv) != 1 or not os.path.isabs(argv[0]):
        print("usage: python -B build_no_bytecode.py <absolute root>")
        return 2
    try:
        n = caches(argv[0])              # a missing or non-directory root raises here
    except OSError as e:
        print("build_no_bytecode: unreadable (%s): refused" % type(e).__name__)
        return 2
    if n:
        print("build_no_bytecode: %d bytecode cache entr%s in the image: refused" % (n, "y" if n == 1 else "ies"))
        return 1
    print("build_no_bytecode: no bytecode cache")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
