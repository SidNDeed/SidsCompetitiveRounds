#!/bin/bash
# /usr/local/bin/cc-snapshot-wrapper.sh
# Runs on the Proxmox host (NOT the LXC). Restricts the ccsnap SSH key to snapshot operations on CT <container id> only.
# Invoked via authorized_keys: command="/usr/local/bin/cc-snapshot-wrapper.sh"
#
# Install on the Proxmox HOST (<snapshot host> or wherever pve runs):
#   scp scripts/cc-snapshot-wrapper.sh root@<snapshot host>:/usr/local/bin/
#   ssh root@<snapshot host> "chmod 755 /usr/local/bin/cc-snapshot-wrapper.sh"

set -euo pipefail

CTID=<container id>
LOG="<log file>"
MAX_AUTO_SNAPSHOTS=10
MAX_DELETES_PER_RUN=10
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(ts) $*" >> "$LOG"; }

prune_snapshots() {
  local mode="$1"
  local report_stdout="${2:-false}"
  local listing found excess delete_count pruned kept old delete_status i
  local -a snapshots=()

  listing=$(sudo pct listsnapshot "$CTID")
  # Scan every field because pct renders a whitespace-indented tree (`-> cc_...).
  # The exact auto-name shape is the deletion boundary: `current`, descriptions,
  # and hand-made snapshots can never enter this list. Sort explicitly on the
  # fixed-width trailing timestamp so variable-length labels cannot decide age;
  # YYYYMMDD_HHMMSS sorts chronologically as text.
  mapfile -t snapshots < <(
    printf '%s\n' "$listing" \
      | awk '{
          for (i = 1; i <= NF; i++) {
            if ($i ~ /^cc_[A-Za-z0-9_-]+_[0-9]{8}_[0-9]{6}$/) {
              stamp = substr($i, length($i) - 14)
              print stamp, $i
            }
          }
        }' \
      | sort -k1,1 \
      | awk '{print $2}'
  )

  found=${#snapshots[@]}
  excess=$((found - MAX_AUTO_SNAPSHOTS))
  if [ "$excess" -lt 0 ]; then excess=0; fi
  delete_count="$excess"
  if [ "$delete_count" -gt "$MAX_DELETES_PER_RUN" ]; then
    delete_count="$MAX_DELETES_PER_RUN"
  fi

  # pct supports removing snapshots from its tree, but each removal may reclaim
  # or merge backing storage. Draining a 71-snapshot backlog in one forced-command
  # session would create an unnecessarily long, heavy operation. Ten oldest per
  # run bounds storage churn and SSH time; repeat prune-snapshots deliberately
  # until the summary reports kept=MAX_AUTO_SNAPSHOTS.
  pruned=0
  for ((i = 0; i < delete_count; i++)); do
    old="${snapshots[$i]}"
    if [ "$mode" = "dry-run" ]; then
      echo "WOULD delete: $old"
      log "prune dry-run would delete: $old"
      continue
    fi

    log "pruning old snapshot: $old"
    delete_status=0
    sudo pct delsnapshot "$CTID" "$old" || { delete_status=$?; true; }
    if [ "$delete_status" -eq 0 ]; then
      pruned=$((pruned + 1))
      log "prune success: $old"
      if [ "$report_stdout" = "true" ]; then echo "deleted: $old"; fi
    else
      log "prune FAILED (exit=$delete_status): $old"
      echo "FAILED to delete: $old (exit=$delete_status)" >&2
    fi
  done

  kept=$((found - pruned))
  if [ "$mode" = "dry-run" ]; then
    log "prune summary: found=$found pruned=0 kept=$found would_prune=$delete_count cap=$MAX_DELETES_PER_RUN"
    echo "summary: found=$found pruned=0 kept=$found would_prune=$delete_count"
  else
    log "prune summary: found=$found pruned=$pruned kept=$kept requested=$delete_count cap=$MAX_DELETES_PER_RUN"
    if [ "$report_stdout" = "true" ]; then
      echo "summary: found=$found pruned=$pruned kept=$kept"
    fi
  fi
}

CMD="${SSH_ORIGINAL_COMMAND:-}"
VERB="${CMD%%:*}"
ARG="${CMD#*:}"
[ "$VERB" = "$ARG" ] && ARG=""

log "invoked: $CMD"

case "$VERB" in
  snapshot)
    # $ARG is the label. Sanitize aggressively.
    LABEL=$(echo "$ARG" | tr -c 'a-zA-Z0-9_-' '_' | cut -c1-40)
    if [ -z "$LABEL" ]; then
      echo "label required" >&2
      exit 1
    fi
    NAME="cc_${LABEL}_$(date +%Y%m%d_%H%M%S)"
    log "snapshotting CT $CTID as $NAME"
    sudo pct snapshot "$CTID" "$NAME" --description "auto snapshot: $ARG"
    echo "$NAME"

    # Use the same bounded pruning path as the standalone maintenance verb.
    prune_snapshots apply false
    ;;

  prune-snapshots)
    # Empty/apply is an explicit destructive invocation. dry-run previews it;
    # an unknown mode fails safe to dry-run instead of guessing.
    case "$ARG" in
      ""|apply) PRUNE_MODE="apply" ;;
      dry-run) PRUNE_MODE="dry-run" ;;
      *)
        echo "Unrecognised prune mode '$ARG'; defaulting to dry-run" >&2
        log "unrecognised prune mode '$ARG'; defaulting to dry-run"
        PRUNE_MODE="dry-run"
        ;;
    esac
    prune_snapshots "$PRUNE_MODE" true
    ;;

  list-snapshots)
    sudo pct listsnapshot "$CTID"
    ;;

  rollback)
    # Reverts CT <container id> to the named snapshot. Destructive — requires explicit call.
    if [ -z "$ARG" ]; then
      echo "snapshot name required" >&2
      exit 1
    fi
    # Only allow rolling back to our own cc_* snapshots
    if ! [[ "$ARG" =~ ^cc_[a-zA-Z0-9_-]+_[0-9]{8}_[0-9]{6}$ ]]; then
      echo "Only cc_*_<timestamp> snapshots can be rolled back via this key" >&2
      log "REJECTED rollback: $ARG"
      exit 1
    fi
    # Verify it exists
    if ! pct listsnapshot "$CTID" | grep -q "$ARG"; then
      echo "Snapshot not found: $ARG" >&2
      exit 1
    fi
    log "rolling back CT $CTID to $ARG"
    sudo pct rollback "$CTID" "$ARG"
    log "rollback complete, CT started"
    ;;

  status)
    sudo pct status "$CTID"
    sudo pct config "$CTID" | head -20
    ;;

  *)
    echo "Command not allowed: $CMD" >&2
    log "REJECTED: $CMD"
    exit 1
    ;;
esac
