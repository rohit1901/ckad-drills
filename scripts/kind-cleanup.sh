#!/usr/bin/env bash
# kind-cleanup.sh
#
# Tears down the local kind environment used by ckad-drills.
# - deletes the named kind cluster (if it exists)
# - removes its kubectl context entry (best effort)
# - reports any *other* kind clusters still present, so nothing is left behind silently
# - with --all, deletes every kind cluster on the machine
#
# Usage:
#   scripts/kind-cleanup.sh [cluster-name]        # delete just that cluster
#   scripts/kind-cleanup.sh --all                 # delete every kind cluster
#
# Defaults:
#   cluster-name = ckad-practice

set -euo pipefail

MODE="single"
CLUSTER_NAME="ckad-practice"

if [ "${1:-}" = "--all" ] || [ "${1:-}" = "-a" ]; then
  MODE="all"
elif [ -n "${1:-}" ]; then
  CLUSTER_NAME="$1"
fi

if [ -t 1 ]; then
  C_RED=$'\033[31m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'
  C_BOLD=$'\033[1m'
  C_RESET=$'\033[0m'
else
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_RESET=""
fi

info()  { printf "%s[info]%s %s\n"  "${C_BLUE}"   "${C_RESET}" "$*"; }
ok()    { printf "%s[ ok ]%s %s\n"  "${C_GREEN}"  "${C_RESET}" "$*"; }
warn()  { printf "%s[warn]%s %s\n"  "${C_YELLOW}" "${C_RESET}" "$*" >&2; }
fail()  { printf "%s[fail]%s %s\n"  "${C_RED}"    "${C_RESET}" "$*" >&2; }

die() {
  fail "$1"
  if [ "${2:-}" != "" ]; then
    printf "        %sHint:%s %s\n" "${C_BOLD}" "${C_RESET}" "$2" >&2
  fi
  exit 1
}

# ---- preflight -------------------------------------------------------------
if ! command -v kind >/dev/null 2>&1; then
  die "Required tool 'kind' was not found on your PATH." \
      "Install kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
fi

if ! command -v docker >/dev/null 2>&1; then
  die "Required tool 'docker' was not found on your PATH." \
      "Install Docker and make sure 'docker' is on your PATH."
fi

if ! docker info >/dev/null 2>&1; then
  die "Cannot talk to the Docker daemon." \
      "Start Docker Desktop (macOS/Windows) or 'sudo systemctl start docker' (Linux), then retry."
fi

# Helper: delete one cluster + its kubectl context entries + stray containers.
delete_one_cluster() {
  local name="$1"

  info "Deleting kind cluster '${name}'..."
  if ! kind delete cluster --name "${name}"; then
    fail "Failed to delete kind cluster '${name}'."
    warn "Inspect 'docker ps -a' for leftover containers and remove them manually if needed."
    return 1
  fi
  ok "kind cluster '${name}' deleted."

  if command -v kubectl >/dev/null 2>&1; then
    local kctx="kind-${name}"
    if kubectl config get-contexts -o name 2>/dev/null | grep -Fxq "${kctx}"; then
      info "Removing leftover kubectl context '${kctx}'..."
      kubectl config delete-context "${kctx}" >/dev/null 2>&1 || \
        warn "Could not remove kubectl context '${kctx}'. You can remove it manually."
      kubectl config delete-cluster "${kctx}" >/dev/null 2>&1 || true
      kubectl config delete-user    "${kctx}" >/dev/null 2>&1 || true
      ok "kubectl context for '${name}' cleaned up."
    fi
  fi

  local stray
  stray="$(docker ps -a --filter "label=io.x-k8s.kind.cluster=${name}" --format '{{.ID}}' 2>/dev/null || true)"
  if [ -n "${stray}" ]; then
    warn "Detected leftover kind containers for cluster '${name}':"
    docker ps -a --filter "label=io.x-k8s.kind.cluster=${name}" || true
    info "Removing leftover containers..."
    # shellcheck disable=SC2086
    docker rm -f ${stray} >/dev/null 2>&1 || \
      warn "Some containers could not be removed automatically. Please remove them manually."
  fi
}

# ---- single-cluster mode ---------------------------------------------------
if [ "${MODE}" = "single" ]; then
  info "Looking for kind cluster '${CLUSTER_NAME}'..."
  if kind get clusters 2>/dev/null | grep -Fxq "${CLUSTER_NAME}"; then
    delete_one_cluster "${CLUSTER_NAME}" || exit 1
  else
    warn "No kind cluster named '${CLUSTER_NAME}' was found; nothing to delete."
  fi

  # Always tell the user about any *other* kind clusters still on the machine.
  REMAINING="$(kind get clusters 2>/dev/null || true)"
  if [ -n "${REMAINING}" ]; then
    printf "\n"
    warn "Other kind clusters are still present on this machine:"
    printf "%s\n" "${REMAINING}" | sed 's/^/         - /'
    printf "        %sHint:%s remove a specific one with 'make kind-down KIND_CLUSTER_NAME=<name>',\n" "${C_BOLD}" "${C_RESET}"
    printf "              or wipe them all with 'make kind-nuke' (or 'scripts/kind-cleanup.sh --all').\n"
  fi
fi

# ---- all-clusters mode -----------------------------------------------------
if [ "${MODE}" = "all" ]; then
  info "Listing all kind clusters..."
  CLUSTERS="$(kind get clusters 2>/dev/null || true)"
  if [ -z "${CLUSTERS}" ]; then
    warn "No kind clusters found; nothing to delete."
  else
    printf "Found:\n%s\n" "${CLUSTERS}" | sed 's/^/  /'
    FAILED=0
    while IFS= read -r name; do
      [ -z "${name}" ] && continue
      delete_one_cluster "${name}" || FAILED=$((FAILED + 1))
    done <<EOF
${CLUSTERS}
EOF
    if [ "${FAILED}" -ne 0 ]; then
      die "${FAILED} cluster(s) failed to delete cleanly." \
          "Re-run the script, or use 'kind delete cluster --name <name>' manually."
    fi
  fi
fi

printf "\n%s%sCKAD kind environment cleanup complete.%s\n" "${C_BOLD}" "${C_GREEN}" "${C_RESET}"
