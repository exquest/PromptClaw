#!/usr/bin/env bash
# Run sdp-cli under preflight and maintenance gates.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}"
TMP_ROOT="${TMP_ROOT:-/run/cypherclaw-tmp}"
WORKDIR_NAME="${WORKDIR_NAME:-cypherclaw-work}"
WORKDIR="${WORKDIR:-${TMP_ROOT}/workdir/${WORKDIR_NAME}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DEFAULT_SDP_BIN="$(command -v sdp-cli 2>/dev/null || true)"
if [[ -z "${DEFAULT_SDP_BIN}" && -x "${HOME}/.local/bin/sdp-cli" ]]; then
  DEFAULT_SDP_BIN="${HOME}/.local/bin/sdp-cli"
fi
SDP_BIN="${SDP_BIN:-${DEFAULT_SDP_BIN:-sdp-cli}}"

configure_pythonpath() {
  if [[ -n "${PYTHONPATH:-}" ]]; then
    return
  fi

  local candidate
  for candidate in \
    "${PROJECT_ROOT}/../sdp-cli/src" \
    "${HOME}/sdp-cli/src"
  do
    if [[ -d "${candidate}" ]]; then
      export PYTHONPATH="$(cd -- "${candidate}" && pwd)"
      return
    fi
  done
}

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

  if [[ "${SDP_BIN}" == */* ]]; then
    if [[ ! -x "${SDP_BIN}" ]]; then
      printf 'sdp-cli launcher not executable: %s\n' "${SDP_BIN}" >&2
      exit 127
    fi
  elif ! command -v "${SDP_BIN}" >/dev/null 2>&1; then
    printf 'sdp-cli not found on PATH\n' >&2
    exit 127
  fi

  configure_pythonpath

  "${PYTHON_BIN}" "${SCRIPT_DIR}/preflight.py" \
    --repair-run-lock \
    --project-root "${PROJECT_ROOT}" \
    --workdir "${WORKDIR}" >/dev/null

  cd "${WORKDIR}"
  exec "${SDP_BIN}" run "$@"
}

main "$@"
