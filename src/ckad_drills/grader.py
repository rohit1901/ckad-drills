from ckad_drills.kubectl_runner import run_verification


def grade_command(command: str) -> bool:
    return run_verification(command)
