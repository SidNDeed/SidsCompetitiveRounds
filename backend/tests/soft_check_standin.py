"""One stand-in for main._check_steam_session (bans part 2a, FIX-1 M3).

A test that puts its own function in as the soft session check takes the
place of the real one for every route, the exits of BAN-R17 too. This
stand-in admits every caller, as the no-op forms did, and RECORDS the
keywords of every call, so a test can assert that an exit passed
banned_ok=True. It takes every argument the real check takes and drops none.

`behave`, when given, is called with the same arguments after the call is
recorded, for a stand-in that judges something itself; its answer is the
stand-in's answer.
"""
from __future__ import annotations


class SoftCheckStandIn:
    def __init__(self, result=None, behave=None):
        self.result = result
        self.behave = behave
        self.calls = []

    async def __call__(self, *args, **kw):
        self.calls.append((args, dict(kw)))
        if self.behave is not None:
            out = self.behave(*args, **kw)
            if hasattr(out, "__await__"):
                out = await out
            return out
        return self.result

    def keywords(self):
        """The keywords of every recorded call, in order."""
        return [kw for _args, kw in self.calls]
