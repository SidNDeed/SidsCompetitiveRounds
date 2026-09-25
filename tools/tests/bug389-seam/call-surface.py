# The external call surface of the two bug-389 files, DERIVED rather than
# recalled.
#
# Why this exists. The notes' integrity answer for the gold axis reads "no award
# or currency call exists in either file, and none is reachable from the members
# above", and "the members above" was a list written out by hand. A hand list
# is not auditable: the round that added a Photon property write to the patches
# file left the list at twenty-five members that did not include it, so the
# reachability half of the answer rested on an enumeration that was materially
# incomplete while its stated expiry condition was keyed only to the grep.
#
# So the list is produced from the files. Run it and paste what it prints; the
# expiry condition then applies to something a reader can reproduce.
#
#   python tools/tests/bug389-seam/call-surface.py
#
# What it counts as external: on CODE lines only (whole-line comments dropped,
# which is how both files comment), every `Type.Member` qualified reference and
# every type named in `typeof(...)`, in a `[HarmonyPatch(typeof(...))]`, in a
# generic argument, or as a declared local's type, MINUS the names declared in
# these two files themselves. Over-inclusion is the safe direction for this
# question: a name listed that is really local costs a reader one lookup, a name
# omitted costs the answer its meaning.
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FILES = ["plugin/ProximityVictimSeam.cs", "plugin/ProximityVictimPatches.cs"]


def code_lines(text):
    out = []
    for line in text.split(chr(10)):
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        if stripped.startswith("using "):
            continue          # a namespace import is not a call
        out.append(line)
    return chr(10).join(out)


def declared_here(text):
    names = set()
    for pat in (r"\b(?:class|struct|enum|interface)\s+([A-Za-z_][A-Za-z0-9_]*)",
                r"\bnamespace\s+([A-Za-z_][A-Za-z0-9_.]*)"):
        for m in re.finditer(pat, text):
            names.add(m.group(1))
    return names


def main():
    blobs = {}
    local = set()
    for rel in FILES:
        path = os.path.join(REPO, rel.replace("/", os.sep))
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        blobs[rel] = code_lines(raw)
        # From the CODE, not the prose: "the class this patch replaces" in a doc
        # comment would otherwise declare a type called "this".
        local |= declared_here(blobs[rel])

    print("declared in these two files (excluded from the surface): "
          + ", ".join(sorted(local)))
    print("")

    for rel, text in blobs.items():
        members = set()
        types = set()
        # Qualified references: Type.Member
        for m in re.finditer(r"\b([A-Z][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", text):
            owner, member = m.group(1), m.group(2)
            if owner in local:
                continue
            members.add(owner + "." + member)
        # Bare types: typeof(X), generics, attributes, declarations
        for pat in (r"typeof\(\s*([A-Z][A-Za-z0-9_]*)",
                    r"<\s*([A-Z][A-Za-z0-9_]*)\s*>",
                    r"\b([A-Z][A-Za-z0-9_]*)\s*\[\s*\]\s+[a-z]",
                    r"^\s*([A-Z][A-Za-z0-9_]*)\s+[a-z][A-Za-z0-9_]*\s*[;=)]",
                    r"\(\s*([A-Z][A-Za-z0-9_]*)\s+[a-z][A-Za-z0-9_]*\s*[,)]"):
            for m in re.finditer(pat, text, re.MULTILINE):
                name = m.group(1)
                if name in local:
                    continue
                types.add(name)
        # MEMBERS INVOKED ON A LOCAL OR A PARAMETER. This bucket is the reason
        # the hand-written list was wrong: the property write this round added
        # reads `me.SetCustomProperties(...)`, where `me` is a local, so no
        # statically-qualified reference to it exists anywhere in the file and an
        # eye scanning for `Type.Member` will not see it.
        instance = set()
        for m in re.finditer(r"\b[a-z_][A-Za-z0-9_]*\??\.([A-Za-z_][A-Za-z0-9_]*)\s*[(<]", text):
            instance.add(m.group(1))
        types -= {t.split(".")[0] for t in members}
        print("=== " + rel)
        print("  qualified members (" + str(len(members)) + "):")
        for x in sorted(members):
            print("    " + x)
        print("  members invoked on a local or parameter (" + str(len(instance)) + "):")
        for x in sorted(instance):
            print("    " + x)
        print("  types named with no member access (" + str(len(types)) + "):")
        for x in sorted(types):
            print("    " + x)
        print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
