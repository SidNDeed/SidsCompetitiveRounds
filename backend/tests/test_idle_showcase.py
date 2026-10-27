"""Board row 31: the broadcast idle showcase walks every Compare tab category.

The rotation itself - every metric in list order with one dwell each, the
other views' places and dwells, the skip rule and the log line - is
ShowcaseRules, EXECUTED by tools/client-rules-harness
(test_client_rules_harness.py, suite "showcase"). These pins hold the wiring
the harness cannot compile: the showcase builds that rotation from the
Compare tab's own array, logs every metric it shows, reads its dwell from a
config key whose default is the rules' default, and the witness lever lifts
the stream-live gate and nothing else.
"""
import re
from pathlib import Path

from _cs_structure import method_spans, strip_comments_only

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
SHOWCASE = PLUGIN / "IdleShowcase.cs"


def _body(path, signature):
    spans = list(method_spans(path, signature))
    assert len(spans) == 1, f"expected one block for {signature}, found {len(spans)}"
    open_brace, end = spans[0]
    return strip_comments_only(path.read_text(encoding="utf-8")[open_brace:end])


def _code(path):
    return strip_comments_only(path.read_text(encoding="utf-8"))


def _compare_metrics():
    m = re.search(r"private static readonly string\[\] COMPARE_METRICS = \{(.*?)\};",
                  _code(PLUGIN / "NativeUI.cs"), re.S)
    assert m, "COMPARE_METRICS not found"
    return re.findall(r'"([^"]*)"', m.group(1))


def test_the_compare_tab_lists_34_distinct_metrics():
    """The count the harness case and the witness are measured against. The
    array's comments quote old metric names; strip_comments_only blanks them,
    so only the entries are counted."""
    names = _compare_metrics()
    assert len(names) == 34, names
    assert len(set(names)) == 34, "a metric name repeats"
    assert names[0] == "Elo", "the Compare setup view is the first metric"


def test_the_showcase_walks_the_compare_tabs_own_array():
    code = _code(PLUGIN / "NativeUI.cs")
    assert "internal static string[] CompareMetricNames => (string[])COMPARE_METRICS.Clone();" in code
    showcase = _code(SHOWCASE)
    assert "CURATED_METRICS" not in showcase and "SCRIPT" not in showcase, (
        "the curated list or the fixed script is back")
    begin = _body(SHOWCASE, "private static void BeginRotation()")
    assert "metrics = NativeUI.CompareMetricNames;" in begin
    assert "script = ShowcaseRules.Script(metrics, MetricSecondsConfigured());" in begin
    assert "metricsShown = 0;" in begin
    tick = _body(SHOWCASE, "internal static void Tick(bool directorIdleNoTicket)")
    assert tick.count("BeginRotation();") == 1 and "Advance();" in tick
    assert "script[viewIdx].Dwell" in tick
    advance = _body(SHOWCASE, "private static void Advance()")
    assert "ShowcaseRules.Next(script, viewIdx, candidates.Count, out wrapped)" in advance
    assert "BeginRotation();" in advance and "StartView(next);" in advance


def test_every_metric_shown_logs_one_line():
    start = _body(SHOWCASE, "private static void StartView(int v)")
    assert start.count("NativeUI.DevSetCompareMetricByName(") == 1
    assert "bool set = NativeUI.DevSetCompareMetricByName(name);" in start
    assert "Plugin.Log?.LogInfo(ShowcaseRules.MetricLine(view.Arg, metrics.Length, name)" in start
    assert "if (set) metricsShown++;" in start
    # the pair the metrics need is the existing selection, set up once
    assert start.count("NativeUI.DevSetCompareSelection(candidates);") == 1
    assert _code(SHOWCASE).count("DevSetCompareMetricByName(") == 1
    advance = _body(SHOWCASE, "private static void Advance()")
    assert '"[SHOWCASE] rotation complete: " + metricsShown + "/" + metrics.Length' in advance


def test_the_dwell_is_a_config_key_with_the_rules_default():
    plugin = _code(PLUGIN / "Plugin.cs")
    m = re.search(r'Config\.Bind\(\s*"Broadcast", "ShowcaseMetricSeconds", ([0-9.]+)f,', plugin)
    assert m, "the ShowcaseMetricSeconds key is not bound"
    rules = _code(PLUGIN / "ShowcaseRules.cs")
    d = re.search(r"DEFAULT_METRIC_SECONDS = ([0-9.]+)f", rules)
    assert d and float(m.group(1)) == float(d.group(1)) == 15.0
    configured = _body(SHOWCASE, "private static float MetricSecondsConfigured()")
    assert "Plugin.BroadcastShowcaseMetricSeconds.Value" in configured


def test_the_test_lever_lifts_the_stream_gate_and_nothing_else():
    plugin = _code(PLUGIN / "Plugin.cs")
    assert re.search(r'Config\.Bind\(\s*"Broadcast", "TestShowcase", "",', plugin)
    lever = _body(PLUGIN / "Plugin.cs", "private void TickTestShowcase()")
    assert "!BroadcastMode.IsBroadcastIdentity" in lever
    assert "if (_lastTestShowcase == null) { _lastTestShowcase = raw; return; }" in lever
    assert "IdleShowcase.DevRunOneRotation();" in lever
    assert plugin.count("try { TickTestShowcase(); } catch { }") == 1
    tick = _body(SHOWCASE, "internal static void Tick(bool directorIdleNoTicket)")
    assert "if (!streamLive && !testRotation) { if (opened) Interrupt(); return; }" in tick
    assert tick.count("testRotation") == 4, "the lever reaches a gate other than the stream's"
    # the other gates stand, in their order
    order = ["if (!directorIdleNoTicket)", "if (opened && !NativeUI.ShowcaseOwnsPage)",
             "if (reportActive)", "if (!streamLive && !testRotation)",
             "PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode", "if (suppressed) return;",
             "if (!opened && NativeUI.IsOpen) return;"]
    at = [tick.index(s) for s in order]
    assert at == sorted(at), at
