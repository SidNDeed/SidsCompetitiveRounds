#!/usr/bin/env bash
# ft_arm_text.sh [--kind] <profile>: the one table of the FrameTime sentinel's arm profiles (lane B11, V6). It writes
# nothing but its standard output and touches no file.
#
#   ft_arm_text.sh <profile>          prints the sentinel text for BepInEx/frametime/arm, one key=value a line, each
#                                     line ending in a newline (no carriage return)
#   ft_arm_text.sh --kind <profile>   prints the profile's launch kind: menu (the menu self-check, ft_vm_launch.ps1
#                                     -Mode menu, s0_gate -Launch 1) or match (-Mode match, -Launch 2)
#
# The profiles (keys and values are the plugin's: FtConfig.cs Load, FtClock.cs and FtSpan.cs SetMutants for k_mutant):
#   menu       the menu self-check of 200 segments, the switch on none           kind menu
#   match      a sitting as built (force absent), the VM seat's seed 2           kind match
#   match-on   the same sitting with force ON (sitting V)                        kind match
#   boot       the control boot: the menu self-check of 4 segments              kind menu
#   boot-k1    the control boot with the control switch k_mutant at k1           kind menu
#   boot-k2    the same at k2                                                    kind menu
#   boot-k3    the same at k3                                                    kind menu
# ft_vm_install.sh arm and ft_vm_leased.sh take their sentinel text and their kind from here and hold no copy.
# An unknown, empty or missing profile, or an extra argument: nothing on standard output, one line on standard error,
# exit 2.
set -u
kind=0
if [ "${1:-}" = "--kind" ]; then kind=1; shift; fi
refuse() { echo "ft_arm_text.sh: $* (usage: ft_arm_text.sh [--kind] <profile>; the profiles are this file's table)" >&2; exit 2; }
[ "$#" -eq 1 ] || refuse "one profile wanted, $# given"
p="$1"
case "$p" in
  menu)                    k=menu;  L=(seed=1 force=none menu=1);;
  match)                   k=match; L=(seed=2 f18=A);;
  match-on)                k=match; L=(seed=2 f18=A force=ON);;
  boot)                    k=menu;  L=(seed=1 force=none menu=1 menu_segments=4);;
  boot-k1|boot-k2|boot-k3) k=menu;  L=(seed=1 force=none menu=1 menu_segments=4 "k_mutant=${p#boot-}");;
  *) refuse "unknown profile '$p'";;
esac
if [ "$kind" = 1 ]; then printf '%s\n' "$k"; else printf '%s\n' "${L[@]}"; fi
exit 0
