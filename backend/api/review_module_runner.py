"""The child side of review_module (choice two; designed, not built).

Started by ModuleSupervisor as `python -I review_module_runner.py <module dir>
<policy>` with an empty environment. It proves its isolation FIRST, then
imports `scr_review_module` from the module directory and answers one JSON
line per request line. It never opens a file of its own accord, never reads
the environment, and holds no database handle.
"""

import json
import os
import sys


def _isolated() -> bool:
    """Not root, no network interface but loopback, an empty environment."""
    if os.name != "posix" or os.getuid() == 0:
        return False
    try:
        interfaces = set(os.listdir("/sys/class/net"))
    except OSError:
        return False
    if interfaces - {"lo"}:
        return False
    return not any(k for k in os.environ if k not in ("LC_CTYPE",))


def _reply(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main(argv):
    module_dir, policy = argv
    if policy != "none" and not _isolated():
        _reply({"error": "policy"})
        return "policy"
    sys.path.insert(0, module_dir)
    import scr_review_module as mod
    for line in sys.stdin:
        req = json.loads(line)
        call = req.get("call")
        if call == "hello":
            _reply({"api": mod.api_version, "measures": dict(mod.measures())})
        elif call == "selftest":
            _reply({"ok": bool(mod.selftest())})
        elif call == "compute":
            _reply({"value": mod.compute(req["name"], req["inputs"], req["params"])})
        else:
            _reply({"error": "call"})
    return None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
