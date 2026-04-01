#!/usr/bin/env bash
# Prepare the tmpfs workdir without taking authority away from the disk DBs.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}"
TMP_ROOT="${TMP_ROOT:-/run/cypherclaw-tmp}"
WORKDIR_NAME="${WORKDIR_NAME:-cypherclaw-work}"
WORKDIR_PARENT="${TMP_ROOT}/workdir"
WORKDIR="${WORKDIR_PARENT}/${WORKDIR_NAME}"
STATE_DB="${PROJECT_ROOT}/.sdp/state.db"
OBSERVATORY_DB="${PROJECT_ROOT}/.promptclaw/observatory.db"
SDP_CONFIG_SOURCE="${SDP_CONFIG_SOURCE:-${PROJECT_ROOT}/sdp.toml}"
GIT_BIN="${GIT_BIN:-git}"

log() {
  printf '[init_workdir] %s\n' "$*"
}

require_path() {
  local path="$1"
  local label="$2"
  if [[ ! -e "${path}" ]]; then
    printf 'missing %s at %s\n' "${label}" "${path}" >&2
    exit 1
  fi
}

link_path() {
  local source="$1"
  local target="$2"
  mkdir -p "$(dirname "${target}")"
  rm -rf "${target}"
  ln -s "${source}" "${target}"
}

refresh_clone() {
  if [[ ! -d "${WORKDIR}/.git" ]]; then
    rm -rf "${WORKDIR}"
    "${GIT_BIN}" clone --quiet "${PROJECT_ROOT}" "${WORKDIR}"
    return
  fi

  "${GIT_BIN}" -C "${WORKDIR}" remote set-url origin "${PROJECT_ROOT}"
  "${GIT_BIN}" -C "${WORKDIR}" fetch --quiet origin --prune
  local branch
  branch="$("${GIT_BIN}" -C "${WORKDIR}" rev-parse --abbrev-ref HEAD)"
  if [[ -n "${branch}" ]] && "${GIT_BIN}" -C "${WORKDIR}" show-ref --verify --quiet "refs/remotes/origin/${branch}"; then
    "${GIT_BIN}" -C "${WORKDIR}" reset --hard --quiet "origin/${branch}"
  else
    "${GIT_BIN}" -C "${WORKDIR}" reset --hard --quiet "$("${GIT_BIN}" -C "${PROJECT_ROOT}" rev-parse HEAD)"
  fi
  "${GIT_BIN}" -C "${WORKDIR}" clean -fdq
}

main() {
  require_path "${PROJECT_ROOT}/.git" "git repo"
  require_path "${STATE_DB}" "state.db"
  require_path "${OBSERVATORY_DB}" "observatory.db"
  require_path "${SDP_CONFIG_SOURCE}" "sdp config"

  mkdir -p "${WORKDIR_PARENT}" "${TMP_ROOT}/cache" "${TMP_ROOT}/workspace"
  refresh_clone

  mkdir -p "${WORKDIR}/.sdp" "${WORKDIR}/.promptclaw"
  link_path "${STATE_DB}" "${WORKDIR}/.sdp/state.db"
  link_path "${OBSERVATORY_DB}" "${WORKDIR}/.promptclaw/observatory.db"
  link_path "${SDP_CONFIG_SOURCE}" "${WORKDIR}/sdp.toml"

  log "workdir ready at ${WORKDIR}"
  log "state authority -> ${STATE_DB}"
  log "observatory authority -> ${OBSERVATORY_DB}"
}

main "$@"
