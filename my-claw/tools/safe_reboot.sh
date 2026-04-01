#!/usr/bin/env bash
# Safe reboot workflow with checkpoint, maintenance, and resume validation.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}"
TMP_ROOT="${TMP_ROOT:-/run/cypherclaw-tmp}"
WORKDIR_NAME="${WORKDIR_NAME:-cypherclaw-work}"
WORKDIR="${WORKDIR:-${TMP_ROOT}/workdir/${WORKDIR_NAME}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"
REBOOT_BIN="${REBOOT_BIN:-reboot}"
DRY_RUN=0
ACTOR="operator"
REASON="safe reboot"
CHECKPOINT_PATH=""

usage() {
  cat <<'EOF'
Usage:
  safe_reboot.sh prepare [--dry-run] [--actor NAME] [--reason TEXT]
  safe_reboot.sh resume --checkpoint PATH [--dry-run] [--actor NAME]
EOF
}

run_cmd() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    printf '[safe_reboot dry-run] %s\n' "$*"
    "$@" 2>/dev/null || true
    return 0
  fi
  "$@"
}

prepare() {
  "${PYTHON_BIN}" "${SCRIPT_DIR}/maintenance_mode.py" \
    --project-root "${PROJECT_ROOT}" \
    enter \
    --reason "${REASON}" \
    --actor "${ACTOR}" >/dev/null

  CHECKPOINT_PATH="$("${PYTHON_BIN}" "${SCRIPT_DIR}/runtime_checkpoint.py" --project-root "${PROJECT_ROOT}")"
  run_cmd "${SYSTEMCTL_BIN}" stop cypherclaw-sdp-runner.service
  run_cmd "${SYSTEMCTL_BIN}" stop cypherclaw.service

  if [[ "${DRY_RUN}" == "1" ]]; then
    printf '%s\n' "${CHECKPOINT_PATH}"
    return 0
  fi

  exec "${REBOOT_BIN}"
}

resume() {
  if [[ -z "${CHECKPOINT_PATH}" ]]; then
    printf 'resume requires --checkpoint PATH\n' >&2
    exit 2
  fi

  "${PYTHON_BIN}" "${SCRIPT_DIR}/preflight.py" \
    --project-root "${PROJECT_ROOT}" \
    --workdir "${WORKDIR}" \
    --checkpoint "${CHECKPOINT_PATH}" >/dev/null

  run_cmd "${SYSTEMCTL_BIN}" start cypherclaw-bootstrap.service
  run_cmd "${SYSTEMCTL_BIN}" start cypherclaw.service
  run_cmd "${SYSTEMCTL_BIN}" start cypherclaw-sdp-runner.service

  "${PYTHON_BIN}" "${SCRIPT_DIR}/maintenance_mode.py" \
    --project-root "${PROJECT_ROOT}" \
    exit \
    --actor "${ACTOR}" >/dev/null
}

main() {
  if [[ "$#" -lt 1 ]]; then
    usage >&2
    exit 2
  fi

  local mode="$1"
  shift

  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --dry-run)
        DRY_RUN=1
        ;;
      --actor)
        shift
        ACTOR="${1:-}"
        ;;
      --reason)
        shift
        REASON="${1:-}"
        ;;
      --checkpoint)
        shift
        CHECKPOINT_PATH="${1:-}"
        ;;
      *)
        printf 'unknown argument: %s\n' "$1" >&2
        exit 2
        ;;
    esac
    shift
  done

  case "${mode}" in
    prepare)
      prepare
      ;;
    resume)
      resume
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
