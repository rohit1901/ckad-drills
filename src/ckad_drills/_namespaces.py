"""Namespace constants used by drill generation and cleanup.

Kept in their own module so ``generator.py`` (which consumes
``KNOWN_NAMESPACES``) and ``cleanup.py`` (which consumes
``PROTECTED_NAMESPACES``) can import them without pulling in unrelated
config. ``config.py`` re-exports both names for backwards compatibility
with external imports.
"""

# Namespaces recognised by the rewriter in ``generator.rewrite_namespace``.
# When a drill is generated for a target namespace, any of these tokens
# appearing as a standalone identifier in scenario / tasks / verify text
# is rewritten to the target.
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

# Namespaces the cleanup module refuses to touch with ``--cleanup
# objects`` or ``--cleanup namespace``. Protects the cluster's own
# control-plane namespaces and the shared ``default`` namespace.
PROTECTED_NAMESPACES = (
    "default",
    "kube-system",
    "kube-public",
    "kube-node-lease",
)
