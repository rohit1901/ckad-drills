from pathlib import Path

DEFAULT_COUNT = 5
DEFAULT_NAMESPACE = "drill-01"
DEFAULT_CLEANUP_MODE = "none"

# CKAD-style exam defaults (matches the official CKAD exam shape).
# Override on the CLI with --count and --time-limit.
CKAD_EXAM_QUESTION_COUNT = 22
CKAD_EXAM_TIME_LIMIT_SECONDS = 120 * 60  # 2 hours
# Reminders fire when the *remaining* time crosses one of these thresholds.
CKAD_EXAM_REMINDER_THRESHOLDS_SECONDS = (
    60 * 60,  # 1h remaining
    30 * 60,  # 30m remaining
    10 * 60,  # 10m remaining
    5 * 60,  #  5m remaining
)
KNOWN_NAMESPACES = (
    "team-alpha",
    "team-beta",
    "default",
    "ckad-practice",
    "workloads",
    "dev",
    "staging",
    "prod",
)
PROTECTED_NAMESPACES = (
    "default",
    "kube-system",
    "kube-public",
    "kube-node-lease",
)
CLEANUP_MODES = (
    "none",
    "objects",
    "namespace",
    "kind-cluster",
)
NAMESPACED_CLEANUP_RESOURCES = (
    "deployments",
    "statefulsets",
    "daemonsets",
    "replicasets",
    "replicationcontrollers",
    "pods",
    "services",
    "ingresses",
    "jobs",
    "cronjobs",
    "configmaps",
    "secrets",
    "serviceaccounts",
    "persistentvolumeclaims",
    "networkpolicies",
    "roles",
    "rolebindings",
    "resourcequotas",
    "limitranges",
)
BASE_QUESTION_BANK_FILE = "ckad_full_question_bank.csv"
EXAM_BLUEPRINT_FILE = "ckad_balanced_exam.csv"
QUESTION_BANK_EXTENSION_DIR = "question_banks"

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent


def resolve_dataset_path(mode: str) -> Path:
    if mode == "exam":
        return resolve_exam_blueprint_path()
    return resolve_base_question_bank_path()


def resolve_base_question_bank_path() -> Path:
    return PROJECT_ROOT / BASE_QUESTION_BANK_FILE


def resolve_exam_blueprint_path() -> Path:
    return PROJECT_ROOT / EXAM_BLUEPRINT_FILE


def resolve_question_bank_extension_paths() -> list[Path]:
    extension_dir = PROJECT_ROOT / QUESTION_BANK_EXTENSION_DIR
    if not extension_dir.exists():
        return []
    return sorted(path for path in extension_dir.glob("*.csv") if path.is_file())


def resolve_yaml_question_bank_paths() -> list[Path]:
    """Return YAML question-bank files under ``question_banks/`` (``*.yaml`` and ``*.yml``)."""
    extension_dir = PROJECT_ROOT / QUESTION_BANK_EXTENSION_DIR
    if not extension_dir.exists():
        return []
    return sorted(
        path
        for path in extension_dir.iterdir()
        if path.is_file() and path.suffix.lower() in (".yaml", ".yml")
    )
