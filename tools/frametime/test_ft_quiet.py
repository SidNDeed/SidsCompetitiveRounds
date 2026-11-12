"""test_ft_quiet.py: the quiet protocol's acceptance (ft_quiet.py) on generated traces (method-v52.md section 6).

The three required counterexamples (method-v52.md:130): ten page reads a second for ten seconds fails; disabled
scheduler statistics (schedstat frozen at zero) fail the contention fixture; a complete quiet trace passes. Every
rule also has its own breach (a mutant that must FAIL or REFUSE) beside the same trace at its limit (the negative
control, which must PASS), and the clean trace is mutant 0.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ft_quiet as Q  # noqa: E402

T0 = 1762855200000          # utc ms of the first host sample (any fixed value)
GAME_AT = 30                # seconds from T0: the guest trace shows ROUNDS from here
GAME_S = 40                 # seconds of game
TIDS = ("501", "502", "503", "504")
CPUS = {"501": "2", "502": "3", "503": "4", "504": "5"}
HEAD = "QH v1 vcpus=501,502,503,504 reserved=2,3,4,5"


def guest_trace(path, edit=None, ncpu=4, disks="0_C:,1_D:", n=GAME_AT + GAME_S + 5):
    """one G line a second; ROUNDS (pid 4321) present from GAME_AT for GAME_S seconds. The game uses 1.0 core of
    four and the total is 26.0 percent, so the non-game work is 0.04 core. edit(i, rec) may change second i."""
    lines = ["QG v1 ncpu=%d disks=%s" % (ncpu, disks)]
    for i in range(n):
        live = GAME_AT <= i < GAME_AT + GAME_S
        r = {"utc": T0 + 1000 * i, "mono": 5000000000 + i * 1000000000, "total": "26.0" if live else "1.0",
             "rpid": "4321" if live else "-", "rstart": "133800000000000000" if live else "-",
             "rcpu": ("NA" if i == GAME_AT else "1.0") if live else "0", "dq": "0.10,0.02", "avail": "6000", "commit": "40.0",
             "pin": "0", "prd": "0", "pout": "0"}
        if edit:
            edit(i, r)
        if r is not None and not r.get("_drop"):
            lines.append("G " + " ".join("%s=%s" % (k, v) for k, v in r.items() if not k.startswith("_")))
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return path


def host_trace(path, edit=None, fixture=(10, 20), fwait=200000000, n=GAME_AT + GAME_S + 5, head=HEAD):
    """one group a second: four vCPUs pinned one to a core, each running 0.9 s a second with 0.1 ms of wait, and
    their four reserved cores busy 0.91 s (0.01 core of non-VM work); inside the fixture vCPU 501 waits 0.2 s a
    second. edit(i, tid_or_cpu, rec) may change one record of second i (cpu records are keyed "c<cpu>")."""
    lines = [head]
    run = dict((t, 0) for t in TIDS)
    wait = dict((t, 0) for t in TIDS)
    busy = dict((CPUS[t], 0) for t in TIDS)
    for i in range(n):
        utc, mono = T0 + 1000 * i, 9000000000 + i * 1000000000
        if fixture and i == fixture[0]:
            lines.append("X utc=%d mono=%d fixture=start" % (utc, mono))
        for t in TIDS:
            if i:
                run[t] += 900000000
                wait[t] += fwait if (fixture and t == "501" and fixture[0] < i <= fixture[1]) else 100000
                busy[CPUS[t]] += 910000000
            r = {"utc": utc, "mono": mono, "tid": t, "cpus": CPUS[t], "run": run[t], "wait": wait[t]}
            if edit:
                edit(i, t, r)
            if not r.get("_drop"):
                lines.append("V " + " ".join("%s=%s" % (k, v) for k, v in r.items() if not k.startswith("_")))
        for t in TIDS:
            c = {"utc": utc, "mono": mono, "cpu": CPUS[t], "busy": busy[CPUS[t]]}
            if edit:
                edit(i, "c" + CPUS[t], c)
            if not c.get("_drop"):
                lines.append("C " + " ".join("%s=%s" % (k, v) for k, v in c.items() if not k.startswith("_")))
        if fixture and i == fixture[1]:
            lines.append("X utc=%d mono=%d fixture=stop" % (utc, mono))
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return path


def verdict(tmp_path, gedit=None, hedit=None, host=True, **hk):
    g = guest_trace(str(tmp_path / "g.txt"), gedit)
    h = host_trace(str(tmp_path / "h.txt"), hedit, **hk) if host else "-"
    v, lines = Q.judge(g, h)
    return v, "\n".join(lines)


def in_game(i):
    return GAME_AT <= i < GAME_AT + GAME_S


def at(lo, hi):
    return lambda i: GAME_AT + lo <= i < GAME_AT + hi


# ---- the three required counterexamples

def test_complete_quiet_trace_passes(tmp_path):
    v, out = verdict(tmp_path)
    assert v == "PASS", out
    assert out.count(" PASS") == 11 and " FAIL" not in out, out


def test_ten_page_reads_a_second_for_ten_seconds_fails(tmp_path):
    w = at(5, 15)
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(prd="10") if w(i) else None)
    assert v == "FAIL" and "QUIET guest Page Reads/sec FAIL: worst ten-second integral 100.00" in out, out


def test_page_reads_at_the_limit_pass(tmp_path):
    # the negative control: one read a second for ten seconds integrates to 10, the limit itself
    w = at(5, 15)
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(prd="1") if w(i) else None)
    assert v == "PASS" and "Page Reads/sec PASS: worst ten-second integral 10.00" in out, out


def test_disabled_schedstat_fails_the_contention_fixture(tmp_path):
    # schedstat off: every wait counter frozen at zero (runtime still grows)
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(wait=0) if "wait" in r else None)
    assert v == "FAIL" and "QUIET contention fixture FAIL" in out, out


def test_frozen_zero_counters_fail_the_contention_fixture(tmp_path):
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(wait=0, run=0) if "wait" in r else None)
    assert v == "FAIL" and "QUIET contention fixture FAIL" in out, out


# ---- each guest rule: its breach and its limit

@pytest.mark.parametrize("field,bad,good,rule", [
    ("total", "32.0", "31.0", "non-game cores"),       # every interval: 0.28 core fails, 0.24 passes p95 only below
    ("dq", "3.50,0.02", "3.00,0.02", "disk queue"),
    ("avail", "2999", "3000", "available memory"),
    ("commit", "85.5", "85.0", "committed"),
    ("pin", "11", "10", "Pages Input/sec"),
    ("pout", "11", "10", "Pages Output/sec"),
])
def test_guest_rule_breach_and_limit(tmp_path, field, bad, good, rule):
    one = at(10, 11)
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update({field: bad}) if one(i) else None)
    assert v == "FAIL" and ("QUIET guest %s FAIL" % rule) in out, out
    if field == "total":
        good = "26.8"   # one interval at 0.072 core: within every-interval 0.20 and one of 39, so p95 stays 0.04
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update({field: good}) if one(i) else None)
    assert v == "PASS", out


def test_non_game_p95_breach_and_limit(tmp_path):
    many = at(0, 6)      # six of 39 intervals above 0.05: the p95 is above the limit
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(total="27.6") if many(i) else None)
    assert v == "FAIL" and "QUIET guest non-game cores FAIL: p95 0.1040" in out, out
    few = at(0, 1)       # one interval above (the 95th of 39 intervals is the 38th smallest)
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(total="27.6") if few(i) else None)
    assert v == "PASS", out


# ---- each host rule: its breach and its limit

def wait_step(tid, from_i, to_i, per_s):
    def e(i, t, r):
        if t == tid and "wait" in r and i >= from_i:
            r["wait"] = r["wait"] + per_s * (min(i, to_i) - from_i + 1)
    return e


def test_vcpu_delay_every_interval(tmp_path):
    s = GAME_AT + 10
    v, out = verdict(tmp_path, hedit=wait_step("503", s, s, 60000000))       # 6 percent in one second
    assert v == "FAIL" and "QUIET host vCPU delay every interval FAIL" in out, out
    v, out = verdict(tmp_path, hedit=wait_step("503", s, s, 4900000))        # 4.9 percent there, 0.13 overall
    assert v == "PASS", out


def test_vcpu_delay_overall(tmp_path):
    a, b = GAME_AT + 1, GAME_AT + GAME_S - 1
    v, out = verdict(tmp_path, hedit=wait_step("502", a, b, 15000000))       # 1.5 percent every second
    assert v == "FAIL" and "QUIET host vCPU delay overall FAIL" in out and "every interval PASS" in out, out
    v, out = verdict(tmp_path, hedit=wait_step("502", a, b, 9000000))        # 0.9 percent plus the base 0.01
    assert v == "PASS", out


def test_reserved_core_non_vm(tmp_path):
    s = GAME_AT + 10

    def bump(extra):
        def e(i, t, r):
            if t == "c4" and i >= s:
                r["busy"] += extra
        return e
    v, out = verdict(tmp_path, hedit=bump(70000000))     # 0.01 + 0.07 core in one second
    assert v == "FAIL" and "QUIET host reserved-core non-VM FAIL" in out, out
    v, out = verdict(tmp_path, hedit=bump(30000000))     # 0.04 core
    assert v == "PASS", out


def test_fixture_contention_must_end_before_the_window(tmp_path):
    v, out = verdict(tmp_path, fixture=(18, GAME_AT - 2))      # one interval between its stop and the window
    assert v == "FAIL" and "QUIET contention fixture FAIL" in out and "then 1 quiet intervals" in out, out
    v, out = verdict(tmp_path, fixture=(16, GAME_AT - 4))      # three
    assert v == "PASS", out


def test_fixture_absent_refuses(tmp_path):
    v, out = verdict(tmp_path, fixture=None)
    assert v == "REFUSED" and "no contention fixture before the window: no X fixture=start line" in out, out


def test_fixture_without_stop_refuses(tmp_path):
    # the stop mark would come after the trace's end: none is before the window
    v, out = verdict(tmp_path, fixture=(10, GAME_AT + GAME_S + 10))
    assert v == "REFUSED" and "has no X fixture=stop line before the window" in out, out


def test_fixture_wait_below_ten_percent_fails(tmp_path):
    v, out = verdict(tmp_path, fwait=99000000)      # 9.9 percent of the wall
    assert v == "FAIL" and "QUIET contention fixture FAIL" in out, out
    v, out = verdict(tmp_path, fwait=100000000)     # 10 percent, the limit
    assert v == "PASS", out


# ---- refusals: no verdict

def test_no_host_trace_refuses(tmp_path):
    v, out = verdict(tmp_path, host=False)
    assert v == "REFUSED" and "missing host evidence refuses" in out, out


def test_host_trace_without_samples_in_the_window_refuses(tmp_path):
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if i >= GAME_AT - 1 else None)
    assert v == "REFUSED", out


def test_guest_gap_over_two_seconds_refuses(tmp_path):
    gap = at(10, 13)
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(_drop=1) if gap(i) else None)
    assert v == "REFUSED" and "gaps over two seconds refuse" in out, out
    gap = at(10, 11)     # two seconds exactly: an interval of 2 s is allowed
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(_drop=1) if gap(i) else None)
    assert v == "PASS", out


def test_host_gap_over_two_seconds_refuses(tmp_path):
    gap = at(10, 13)
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if gap(i) else None)
    assert v == "REFUSED" and "host trace: an interval of 4.000 s" in out, out


def test_rounds_identity_change_refuses(tmp_path):
    later = at(20, GAME_S)
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(rpid="9999") if later(i) else None)
    assert v == "REFUSED" and "ROUNDS identity changes" in out, out


def test_rounds_cpu_missing_inside_the_window_refuses(tmp_path):
    # NA is the first sample of the process only; anywhere else it refuses, and an explicit window that makes an
    # interval end on the first sample refuses too
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(rcpu="NA") if i == GAME_AT + 7 else None)
    assert v == "REFUSED", out
    g = guest_trace(str(tmp_path / "g.txt"))
    h = host_trace(str(tmp_path / "h.txt"))
    v, lines = Q.judge(g, h, (T0 + 1000 * (GAME_AT - 1), T0 + 1000 * (GAME_AT + 10)))
    assert v == "REFUSED", lines


def test_two_rounds_processes_refuse(tmp_path):
    # the sampler writes rpid=NA when more than one ROUNDS process runs: no single identity
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(rpid="NA", rstart="NA", rcpu="1.0") if in_game(i) else None)
    assert v == "REFUSED" and "ROUNDS identity changes" in out and "'NA'" in out, out


def test_vcpu_set_change_refuses(tmp_path):
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(tid="777") if t == "504" and i >= GAME_AT + 5 and "wait" in r else None)
    assert v == "REFUSED" and "the group at utc %d lacks vCPU 504 that the header names" % (T0 + 1000 * (GAME_AT + 5)) in out, out


def test_counter_backwards_refuses(tmp_path):
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(wait=0) if t == "501" and i == GAME_AT + 5 and "wait" in r else None)
    assert v == "REFUSED" and "goes backwards" in out, out


@pytest.mark.parametrize("field", ["total", "dq", "avail", "commit", "pin", "prd", "pout", "rcpu"])
def test_missing_or_na_guest_counter_refuses(tmp_path, field):
    one = at(3, 4)
    v, out = verdict(tmp_path, gedit=lambda i, r: r.pop(field) if one(i) else None)
    assert v == "REFUSED" and "lacks %s" % field in out, out
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update({field: "NA"}) if one(i) else None)
    assert v == "REFUSED", out


def test_the_cli_and_the_guest_half(tmp_path):
    g = guest_trace(str(tmp_path / "g.txt"))
    h = host_trace(str(tmp_path / "h.txt"))
    run = lambda *a: subprocess.run([sys.executable, "-I", "-B", os.path.join(HERE, "ft_quiet.py")] + list(a),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    p = run(g, h)
    assert p.returncode == 0 and p.stdout.rstrip().endswith("QUIET RESULT PASS"), p.stdout + p.stderr
    p = run(g, "-")
    assert p.returncode == 3 and p.stdout.rstrip().endswith("QUIET RESULT REFUSED"), p.stdout
    # the guest half has its own word, and never prints the sitting's RESULT line
    p = run("--guest", g)
    assert p.returncode == 0 and p.stdout.rstrip().endswith("QUIET GUEST-HALF PASS") and "RESULT" not in p.stdout
    bad = guest_trace(str(tmp_path / "b.txt"), lambda i, r: r.update(prd="10") if at(5, 15)(i) else None)
    p = run("--guest", bad)
    assert p.returncode == 1 and p.stdout.rstrip().endswith("QUIET GUEST-HALF FAIL"), p.stdout
    p = run(g)
    assert p.returncode == 2


# ---- the host sampler (ft_quiet_host.sh) on a stand-in /proc; it is never run on a host from here

# cpu2: user 100 (90 of them guest), nice 0, system 50, idle 1000, iowait 20, irq 5, softirq 5, steal 0, guest 90,
# guest_nice 3: busy = 100 + 0 + 50 + 5 + 5 + 0 = 160 ticks; guest and guest_nice are already inside user and nice
STAT = "cpu  1 1 1 1 1 1 1 1 1 1\ncpu2 100 0 50 1000 20 5 5 0 90 3\ncpu3 10 0 10 1000 0 0 0 0 0 0\n"


def fake_proc(root, vcpus=(("7001", "CPU 0/KVM", "2"), ("7002", "CPU 1/KVM", "3")), other=("7003", "worker", "0-7"),
              stat=STAT):
    """a stand-in /proc under root: FT_QUIET_PROC_ROOT is the seam through which a test feeds the sampler its own
    task files and /proc/stat text"""
    base = os.path.join(root, "proc", "4242", "task")
    for tid, comm, cpus in list(vcpus) + ([other] if other else []):
        d = os.path.join(base, tid)
        os.makedirs(d)
        open(os.path.join(d, "comm"), "w").write(comm + "\n")
        open(os.path.join(d, "schedstat"), "w").write("%s %s 77\n" % (int(tid) * 1000, int(tid)))
        open(os.path.join(d, "status"), "w").write("Name:\tx\nCpus_allowed_list:\t%s\n" % cpus)
    os.makedirs(os.path.join(root, "proc"), exist_ok=True)
    open(os.path.join(root, "proc", "stat"), "w").write(stat)


def clk_tck():
    return int(subprocess.run(["getconf", "CLK_TCK"], stdout=subprocess.PIPE, universal_newlines=True).stdout)


def host_sh(root, *args, test=True):
    env = dict(os.environ, FT_QUIET_PROC_ROOT=root)
    if test:
        env["FT_QUIET_TEST"] = "1"
    return subprocess.run(["bash", os.path.join(HERE, "ft_quiet_host.sh")] + list(args), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=60)


def test_host_sampler_writes_the_trace_the_checker_reads(tmp_path):
    root = str(tmp_path)
    fake_proc(root)
    out = os.path.join(root, "h.txt")
    p = host_sh(root, "4242", out, os.path.join(root, "stop"), "4", "2,3", "2", "1")
    assert p.returncode == 0, p.stderr
    # the header names the sets every group must hold a record for
    assert open(out).readline().rstrip("\n") == "QH v1 vcpus=7001,7002 reserved=2,3"
    groups, marks = Q.read_host(out)
    assert [m for _, m in marks] == ["start", "stop"], marks
    assert len(groups) == 4 and all(set(g["v"]) == {"7001", "7002"} for g in groups), groups
    g = groups[0]
    assert g["v"]["7001"] == {"cpus": "2", "run": 7001000.0, "wait": 7001.0}, g
    hz = clk_tck()
    assert g["c"] == {"2": 160 * 1e9 / hz, "3": 20 * 1e9 / hz}, g["c"]
    assert all(b["mono"] > a["mono"] for a, b in zip(groups, groups[1:]))


def test_host_sampler_busy_leaves_guest_time_out(tmp_path):
    # item 1, on a fixed /proc/stat text: cpu2 ran 0.9 s of VM work (guest 90 ticks, counted inside user 92) and 3
    # ticks of system; its busy is 95 ticks, so d busy - d run of its vCPU leaves the 5 ticks of other work. Adding
    # guest again would read 185, the VM's 0.9 core a second time. cpu3's line is short and cpu9 has none: busy=NA.
    root = str(tmp_path)
    fake_proc(root, stat="cpu  1 1 1 1 1 1 1 1 1 1\ncpu2 92 0 3 5 0 0 0 0 90 0\ncpu3 10 0 10\n")
    out = os.path.join(root, "h.txt")
    p = host_sh(root, "4242", out, os.path.join(root, "stop"), "1", "2,3,9")
    assert p.returncode == 0, p.stderr
    c = [ln.split()[3:] for ln in open(out).read().splitlines() if ln.startswith("C ")]
    assert c == [["cpu=2", "busy=%.0f" % (95 * 1e9 / clk_tck())], ["cpu=3", "busy=NA"], ["cpu=9", "busy=NA"]], c
    with pytest.raises(Q.Refused, match="busy='NA' is not a number"):
        Q.read_host(out)


def test_host_sampler_unreadable_affinity_refuses_in_the_checker(tmp_path):
    root = str(tmp_path)
    fake_proc(root)
    os.remove(os.path.join(root, "proc", "4242", "task", "7002", "status"))
    out = os.path.join(root, "h.txt")
    p = host_sh(root, "4242", out, os.path.join(root, "stop"), "1", "2,3")
    assert p.returncode == 0 and " tid=7002 cpus=NA " in open(out).read(), p.stderr
    with pytest.raises(Q.Refused, match="lacks cpus"):
        Q.read_host(out)


def test_host_sampler_refusals(tmp_path):
    root = str(tmp_path)
    p = host_sh(root, "4242", "x", "y", "2")                         # four arguments: no defaults
    assert p.returncode == 2 and "usage" in p.stderr
    p = host_sh(root, "4242", "x", "y", "two", "-")
    assert p.returncode == 2
    for bad in ("2,,3", "2,x", "2,", ",2"):                          # an empty or non-numeric reserved core
        p = host_sh(root, "4242", "x", "y", "2", bad)
        assert p.returncode == 2 and "reserved cpus must be" in p.stderr, bad
    fake_proc(root, vcpus=())
    out = os.path.join(root, "h.txt")
    p = host_sh(root, "4242", out, os.path.join(root, "stop"), "2", "-")
    assert p.returncode == 3 and "no host evidence" in p.stderr and not os.path.exists(out)


def test_host_sampler_unreadable_schedstat_refuses_in_the_checker(tmp_path):
    root = str(tmp_path)
    fake_proc(root)
    os.remove(os.path.join(root, "proc", "4242", "task", "7002", "schedstat"))
    out = os.path.join(root, "h.txt")
    p = host_sh(root, "4242", out, os.path.join(root, "stop"), "2", "2")
    assert p.returncode == 0, p.stderr
    with pytest.raises(Q.Refused):
        Q.read_host(out)


def test_a_trace_that_ends_or_starts_inside_the_game_refuses(tmp_path):
    g = guest_trace(str(tmp_path / "g.txt"), n=GAME_AT + 10)            # cut while ROUNDS runs
    h = host_trace(str(tmp_path / "h.txt"))
    v, lines = Q.judge(g, h)
    assert v == "REFUSED" and "ends while ROUNDS runs" in "\n".join(lines), lines
    g = guest_trace(str(tmp_path / "g2.txt"), lambda i, r: r.update(_drop=1) if i < GAME_AT else None)
    v, lines = Q.judge(g, h)
    assert v == "REFUSED" and "starts while ROUNDS runs" in "\n".join(lines), lines


# ---- inputs that are absent, partial or too short: each refuses and names the missing input; the complete trace
# (test_complete_quiet_trace_passes) is the negative control of every one, and each test holds its own where a
# near state must still pass

def stretch(s, n, by_ms):
    """guest samples after second s come by_ms later each, for n samples: n intervals of 1 s + by_ms"""
    def e(i, r):
        k = min(max(i - s, 0), n)
        r["mono"] += by_ms * 1000000 * k
        r["utc"] += by_ms * k
    return e


def test_paging_integral_weights_intervals_by_their_overlap(tmp_path):
    # item 2: nine intervals of 1.2 s at one read a second. Every ten seconds hold 10 reads; the nine whole intervals
    # that end inside one ten-second span hold 10.8
    s = GAME_AT + 5
    st = stretch(s, 9, 200)
    v, out = verdict(tmp_path, gedit=lambda i, r: (st(i, r), r.update(prd="1") if s < i <= s + 9 else None))
    assert v == "PASS" and "QUIET guest Page Reads/sec PASS: worst ten-second integral 10.00" in out, out
    # the same intervals at 1.2 reads a second: 12 in ten seconds
    v, out = verdict(tmp_path, gedit=lambda i, r: (st(i, r), r.update(prd="1.2") if s < i <= s + 9 else None))
    assert v == "FAIL" and "QUIET guest Page Reads/sec FAIL: worst ten-second integral 12.00" in out, out


def test_host_trace_must_cover_the_window(tmp_path):
    w0, w1 = T0 + 1000 * GAME_AT, T0 + 1000 * (GAME_AT + GAME_S - 1)
    # item 3: only two host samples inside a forty-second window
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if i > GAME_AT + 1 else None)
    assert v == "REFUSED" and "host trace does not cover the window's end: no sample after utc %d" % w1 in out, out
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if i < GAME_AT else None)
    assert v == "REFUSED" and "host trace does not cover the window's start: no sample before utc %d" % w0 in out, out
    # a gap across the window's start, then one across its end: the gap limit holds from the last sample before the
    # window to the first one after it
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if GAME_AT - 2 <= i < GAME_AT else None)
    assert v == "REFUSED" and "host trace: an interval of 3.000 s" in out, out
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if GAME_AT + GAME_S <= i < GAME_AT + GAME_S + 2 else None)
    assert v == "REFUSED" and "host trace: an interval of 3.000 s" in out, out
    # the negative control: one sample missing at each edge leaves two-second intervals, which pass
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if i in (GAME_AT - 1, GAME_AT + GAME_S) else None)
    assert v == "PASS", out


def test_guest_trace_must_cover_an_explicit_window(tmp_path):
    h = host_trace(str(tmp_path / "h.txt"))
    part = guest_trace(str(tmp_path / "g.txt"), lambda i, r: r.update(_drop=1) if not GAME_AT <= i < GAME_AT + 20 else None)
    v, lines = Q.judge(part, h, (T0 + 1000 * (GAME_AT + 1), T0 + 1000 * (GAME_AT + GAME_S - 1)))
    assert v == "REFUSED" and "guest trace does not cover the window's end: no sample after utc" in "\n".join(lines), lines
    v, lines = Q.judge(part, h, (T0 + 1000 * (GAME_AT - 5), T0 + 1000 * (GAME_AT + 10)))
    assert v == "REFUSED" and "guest trace does not cover the window's start: no sample before utc" in "\n".join(lines), lines
    # the negative control: the same window over the whole trace
    full = guest_trace(str(tmp_path / "g2.txt"))
    v, lines = Q.judge(full, h, (T0 + 1000 * (GAME_AT + 1), T0 + 1000 * (GAME_AT + GAME_S - 1)))
    assert v == "PASS", lines


def test_default_window_edges_must_be_observed_within_two_seconds(tmp_path):
    # ROUNDS's start (then its end) seen only across a four-second gap in the guest trace
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(_drop=1) if GAME_AT - 3 <= i < GAME_AT else None)
    assert v == "REFUSED" and "guest trace: an interval of 4.000 s" in out, out
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(_drop=1) if GAME_AT + GAME_S <= i < GAME_AT + GAME_S + 3 else None)
    assert v == "REFUSED" and "guest trace: an interval of 4.000 s" in out, out
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(_drop=1) if i in (GAME_AT - 1, GAME_AT + GAME_S) else None)
    assert v == "PASS", out


def test_guest_utc_must_increase_through_the_window(tmp_path):
    s = GAME_AT + 7
    v, out = verdict(tmp_path, gedit=lambda i, r: r.update(utc=T0 + 1000 * (s - 3)) if i == s else None)
    assert v == "REFUSED" and "guest trace: utc does not increase at %d" % (s + 2) in out, out


@pytest.mark.parametrize("head,drop_c,why", [
    ("QH v1", True, "host header lacks vcpus= (the vCPU threads the capture expects)"),
    ("QH v1 vcpus=501,502,503,504", True, "host header lacks reserved= (the reserved cores the capture expects)"),
    ("QH v1 vcpus=501,502,503,504 reserved=-", True, "host header names no reserved cores (reserved=-)"),
    ("QH v1 vcpus=- reserved=2,3,4,5", False, "host header names no vCPU threads (vcpus=-)"),
    ("QH v1 vcpus=501,502,503,504 reserved=2,x", False, "host header reserved='2,x' is not a list of distinct numbers"),
    ("QH v1 vcpus=501,502,503,504 reserved=2,3,4", False, "holds reserved core 5 that the header does not name"),
])
def test_host_header_must_name_the_expected_sets(tmp_path, head, drop_c, why):
    # item 4: the capture's header records the vCPU threads and the reserved cores every group must hold
    v, out = verdict(tmp_path, head=head, hedit=lambda i, t, r: r.update(_drop=1) if drop_c and t.startswith("c") else None)
    assert v == "REFUSED" and why in out, out


def test_reserved_core_records_removed_refuse(tmp_path):
    # item 4: every C record removed from a passing trace (the worst reserved-core value would read 0), then one
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if t.startswith("c") else None)
    assert v == "REFUSED" and "the group at utc %d lacks reserved core 2,3,4,5 that the header names" % T0 in out, out
    s = GAME_AT + 7
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if t == "c4" and i == s else None)
    assert v == "REFUSED" and "the group at utc %d lacks reserved core 4 that" % (T0 + 1000 * s) in out, out


def test_vcpu_records_removed_refuse(tmp_path):
    # a vCPU and its core absent from every group: the trace is consistent with itself, so only the header shows it
    v, out = verdict(tmp_path, head="QH v1 vcpus=501,502,503,504 reserved=2,3,4",
                     hedit=lambda i, t, r: r.update(_drop=1) if t in ("504", "c5") else None)
    assert v == "REFUSED" and "the group at utc %d lacks vCPU 504 that the header names" % T0 in out, out


def test_vcpu_affinity_or_core_name_missing_refuses(tmp_path):
    s = GAME_AT + 7
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(cpus="NA") if t == "503" and i == s else None)
    assert v == "REFUSED" and "lacks cpus (the vCPU's affinity)" in out, out
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.pop("cpus") if t == "503" and i == s else None)
    assert v == "REFUSED" and "lacks cpus (the vCPU's affinity)" in out, out
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.pop("cpu") if t == "c4" and i == s else None)
    assert v == "REFUSED" and out.endswith(" lacks cpu"), out


def test_host_group_record_twice_or_utc_disagreeing_refuses(tmp_path):
    # two groups written with one mono would merge, and the second's records would hide the first's
    s = GAME_AT + 7
    same = lambda i, t, r: r.update(mono=9000000000 + (s - 1) * 1000000000, utc=T0 + 1000 * (s - 1)) if i == s else None
    v, out = verdict(tmp_path, hedit=same)
    assert v == "REFUSED" and "a second V record for 501 in the group at mono" in out, out
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(utc=r["utc"] + 5) if t == "502" and i == s else None)
    assert v == "REFUSED" and "differs from the utc %d of its group" % (T0 + 1000 * s) in out, out


def test_host_utc_must_increase_with_mono(tmp_path):
    s = GAME_AT + 7
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(utc=T0 + 1000 * (s - 2)) if i == s else None)
    assert v == "REFUSED" and "host trace: utc does not increase with mono at utc %d" % (T0 + 1000 * (s - 2)) in out, out


def test_negative_field_refuses(tmp_path):
    # a negative paging rate would lower a ten-second integral; a negative counter reading has no meaning. Through
    # the CLI: exit 3 and the field named, while the same trace with the value at zero is judged (exit 0)
    run = lambda *a: subprocess.run([sys.executable, "-I", "-B", os.path.join(HERE, "ft_quiet.py")] + list(a),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    h = host_trace(str(tmp_path / "h.txt"))
    s = GAME_AT + 7
    for val, rc in (("-1", 3), ("0", 0)):
        g = guest_trace(str(tmp_path / "g.txt"), lambda i, r: r.update(prd=val) if i == s else None)
        p = run(g, h)
        assert p.returncode == rc, p.stdout
        assert ("prd='-1' is negative" in p.stdout) == (rc == 3), p.stdout
    g = guest_trace(str(tmp_path / "g.txt"))
    for val, rc in ((-1, 3), (0, 0)):
        h = host_trace(str(tmp_path / "h.txt"), lambda i, t, r: r.update(wait=val) if t == "501" and i == 0 else None)
        p = run(g, h)
        assert p.returncode == rc, p.stdout
        assert ("wait='-1' is negative" in p.stdout) == (rc == 3), p.stdout


def test_unknown_record_kinds_refuse(tmp_path):
    g = guest_trace(str(tmp_path / "g.txt"))
    h = host_trace(str(tmp_path / "h.txt"))
    gl = open(g).read().split("\n")
    gl[1 + GAME_AT + 7] = "g" + gl[1 + GAME_AT + 7][1:]            # a G line inside the window, mis-kinded
    open(str(tmp_path / "g2.txt"), "w").write("\n".join(gl))
    v, lines = Q.judge(str(tmp_path / "g2.txt"), h)
    assert v == "REFUSED" and "is not a G record: 'g utc=" in "\n".join(lines), lines
    hl = open(h).read().split("\n")
    k = [j for j, ln in enumerate(hl) if ln.startswith("C utc=%d " % (T0 + 1000 * (GAME_AT + 7)))][0]
    hl[k] = "c" + hl[k][1:]
    open(str(tmp_path / "h2.txt"), "w").write("\n".join(hl))
    v, lines = Q.judge(g, str(tmp_path / "h2.txt"))
    assert v == "REFUSED" and "is not a V, C or X record: 'c utc=" in "\n".join(lines), lines


def test_busy_counter_backwards_refuses(tmp_path):
    s = GAME_AT + 7
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(busy=r["busy"] - 1000000000) if t == "c3" and i >= s else None)
    assert v == "REFUSED" and "the busy counter of reserved core 3 goes backwards at utc %d" % (T0 + 1000 * s) in out, out


def test_frozen_busy_counter_refuses(tmp_path):
    # every reserved core's busy frozen: d busy - d run reads below zero, which is a quiet value
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(busy=0) if t.startswith("c") else None)
    assert v == "REFUSED" and "the busy counter of reserved core 2 does not advance at utc" in out, out
    assert "pinned to it ran 0.900 core (a frozen counter)" in out, out

    # THE RULE (ruling R6-A3.11.153 (4)) is per interval, not per window: a reserved core's busy counter that does not
    # advance in an interval refuses as frozen when the vCPUs pinned to that core ran more than RESERVED_MAX (0.05
    # core) in the same interval. At or below that runtime a zero reading is inside the counter's own granularity
    # and is read as it stands. Both sides of the bound, each away from its float edge:
    def idle5(per_sample_ns):
        def edit(i, t, r):
            if t == "504":
                r["run"] = i * per_sample_ns
            if t == "c5":
                r["busy"] = 0
        return edit
    v, out = verdict(tmp_path, hedit=idle5(10000000))      # 0.01 core: the counter may show no tick
    assert v == "PASS", out
    v, out = verdict(tmp_path, hedit=idle5(40000000))      # 0.04 core: still below the bound
    assert v == "PASS", out
    v, out = verdict(tmp_path, hedit=idle5(60000000))      # 0.06 core: above it, a live counter must have moved
    assert v == "REFUSED" and "the busy counter of reserved core 5 does not advance at utc" in out, out
    assert "pinned to it ran 0.060 core (a frozen counter)" in out, out


def test_fixture_must_last_ten_seconds(tmp_path):
    # item 5: a one-second fixture (two samples with rising runtime and 20 percent wait, then quiet intervals)
    v, out = verdict(tmp_path, fixture=(10, 11))
    assert v == "REFUSED" and "the contention fixture lasted 1.0 s (utc %d to %d): it must last ten seconds" \
        % (T0 + 10000, T0 + 11000) in out, out
    v, out = verdict(tmp_path, fixture=(10, 19))
    assert v == "REFUSED" and "the contention fixture lasted 9.0 s" in out, out
    v, out = verdict(tmp_path, fixture=(10, 20))     # the negative control: ten seconds
    assert v == "PASS" and "QUIET contention fixture PASS: 10.0 s, vCPU 501" in out, out


def test_fixture_must_be_covered_by_host_samples(tmp_path):
    # item 5: no host sample at or before the fixture's start, then gaps across its start and its stop
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if i <= 10 else None)
    assert v == "REFUSED" and "host trace does not cover the contention fixture's start: no sample at or before " \
        "utc %d" % (T0 + 10000) in out, out
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if 8 <= i <= 10 else None)
    assert v == "REFUSED" and "host trace (fixture): an interval of 4.000 s" in out, out
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if 20 <= i <= 22 else None)
    assert v == "REFUSED" and "host trace (fixture): an interval of 4.000 s" in out, out
    # the negative control: one sample missing at the start leaves a two-second interval
    v, out = verdict(tmp_path, hedit=lambda i, t, r: r.update(_drop=1) if i == 10 else None)
    assert v == "PASS", out
