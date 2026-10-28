"""DSN-free A1 proof using the source constant and rule, without importing the app."""
import ast
from pathlib import Path


def test_readmit_refused_and_sibling_labels_keep_their_values():
    source = (Path(__file__).resolve().parents[1] / "api" / "main.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    labels = next(node for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "_PREROOM_LEAVE_LABELS"
                          for target in node.targets))
    rule = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "_preroom_leave_label")
    assert isinstance(labels.value, ast.Call)
    assert isinstance(labels.value.func, ast.Name) and labels.value.func.id == "frozenset"
    values = frozenset(ast.literal_eval(labels.value.args[0]))
    assert "readmit_refused" in values and len(values) == 22
    assert "22 sites" in ast.get_docstring(rule)
    namespace = {}
    exec(compile(ast.Module(body=[labels, rule], type_ignores=[]),
                 "<pre-room leave label rule>", "exec"), namespace)
    label = namespace["_preroom_leave_label"]
    assert label("readmit_refused") == "readmit_refused"
    assert label("menu_leave") == "menu_leave"
    assert label("not_a_site") == "unlabelled"
    assert label(None) == "unlabelled"
