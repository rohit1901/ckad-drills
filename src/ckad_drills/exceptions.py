class DatasetValidationError(ValueError):
    """Raised when a CSV question bank has an invalid schema or invalid rows."""


class CleanupConfigurationError(ValueError):
    """Raised when cleanup settings are invalid or unsafe."""
