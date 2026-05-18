import shlex
from collections.abc import Callable

from ckad_drills.config import (
    CLEANUP_MODES,
    NAMESPACED_CLEANUP_RESOURCES,
    PROTECTED_NAMESPACES,
)
from ckad_drills.exceptions import CleanupConfigurationError
from ckad_drills.kubectl_runner import run_command
from ckad_drills.models import CleanupStepResult, CleanupSummary

ShellRunner = Callable[[str], bool]


def validate_cleanup_settings(
    mode: str,
    namespace: str,
    kind_cluster_name: str | None = None,
) -> None:
    if mode not in CLEANUP_MODES:
        allowed = ", ".join(CLEANUP_MODES)
        raise CleanupConfigurationError(
            f"Unsupported cleanup mode '{mode}'. Expected one of: {allowed}."
        )

    if mode in {"objects", "namespace"} and namespace in PROTECTED_NAMESPACES:
        protected = ", ".join(PROTECTED_NAMESPACES)
        raise CleanupConfigurationError(
            f"Refusing to run cleanup mode '{mode}' against protected namespace '{namespace}'. Protected namespaces: {protected}."
        )

    if mode == "kind-cluster" and not kind_cluster_name:
        raise CleanupConfigurationError(
            "Cleanup mode 'kind-cluster' requires --kind-cluster-name."
        )


def build_cleanup_plan(
    mode: str,
    namespace: str,
    kind_cluster_name: str | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    validate_cleanup_settings(mode, namespace, kind_cluster_name)

    if mode == "none":
        return namespace, []

    if mode == "objects":
        resources = ",".join(NAMESPACED_CLEANUP_RESOURCES)
        quoted_namespace = shlex.quote(namespace)
        return (
            namespace,
            [
                (
                    "Delete common namespaced resources",
                    f"kubectl delete {resources} -n {quoted_namespace} --all --ignore-not-found",
                )
            ],
        )

    if mode == "namespace":
        quoted_namespace = shlex.quote(namespace)
        return (
            namespace,
            [
                (
                    "Delete practice namespace",
                    f"kubectl delete namespace {quoted_namespace} --ignore-not-found --wait=false",
                )
            ],
        )

    quoted_cluster_name = shlex.quote(kind_cluster_name or "")
    return (
        kind_cluster_name or "",
        [
            (
                "Delete kind cluster",
                f"kind delete cluster --name {quoted_cluster_name}",
            )
        ],
    )


def cleanup_environment(
    mode: str,
    namespace: str,
    *,
    kind_cluster_name: str | None = None,
    runner: ShellRunner = run_command,
) -> CleanupSummary:
    target, plan = build_cleanup_plan(mode, namespace, kind_cluster_name)
    if not plan:
        return CleanupSummary(
            mode=mode,
            target=target,
            attempted=False,
            succeeded=True,
            steps=(),
        )

    step_results = []
    overall_success = True
    for label, command in plan:
        succeeded = runner(command)
        overall_success = overall_success and succeeded
        step_results.append(
            CleanupStepResult(
                label=label,
                command=command,
                succeeded=succeeded,
            )
        )

    return CleanupSummary(
        mode=mode,
        target=target,
        attempted=True,
        succeeded=overall_success,
        steps=tuple(step_results),
    )
