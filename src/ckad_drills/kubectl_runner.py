import subprocess


def run_command(command: str) -> bool:
    result = subprocess.run(
        command,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def run_verification(command: str) -> bool:
    return run_command(command)
