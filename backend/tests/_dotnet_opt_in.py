"""Where a test may build and run C# with the dotnet CLI.

`dotnet build` and `dotnet run` compile a project, so a test that does either
runs only where building is opted into: SCR_CLIENT_HARNESS_RUN=1 on any
machine, or the LXC seat's gate runner, recognised by the staged decompiled
tree it sets on every pytest run (SCR_DECOMPILED_DIR under /seat/). The VM
seat sets neither and never builds there; each such test skips and says why.
Every test module that invokes dotnet asks here (require_dotnet_opt_in, or
dotnet_opt_in in a module skip mark) before it looks for the CLI;
test_dotnet_opt_in.py checks that for every module under backend/tests.
"""
import os

import pytest

HARNESS_OPT_IN = "SCR_CLIENT_HARNESS_RUN"

SKIP_REASON = ("this test builds C# with dotnet, which runs only on an LXC seat "
               "or with %s=1" % HARNESS_OPT_IN)


def dotnet_opt_in(env=None):
    """Why this run may build with dotnet, or None when it may not."""
    env = os.environ if env is None else env
    if env.get(HARNESS_OPT_IN) == "1":
        return HARNESS_OPT_IN + "=1"
    staged = env.get("SCR_DECOMPILED_DIR", "")
    if staged.startswith("/seat/"):
        return "the seat gate runner (SCR_DECOMPILED_DIR=%s)" % staged
    return None


def require_dotnet_opt_in():
    """Skip the calling test or fixture unless this run may build with dotnet."""
    if dotnet_opt_in() is None:
        pytest.skip(SKIP_REASON)
