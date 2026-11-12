#!/usr/bin/env bash
# ft_quiet_host.sh <qemu pid> <out file> <stop file> <max seconds> <reserved cpus|-> [<fixture cpu> <fixture seconds>]
#
# The host half of the quiet trace (method-v52.md section 6), for the hypervisor host: ZAP or Sid runs it, never a
# session on the VM. Every argument is given; none has a default, and nothing in the trace names a machine.
#   <qemu pid>        the measured VM's QEMU process; its vCPU threads are the tasks whose comm is "CPU <n>/KVM";
#   <reserved cpus>   the host cores reserved for those vCPUs, comma-separated, or "-" for none (ft_quiet.py refuses a
#                     trace that names no reserved core: the reserved-core rule then has no evidence);
#   fixture           optional: before the first sample, the ten-second pinned contention fixture: one CPU burner
#                     pinned to <fixture cpu> (taskset) for <fixture seconds>, killed by its captured pid, between
#                     an "X fixture=start" and an "X fixture=stop" line; sampling runs throughout. ft_quiet.py refuses
#                     a fixture shorter than ten seconds.
# Output: "QH v1 vcpus=<tid,...> reserved=<cpu,...|->", the sets every group must hold a record for, then each second
# one group sharing one utc and mono: per vCPU
#   V utc=<epoch ms> mono=<ns> tid=<tid> cpus=<Cpus_allowed_list> run=<schedstat run ns> wait=<schedstat wait ns>
# and per reserved core
#   C utc=<epoch ms> mono=<ns> cpu=<n> busy=<ns from /proc/stat: user + nice + system + irq + softirq + steal>
# busy leaves out idle and iowait, and leaves out guest and guest_nice because the kernel already counts guest time
# inside user and nice. A core whose /proc/stat line is missing or shorter than eight counters is written busy=NA.
# A vCPU whose schedstat or status cannot be read is written run=NA wait=NA or cpus=NA; ft_quiet.py refuses NA.
# mono is the host's CLOCK_REALTIME in ns (date +%s%N); ft_quiet.py refuses an interval that does not advance or
# exceeds two seconds. Stops at the stop file or after <max seconds> groups. Exit 0 written; 2 usage; 3 no vCPU
# thread found (no host evidence). FT_QUIET_PROC_ROOT re-roots /proc (a test feeds its own /proc/stat text there)
# and FT_QUIET_TEST=1 replaces the burner by a sleep: tests only, never set on a real run.
set -u
[ "$#" = 5 ] || [ "$#" = 7 ] || { echo "usage: ft_quiet_host.sh <qemu pid> <out> <stop file> <max seconds> <reserved cpus|-> [<fixture cpu> <fixture seconds>]" >&2; exit 2; }
QPID=$1; OUT=$2; STOP=$3; MAX=$4; RES=$5; FCPU=${6:-}; FSEC=${7:-}
case "$QPID$MAX$FCPU$FSEC" in *[!0-9]*) echo "ft_quiet_host.sh: pid, seconds and cpu must be numbers" >&2; exit 2;; esac
[[ "$RES" =~ ^(-|[0-9]+(,[0-9]+)*)$ ]] || { echo "ft_quiet_host.sh: reserved cpus must be a comma list of numbers or -" >&2; exit 2; }
P=${FT_QUIET_PROC_ROOT:-}/proc
HZ=$(getconf CLK_TCK)
vcpus=()
for d in "$P/$QPID"/task/*; do
  [ -r "$d/comm" ] || continue
  case "$(cat "$d/comm")" in "CPU "*/KVM) vcpus+=("${d##*/}");; esac
done
[ "${#vcpus[@]}" -gt 0 ] || { echo "ft_quiet_host.sh: no vCPU thread under $P/$QPID/task (no host evidence)" >&2; exit 3; }
IFS=, read -r -a cores <<< "$([ "$RES" = - ] && echo "" || echo "$RES")"
now() { local n; n=$(date +%s%N); echo "utc=$((n / 1000000)) mono=$n"; }
group() {
  local t tid st run wait rest c line
  t=$(now)
  for tid in "${vcpus[@]}"; do
    read -r run wait rest < "$P/$QPID/task/$tid/schedstat" || { run=NA; wait=NA; }
    st=$(sed -n 's/^Cpus_allowed_list:[[:space:]]*//p' "$P/$QPID/task/$tid/status" 2>/dev/null)
    echo "V $t tid=$tid cpus=${st:-NA} run=$run wait=$wait"
  done
  for c in "${cores[@]}"; do
    line=$(grep "^cpu$c " "$P/stat")
    # $2.. are user nice system idle iowait irq softirq steal guest guest_nice: busy = user + nice + system + irq +
    # softirq + steal, in ns; a missing line (grep found none) or one shorter than eight counters is busy=NA
    echo "$line" | awk -v t="$t" -v c="$c" -v hz="$HZ" '{ if ($1 != "cpu" c || NF < 9) { printf "C %s cpu=%s busy=NA\n", t, c; next }
      printf "C %s cpu=%s busy=%.0f\n", t, c, ($2 + $3 + $4 + $7 + $8 + $9) * 1e9 / hz }'
  done
}
BURN=""
cleanup() { [ -n "$BURN" ] && kill "$BURN" 2>/dev/null; wait "$BURN" 2>/dev/null; BURN=""; }
trap cleanup EXIT
{
  echo "QH v1 vcpus=$(IFS=,; echo "${vcpus[*]}") reserved=$RES"
  i=0
  if [ -n "$FCPU" ]; then
    group; i=$((i + 1))
    echo "X $(now) fixture=start"
    if [ "${FT_QUIET_TEST:-}" = 1 ]; then sleep "$FSEC" & else taskset -c "$FCPU" sh -c 'while :; do :; done' & fi
    BURN=$!
    for s in $(seq 1 "$FSEC"); do sleep 1; group; i=$((i + 1)); done
    cleanup
    echo "X $(now) fixture=stop"
  fi
  while [ "$i" -lt "$MAX" ] && [ ! -e "$STOP" ]; do
    group; i=$((i + 1))
    sleep 1
  done
} > "$OUT"
exit 0
