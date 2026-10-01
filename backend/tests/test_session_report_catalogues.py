"""Every string the session report shows is in every bundled catalogue.

Board rows 30c, 30d and 30e added fifty display strings to the report (30g
and 31 add none a player reads). The artifact that renders is the
DLL-bundled plugin/I18nCatalogues.cs, never a SQL seed (#583), and a key with
no entry renders English with every other gate green (#578). The key set is
the extractor's own: every string tools/i18n_extract.py harvests from a
report surface (SessionReportView, SessionReportModel, PostSessionReport), so
a string added to those files later is held here as well, and a string the
report stopped showing stops being asked for (its catalogue entries stay, as
the catalogue file's own rule keeps them for a rollback).
"""
import functools
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))

import i18n_extract                                   # noqa: E402
from test_pc_sept12 import _bundled_catalogues        # noqa: E402

LOCALES = ("es", "ru", "uk", "sv")
SURFACES = ("SessionReportView", "SessionReportModel", "PostSessionReport")
PLACEHOLDER = re.compile(r"\{\d+[^}]*\}")


@functools.lru_cache(maxsize=1)
def _report_keys():
    _found, sites = i18n_extract.extract()
    return tuple(sorted(k for k, where in sites.items() if any(s[0] in SURFACES for s in where)))


def test_the_report_surfaces_are_harvested():
    keys = _report_keys()
    assert len(keys) >= 150, len(keys)
    for k in ("Set totals", "Player totals", "Score race (rounds won per game)",
              "{0} of {1} games timed", "The lead in rounds changed hands {0} times over the set",
              "Games {0}-{1} of {2}", "dimmed: rolled out of the build"):
        assert k in keys, k
    # a string the report no longer shows is not asked for
    assert "Set summary" not in keys and "Score race (points per game)" not in keys


@pytest.mark.parametrize("lang", LOCALES)
def test_every_report_string_is_in_every_catalogue(lang):
    catalogue = _bundled_catalogues()
    assert lang in catalogue, "no %s dictionary in I18nCatalogues.cs" % lang
    missing, broken = [], []
    for k in _report_keys():
        v = catalogue[lang].get(k)
        if not v or not v.strip():
            missing.append(k)
        elif sorted(PLACEHOLDER.findall(v)) != sorted(PLACEHOLDER.findall(k)):
            broken.append(k)
    assert not missing, "%s: %d report string(s) with no entry, e.g. %r" % (lang, len(missing), missing[:5])
    assert not broken, "%s: placeholders changed in %r" % (lang, broken[:5])
