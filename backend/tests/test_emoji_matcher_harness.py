"""Bug 333 step 2 - the runtime's C# EmojiMatcher, EXECUTED (review E-M7).

test_emoji_atlas.py proves the Python reference matcher and the C# source
text agree on their self-check constants; this file compiles the C# class
out of plugin/EmojiSprites.cs into a small console program and runs it, so
the C# ALGORITHM is what is checked, not its literals. Skipped when no
dotnet SDK is on the PATH (the seat that builds the mod always has one).

Protocol: the program reads the key list (one hyphenated key per line) and a
vector file whose lines are `<T|N> <hex UTF-16 code units...>`, and prints one
line of hex UTF-16 code units per vector - so no emoji or quote ever has to
survive a shell or a console code page. It also runs the class's own
RunSelfTest and exits 3 on any warning.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CS_PATH = os.path.join(REPO, "plugin", "EmojiSprites.cs")
TOOL_PATH = os.path.join(REPO, "tools", "emoji_atlas.py")

pytestmark = pytest.mark.skipif(shutil.which("dotnet") is None, reason="no dotnet SDK on this seat")


def _tool():
    spec = importlib.util.spec_from_file_location("emoji_atlas_for_harness", TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # dataclasses resolve cls.__module__ through here
    spec.loader.exec_module(mod)
    return mod


def _matcher_class_text() -> str:
    """The EmojiMatcher class, from its declaration to the closing brace at the
    class's own indent - everything the harness compiles besides its stub."""
    with open(CS_PATH, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip().startswith("internal sealed class EmojiMatcher"))
    indent = len(lines[start]) - len(lines[start].lstrip())
    close = indent * " " + "}"
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == close)
    text = "\n".join(lines[start:end + 1])
    assert "EmojiSprites.SPRITE_NAME_PREFIX" in text, "the class names its sprites through the outer constant"
    return text


PROGRAM = r'''
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace Harness
{
    internal static class EmojiSprites { internal const string SPRITE_NAME_PREFIX = "e_"; }

    // ---- EmojiMatcher, verbatim from plugin/EmojiSprites.cs ----
__MATCHER__
    // ---- end of the runtime class ----

    internal static class Program
    {
        static string Decode(string[] hex, int from)
        {
            var sb = new StringBuilder();
            for (int i = from; i < hex.Length; i++)
                if (hex[i].Length > 0) sb.Append((char)int.Parse(hex[i], NumberStyles.HexNumber, CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        static string Encode(string s)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < s.Length; i++) { if (i > 0) sb.Append(' '); sb.Append(((int)s[i]).ToString("X4")); }
            return sb.ToString();
        }

        static int Main(string[] args)
        {
            var keys = new List<string>();
            foreach (var k in File.ReadAllLines(args[0], Encoding.UTF8)) if (k.Trim().Length > 0) keys.Add(k.Trim());
            var m = new EmojiMatcher(keys);
            int rc = 0;
            EmojiMatcher.RunSelfTest(s => { }, s => { Console.Error.WriteLine("SELFTEST WARN: " + s); rc = 3; });
            foreach (var line in File.ReadAllLines(args[1], Encoding.UTF8))
            {
                if (line.Trim().Length == 0) continue;
                string[] parts = line.Split(' ');
                bool tint = parts[0] == "T";
                Console.Out.WriteLine("OUT " + Encode(m.Substitute(Decode(parts, 1), tint)));   // prefixed: an empty result is still a line
            }
            Console.Out.WriteLine("COUNT " + m.Count.ToString(CultureInfo.InvariantCulture));
            return rc;
        }
    }
}
'''

CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>disable</Nullable>
    <ImplicitUsings>disable</ImplicitUsings>
    <LangVersion>latest</LangVersion>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <NoWarn>CS0168;CS0219;CS0414;CS0649;CS0169;CS8632</NoWarn>
    <SatelliteResourceLanguages>en</SatelliteResourceLanguages>
  </PropertyGroup>
</Project>
"""


def _hex(s: str) -> str:
    units = s.encode("utf-16-le")
    return " ".join("%04X" % int.from_bytes(units[i:i + 2], "little") for i in range(0, len(units), 2))


def _unhex(line: str) -> str:
    parts = [p for p in line.strip().split(" ") if p]
    return b"".join(int(p, 16).to_bytes(2, "little") for p in parts).decode("utf-16-le", "surrogatepass")


class Harness:
    def __init__(self, tmp_path):
        self.dir = tmp_path / "harness"
        self.dir.mkdir()
        (self.dir / "harness.csproj").write_text(CSPROJ, encoding="utf-8")
        (self.dir / "Program.cs").write_text(PROGRAM.replace("__MATCHER__", _matcher_class_text()), encoding="utf-8")
        env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
                   DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", MSBUILDTERMINALLOGGER="off")
        self.env = env
        build = subprocess.run(["dotnet", "build", str(self.dir / "harness.csproj"), "-c", "Release", "-nologo", "-v", "q",
                                "-o", str(self.dir / "out")],
                               capture_output=True, text=True, timeout=300, env=env, cwd=str(self.dir))
        assert build.returncode == 0, "harness build failed:\n" + build.stdout[-4000:] + build.stderr[-2000:]
        self.dll = self.dir / "out" / "harness.dll"
        assert self.dll.exists()

    def run(self, keys, vectors):
        """vectors: list of (text, tint) -> list of outputs (str), plus the matcher's Count."""
        kf = self.dir / "keys.txt"
        vf = self.dir / "vectors.txt"
        kf.write_text("\n".join(keys) + "\n", encoding="utf-8")
        vf.write_text("\n".join(("T " if tint else "N ") + _hex(t) for t, tint in vectors) + "\n", encoding="utf-8")
        r = subprocess.run(["dotnet", str(self.dll), str(kf), str(vf)], capture_output=True, text=True,
                           timeout=120, env=self.env, cwd=str(self.dir))
        assert r.returncode == 0, "harness run failed (%d):\n%s\n%s" % (r.returncode, r.stdout[-2000:], r.stderr[-2000:])
        outs = [l[4:] for l in r.stdout.splitlines() if l.startswith("OUT ")]
        counts = [l for l in r.stdout.splitlines() if l.startswith("COUNT ")]
        assert len(outs) == len(vectors) and len(counts) == 1, r.stdout[-2000:]
        return [_unhex(l) for l in outs], int(counts[0].split()[1])


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    return Harness(tmp_path_factory.mktemp("emoji"))


def test_the_compiled_matcher_reproduces_every_reference_vector(harness):
    ea = _tool()
    vectors = [(inp, False) for inp, _ in ea.SELF_CHECK_VECTORS] + [(ea.SELF_CHECK_TINT[0], True)]
    expected = [exp for _, exp in ea.SELF_CHECK_VECTORS] + [ea.SELF_CHECK_TINT[1]]
    outputs, count = harness.run(list(ea.SELF_CHECK_KEYS), vectors)
    assert count == len(set(ea.SELF_CHECK_KEYS))
    for (inp, _), got, exp in zip(vectors, outputs, expected):
        assert got == exp, "C# matcher disagrees with the reference on %r: got %r, expected %r" % (inp, got, exp)
    # the Python reference agrees with itself on the same inputs (ties the two proofs together)
    ref = ea.ReferenceMatcher(list(ea.SELF_CHECK_KEYS)) if hasattr(ea, "ReferenceMatcher") else None
    if ref is not None:
        for (inp, tint), exp in zip(vectors, expected):
            assert ref.substitute(inp, tint) == exp


def test_the_harness_has_teeth_a_missing_key_changes_the_output(harness):
    """Negative control (#391): without the ZWJ family key, the family sequence
    must fall apart into its member sprites instead of one family sprite."""
    ea = _tool()
    family = "1F468-200D-1F469-200D-1F467"
    keys = [k for k in ea.SELF_CHECK_KEYS if k != family]
    assert family in ea.SELF_CHECK_KEYS and len(keys) == len(ea.SELF_CHECK_KEYS) - 1
    inp = "\U0001F468‍\U0001F469‍\U0001F467"
    full, _ = harness.run(list(ea.SELF_CHECK_KEYS), [(inp, False)])
    partial, count = harness.run(keys, [(inp, False)])
    assert full[0] == '<sprite name="e_%s">' % family
    assert partial[0] != full[0]
    assert "e_1F468" in partial[0] and "e_1F469" in partial[0] and "e_1F467" in partial[0]
    assert count == len(set(keys))


def test_the_compiled_matcher_leaves_existing_tags_and_unknown_code_points_alone(harness):
    ea = _tool()
    vectors = [
        ('<sprite name="e_1F600"> \U0001F600', False),          # an existing tag is not re-substituted
        ("plain ascii, no emoji", False),
        ("\U0001F9FF unknown", False),                            # not in the key list: passes through
        ("<b>\U0001F600</b>", False),                             # a tag the input already carries stays intact
    ]
    outputs, _ = harness.run(list(ea.SELF_CHECK_KEYS), vectors)
    assert outputs[0] == '<sprite name="e_1F600"> <sprite name="e_1F600">'
    assert outputs[1] == "plain ascii, no emoji"
    assert outputs[2] == "\U0001F9FF unknown"
    assert outputs[3] == '<b><sprite name="e_1F600"></b>'
