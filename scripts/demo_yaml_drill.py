#!/usr/bin/env python3
"""End-to-end demo: run YQ01 from question_banks/yaml_demo.yaml against
the live kind cluster, showing the YAML pipeline (setup -> verify (before)
-> simulated student solution -> verify (after) -> teardown).

This is a throwaway demo, not part of the package.
"""

import subprocess

from ckad_drills.environment import execute_phase
from ckad_drills.generator import build_drill
from ckad_drills.grading import grade_drills
from ckad_drills.kubectl_runner import run_command_capture, run_verification
from ckad_drills.yaml_datasets import load_yaml_questions


def banner(label: str) -> None:
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)


def main() -> int:
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "ynet01":
        return _run_ynet01()
    return _run_yq01()


def _run_yq01() -> int:
    questions = load_yaml_questions("question_banks/yaml_demo.yaml")
    yq01 = next(q for q in questions if q.question_id == "YQ01")
    drill = build_drill(yq01, target_namespace=None)  # keep 'workloads'

    banner(f"Drill {drill.question_id}: {drill.domain} - {drill.topic}")
    print(drill.scenario)
    print(drill.tasks)

    banner("PHASE 1: setup")
    setup_summary = execute_phase([drill], "setup", run_command_capture)
    for step in setup_summary.steps:
        status = "OK" if step.succeeded else "FAILED"
        print(f"  [{status}] {step.label}")
        if step.output:
            for line in step.output.splitlines():
                print(f"         {line}")

    banner("PHASE 2: verify BEFORE solving (expected: every check fails)")
    results_before = grade_drills(
        [drill], runner=run_verification, capture_runner=run_command_capture
    )
    for cr in results_before[0].check_results:
        status = "PASS" if cr.passed else "FAIL"
        print(f"  [{status}] {cr.name}")
        print(f"          detail: {cr.detail}")

    banner("PHASE 3: simulate student solution")
    cmd = (
        "kubectl run demo-pod -n workloads "
        "--image=nginx:1.27-alpine --labels=tier=frontend"
    )
    print(f"  $ {cmd}")
    rc = subprocess.run(cmd, shell=True).returncode
    print(f"  exit_code={rc}")
    print("  waiting for the Pod to become Ready (up to 60s)...")
    subprocess.run(
        "kubectl wait --for=condition=Ready pod/demo-pod -n workloads --timeout=60s",
        shell=True,
    )

    banner("PHASE 4: verify AFTER solving (expected: every check passes)")
    results_after = grade_drills(
        [drill], runner=run_verification, capture_runner=run_command_capture
    )
    for cr in results_after[0].check_results:
        status = "PASS" if cr.passed else "FAIL"
        print(f"  [{status}] {cr.name}")
        print(f"          detail: {cr.detail}")
    print(
        f"\n  drill passed = {results_after[0].passed}  "
        f"(checks: {sum(cr.passed for cr in results_after[0].check_results)}/"
        f"{len(results_after[0].check_results)})"
    )

    banner("PHASE 5: teardown")
    teardown_summary = execute_phase([drill], "teardown", run_command_capture)
    for step in teardown_summary.steps:
        status = "OK" if step.succeeded else "FAILED"
        print(f"  [{status}] {step.label}")

    return 0 if results_after[0].passed else 1


def _run_ynet01() -> int:
    questions = load_yaml_questions("question_banks/services_and_networking.yaml")
    ynet01 = next(q for q in questions if q.question_id == "YNET01")
    drill = build_drill(ynet01, target_namespace=None)

    banner(f"Drill {drill.question_id}: {drill.domain} - {drill.topic}")
    print(drill.scenario)
    print(drill.tasks)

    banner(
        "PHASE 1: setup (creates namespace, seeds 'api' Deployment, waits for Available)"
    )
    setup_summary = execute_phase([drill], "setup", run_command_capture)
    for step in setup_summary.steps:
        status = "OK" if step.succeeded else "FAILED"
        print(f"  [{status}] {step.label}")
        if step.output:
            for line in step.output.splitlines()[:3]:
                print(f"         {line}")

    banner("PHASE 2: verify BEFORE solving (Service not yet created)")
    results_before = grade_drills(
        [drill], runner=run_verification, capture_runner=run_command_capture
    )
    for cr in results_before[0].check_results:
        status = "PASS" if cr.passed else "FAIL"
        print(f"  [{status}] {cr.name}")
        print(f"          detail: {cr.detail}")

    banner("PHASE 3: simulate student solution")
    cmd = (
        "kubectl expose deployment api -n workloads "
        "--name=api-svc --port=80 --target-port=8080"
    )
    print(f"  $ {cmd}")
    subprocess.run(cmd, shell=True)
    print("  waiting for endpoints to populate...")
    subprocess.run(
        "kubectl wait --for=jsonpath='{.subsets[0].addresses[0].ip}' "
        "endpoints/api-svc -n workloads --timeout=60s",
        shell=True,
    )

    banner("PHASE 4: verify AFTER solving")
    results_after = grade_drills(
        [drill], runner=run_verification, capture_runner=run_command_capture
    )
    for cr in results_after[0].check_results:
        status = "PASS" if cr.passed else "FAIL"
        print(f"  [{status}] {cr.name}")
        print(f"          detail: {cr.detail}")
    print(
        f"\n  drill passed = {results_after[0].passed}  "
        f"(checks: {sum(cr.passed for cr in results_after[0].check_results)}/"
        f"{len(results_after[0].check_results)})"
    )

    banner("PHASE 5: teardown")
    teardown_summary = execute_phase([drill], "teardown", run_command_capture)
    for step in teardown_summary.steps:
        status = "OK" if step.succeeded else "FAILED"
        print(f"  [{status}] {step.label}")

    return 0 if results_after[0].passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
