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


def run_command_capture(command: str) -> tuple[int, str, str]:
    """Run a shell command and capture exit code, stdout, and stderr as text."""
    result = subprocess.run(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.returncode, result.stdout or "", result.stderr or ""
