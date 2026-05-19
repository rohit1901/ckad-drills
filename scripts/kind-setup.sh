#!/usr/bin/env bash
# kind-setup.sh
#
# Bootstraps a local Kubernetes environment for ckad-drills using kind.
# - verifies required tools are installed
# - verifies the Docker daemon is reachable
# - creates a kind cluster from kind-config.yaml (if not already present)
# - switches kubectl to the new context
# - waits for the cluster nodes to become Ready
#
# Usage:
#   scripts/kind-setup.sh [cluster-name] [path-to-kind-config.yaml]
#
# Defaults:
#   cluster-name        = ckad-practice
#   kind-config.yaml    = ./kind-config.yaml (relative to repo root)

set -euo pipefail

CLUSTER_NAME="${1:-ckad-practice}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
KIND_CONFIG="${2:-${REPO_ROOT}/kind-config.yaml}"

# ---- pretty printing -------------------------------------------------------
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

# ---- preflight: required tools --------------------------------------------
require_tool() {
  local tool="$1"
  local hint="$2"
  if ! command -v "${tool}" >/dev/null 2>&1; then
    die "Required tool '${tool}' was not found on your PATH." "${hint}"
  fi
}

info "Checking required tools..."
require_tool docker  "Install Docker Desktop or Docker Engine and make sure 'docker' is on your PATH."
require_tool kind    "Install kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
require_tool kubectl "Install kubectl: https://kubernetes.io/docs/tasks/tools/"
ok "docker, kind, and kubectl are available."

# ---- preflight: docker daemon ---------------------------------------------
info "Checking Docker daemon..."
if ! docker info >/dev/null 2>&1; then
  die "Cannot talk to the Docker daemon." \
      "Start Docker Desktop (macOS/Windows) or 'sudo systemctl start docker' (Linux), then retry."
fi
ok "Docker daemon is reachable."

# ---- preflight: kind config file ------------------------------------------
info "Checking kind config..."
if [ ! -f "${KIND_CONFIG}" ]; then
  die "kind config file not found at: ${KIND_CONFIG}" \
      "Pass an explicit path as the second argument, or create kind-config.yaml in the repo root."
fi
ok "Using kind config: ${KIND_CONFIG}"

# ---- check if cluster already exists --------------------------------------
info "Checking existing kind clusters..."
if kind get clusters 2>/dev/null | grep -Fxq "${CLUSTER_NAME}"; then
  ok "kind cluster '${CLUSTER_NAME}' already exists; skipping creation."
else
  info "Creating kind cluster '${CLUSTER_NAME}'..."
  if ! kind create cluster --name "${CLUSTER_NAME}" --config "${KIND_CONFIG}"; then
    die "Failed to create kind cluster '${CLUSTER_NAME}'." \
        "Check the output above. Common causes: low Docker resources, port conflicts, or a stale cluster (try: scripts/kind-cleanup.sh ${CLUSTER_NAME})."
  fi
  ok "kind cluster '${CLUSTER_NAME}' created."
fi

# ---- switch kubectl context -----------------------------------------------
KCTX="kind-${CLUSTER_NAME}"
info "Switching kubectl context to '${KCTX}'..."
if ! kubectl config use-context "${KCTX}" >/dev/null 2>&1; then
  die "Could not switch kubectl context to '${KCTX}'." \
      "Run 'kubectl config get-contexts' to inspect what's available."
fi
ok "kubectl context is now '${KCTX}'."

# ---- wait for nodes Ready --------------------------------------------------
info "Waiting for cluster nodes to become Ready (timeout 120s)..."
if ! kubectl wait --for=condition=Ready nodes --all --timeout=120s >/dev/null 2>&1; then
  fail "Cluster nodes did not reach Ready state within 120s."
  warn "Current node status:"
  kubectl get nodes || true
  die "Cluster '${CLUSTER_NAME}' is not healthy." \
      "Try 'scripts/kind-cleanup.sh ${CLUSTER_NAME}' and re-run this setup."
fi
ok "All nodes are Ready."

printf "\n%s%sCKAD kind environment is ready.%s\n" "${C_BOLD}" "${C_GREEN}" "${C_RESET}"
printf "  cluster name : %s\n" "${CLUSTER_NAME}"
printf "  kube context : %s\n" "${KCTX}"
printf "  config file  : %s\n" "${KIND_CONFIG}"
printf "\nYou can now run drills, for example:\n"
printf "  make run\n"
printf "  make exam\n"
