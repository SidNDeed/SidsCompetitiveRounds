"""The in-game uploader's size refusals state the exact limit their checks
enforce (the FAQ refresh's client contract, section 3).

The PNG refusal once said "1 MB max" beside a 1,200,000-byte check; the
figure was later formatted from the constant, but as "0.# MB", which rounds
to a tenth of a million bytes: a cap raised by 40,000 bytes still read
"1.2 MB", and a file browser that counts a megabyte as 1,048,576 bytes shows a
refused file as smaller than that. The contract's requirement is the value
the check enforces, 1,200,000 bytes, and the GIF refusal is the same class.

Two halves. The source half reads plugin/NativeUI.cs: every size refusal
formats its figure from the very constant its comparison uses, and carries no
written-out figure. The executed half compiles SizeCapLabel verbatim out of
the same file into a throwaway console program and runs it on the shipped
caps and on caps no shipped constant has, under four cultures: every label
must be the digit-grouped byte count followed by "bytes", and must parse back
to exactly the number it was given. It needs the dotnet CLI and skips without
it, the way test_client_rules_harness.py does.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NATIVE_UI = ROOT / "plugin" / "NativeUI.cs"

# A size check and the refusal it returns: the comparison names a cap
# constant, and the message on the same or the next line states the figure.
_SIZE_CHECK = re.compile(r"bytes\.Length > (Cosmetic\w*MaxBytes)\)")
_CAP_DECL = re.compile(r"private const int (Cosmetic\w*MaxBytes) = ([0-9_]+);")
_LABEL_DECL = "private static string SizeCapLabel(int bytes)"

# Caps no shipped constant has, chosen to sit where a rounded figure is wrong:
# within a tenth of a million of a round number, either side, and the edges.
_PROBE_CAPS = (1_240_000, 1_150_000, 1_000_001, 999_999, 2_249_999, 1, 0, 2_147_483_647)
_CULTURES = ("invariant", "de-DE", "sv-SE", "fr-FR")
_EXACT = re.compile(r"^(\d{1,3}(?:,\d{3})*) bytes$")


def _source():
    return NATIVE_UI.read_text(encoding="utf-8")


def _caps(src):
    caps = {name: int(value.replace("_", "")) for name, value in _CAP_DECL.findall(src)}
    assert len(caps) == 2, "expected the PNG and GIF byte caps, found %s" % sorted(caps)
    return caps


def _label_method(src):
    """SizeCapLabel's whole declaration, verbatim, by brace matching."""
    assert src.count(_LABEL_DECL) == 1, "SizeCapLabel is declared %d times" % src.count(_LABEL_DECL)
    start = src.index(_LABEL_DECL)
    open_at = src.index("{", start)
    depth = 0
    for i in range(open_at, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError("SizeCapLabel's body never closes")


def test_each_size_refusal_states_the_constant_its_check_compares_against():
    src = _source()
    caps = _caps(src)
    lines = src.split("\n")
    checks = [(i, m.group(1)) for i, line in enumerate(lines) for m in _SIZE_CHECK.finditer(line)]
    found = sorted(name for _i, name in checks)
    assert found == sorted(caps), (
        "the size checks compare against %s; the declared caps are %s — a cap "
        "with no check, or a check against something else" % (found, sorted(caps)))
    for i, name in checks:
        window = "\n".join(lines[i:i + 2])
        stated = re.findall(r"\{SizeCapLabel\((\w+)\)\} max", window)
        assert stated == [name], (
            "NativeUI.cs:%d compares against %s but its refusal states %s"
            % (i + 1, name, stated or "no formatted figure"))
        message = re.search(r'\\"detail\\":\\"(.*?)\\"', window)
        assert message, "NativeUI.cs:%d: no detail message beside the check" % (i + 1)
        text = re.sub(r"\{[^{}]*\}", "", message.group(1))
        assert not re.search(r"\d", text), (
            "NativeUI.cs:%d: the refusal carries a written-out figure beside the "
            "formatted one: %r" % (i + 1, text))
        assert "MB" not in text and "KB" not in text, (
            "NativeUI.cs:%d: the refusal names a unit of its own: %r" % (i + 1, text))


def _dotnet():
    found = shutil.which("dotnet")
    if found:
        return found
    candidate = Path(os.path.expanduser("~")) / ".dotnet" / "dotnet.exe"
    return str(candidate) if candidate.exists() else None


_PROGRAM = """using System;
using System.Globalization;
using System.Threading;

static class Probe
{
%METHOD%

    static int Main(string[] args)
    {
        foreach (var name in new[] { %CULTURES% })
        {
            Thread.CurrentThread.CurrentCulture = name == "invariant"
                ? CultureInfo.InvariantCulture : new CultureInfo(name);
            foreach (var a in args)
                Console.WriteLine(name + "\\t" + a + "\\t" + SizeCapLabel(int.Parse(a, CultureInfo.InvariantCulture)));
        }
        return 0;
    }
}
"""

_PROJECT = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>disable</Nullable>
    <ImplicitUsings>disable</ImplicitUsings>
    <InvariantGlobalization>false</InvariantGlobalization>
  </PropertyGroup>
</Project>
"""


def test_the_stated_cap_is_the_exact_byte_count_under_any_culture(tmp_path):
    dotnet = _dotnet()
    if dotnet is None:
        pytest.skip("dotnet CLI not on this machine")
    src = _source()
    caps = _caps(src)
    method = _label_method(src)
    program = _PROGRAM.replace("%METHOD%", method).replace(
        "%CULTURES%", ", ".join('"%s"' % c for c in _CULTURES))
    (tmp_path / "Probe.csproj").write_text(_PROJECT, encoding="utf-8")
    (tmp_path / "Program.cs").write_text(program, encoding="utf-8")
    values = sorted(set(caps.values()) | set(_PROBE_CAPS))
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    run = subprocess.run(
        [dotnet, "run", "--project", str(tmp_path / "Probe.csproj"), "-c", "Release", "--"]
        + [str(v) for v in values],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, env=env)
    assert run.returncode == 0, "the probe did not build or run:\n%s\n%s" % (
        run.stdout[-3000:], run.stderr[-3000:])
    rows = [ln.split("\t") for ln in run.stdout.splitlines() if ln.count("\t") == 2]
    assert len(rows) == len(values) * len(_CULTURES), (
        "the probe printed %d labels for %d caps under %d cultures"
        % (len(rows), len(values), len(_CULTURES)))
    wrong = []
    for culture, given, label in rows:
        m = _EXACT.match(label)
        if not m or int(m.group(1).replace(",", "")) != int(given):
            wrong.append("%s: %s bytes is stated as %r" % (culture, given, label))
    assert not wrong, (
        "SizeCapLabel does not state the exact byte count it is given:\n" + "\n".join(wrong))
    shipped = {label for culture, given, label in rows if int(given) in caps.values()}
    assert shipped == {"1,200,000 bytes", "2,200,000 bytes"}, (
        "the shipped caps are stated as %s" % sorted(shipped))
