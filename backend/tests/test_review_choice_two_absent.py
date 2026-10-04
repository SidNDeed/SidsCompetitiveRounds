"""Choice two (a private review module run in its own sandboxed service) is
ABSENT from this build: the server config revision (choice one) is the only
mechanism. Its inside-the-sandbox proof needs a container runtime this seat
does not have, so the service, its image, the runner and the api's exchange
client were removed rather than shipped unproven; the design stays in the
lane's notes as owed.

What this file shows:
  * no file of the backend names the removed service, image, runner, client
    or exchange (a scan with a planted reference as its control);
  * no backend module imports either removed module (an import scan, with a
    planted import as its control);
  * the compose file declares no such service, profile or volume;
  * the health response carries no word for it;
  * a rule naming a measure this build does not define is refused, so no
    revision can reach for one (test_review_rules.py, the unknown-entry test).
"""

import ast
import os
import re
import shutil

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
API = os.path.join(BACKEND, "api")
SELF = os.path.abspath(__file__)

REMOVED_FILES = ("api/review_module.py", "api/review_module_runner.py", "api/Dockerfile.review-module")
REMOVED_MODULES = {"review_module", "review_module_runner"}
# every name the removed mechanism used: modules, service, image, profile,
# volumes, exchange directory, environment key, health word
NAMES = ("review_module", "review-module", "SCR_REVIEW_MODULE_EXCHANGE", "SCR_REVIEW_MODULE_DIR",
         "review_module_runner", "Dockerfile.review-module", "review-module-exchange")
# a name as a whole word: `review_modules` (plural prose) is not the module
_WORD = {n: re.compile(r"(?<![\w-])" + re.escape(n) + r"(?!\w)") for n in NAMES}
TEXT_EXT = (".py", ".yml", ".yaml", ".sh", ".sql", ".txt", ".json", ".cfg", ".ini", ".toml", ".md")


def _text_files(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", ".pytest_cache", "db-backups",
                                                "bot-state", "assets")]
        for n in files:
            p = os.path.join(d, n)
            if os.path.abspath(p) == SELF:
                continue
            if n.endswith(TEXT_EXT) or n.startswith("Dockerfile"):
                yield p


def references(root):
    """Every (file, name) where a backend text file names the removed mechanism."""
    hits = []
    for p in _text_files(root):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for name in NAMES:
            if _WORD[name].search(text):
                hits.append((os.path.relpath(p, root), name))
    return hits


def imports(api_dir):
    """Every (file, module) where an api module imports a removed module."""
    hits = []
    for n in sorted(os.listdir(api_dir)):
        if not n.endswith(".py"):
            continue
        with open(os.path.join(api_dir, n), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module.split(".")[0]]
            hits += [(n, m) for m in mods if m in REMOVED_MODULES]
    return hits


def test_the_removed_files_are_gone():
    for rel in REMOVED_FILES:
        assert not os.path.exists(os.path.join(BACKEND, rel)), rel


def test_no_backend_file_names_the_removed_mechanism():
    assert references(BACKEND) == []


def test_control_a_planted_reference_is_found(tmp_path):
    root = tmp_path / "backend"
    shutil.copytree(API, str(root / "api"), ignore=shutil.ignore_patterns("__pycache__", "assets"))
    assert references(str(root)) == []
    with open(root / "api" / "seat_evidence.py", "a", encoding="utf-8") as f:
        f.write("\n# exchange at /app/private/review-module-exchange/in\n")
    assert references(str(root)) == [(os.path.join("api", "seat_evidence.py"), "review-module"),
                                      (os.path.join("api", "seat_evidence.py"), "review-module-exchange")]


def test_no_api_module_imports_a_removed_module():
    assert imports(API) == []


def test_control_a_planted_import_is_found(tmp_path):
    d = tmp_path / "api"
    d.mkdir()
    shutil.copy(os.path.join(API, "review_rules.py"), str(d))
    assert imports(str(d)) == []
    with open(d / "review_rules.py", "a", encoding="utf-8") as f:
        f.write("\n\ndef _late():\n    from review_module_runner import main  # noqa: F401\n")
    assert imports(str(d)) == [("review_rules.py", "review_module_runner")]


def test_compose_declares_no_module_service_profile_or_volume():
    with open(os.path.join(BACKEND, "docker-compose.yml"), encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    assert "review-module" not in doc["services"]
    assert not any("review-module" in v for v in (doc.get("volumes") or {}))
    for name, svc in doc["services"].items():
        assert "profiles" not in svc, name
        for vol in svc.get("volumes") or []:
            assert "review-module" not in str(vol), (name, vol)


def test_the_health_response_has_no_module_word():
    import sys
    sys.path.insert(0, API)
    import schemas
    assert "review_module" not in schemas.HealthResponse.model_fields
    assert {"review_eval", "review_rules"} <= set(schemas.HealthResponse.model_fields)
