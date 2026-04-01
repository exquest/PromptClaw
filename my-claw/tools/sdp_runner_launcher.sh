#!/usr/bin/env bash
# Run sdp-cli under preflight and maintenance gates.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}"
TMP_ROOT="${TMP_ROOT:-/run/cypherclaw-tmp}"
WORKDIR_NAME="${WORKDIR_NAME:-cypherclaw-work}"
WORKDIR="${WORKDIR:-${TMP_ROOT}/workdir/${WORKDIR_NAME}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SDP_BIN="${SDP_BIN:-sdp-cli}"

maintenance_active() {
  local active
  active="$(
    "${PYTHON_BIN}" "${SCRIPT_DIR}/maintenance_mode.py" --project-root "${PROJECT_ROOT}" status \
      | "${PYTHON_BIN}" -c 'import json,sys; data=json.load(sys.stdin); print("1" if data.get("active") else "0")'
  )"
  [[ "${active}" == "1" ]]
}

main() {
  if maintenance_active; then
    printf 'refusing to start runner while maintenance mode is active\n' >&2
    exit 75
  fi

  "${PYTHON_BIN}" "${SCRIPT_DIR}/preflight.py" \
    --project-root "${PROJECT_ROOT}" \
    --workdir "${WORKDIR}" >/dev/null

  cd "${WORKDIR}"
  exec "${SDP_BIN}" run "$@"
}

main "$@"
