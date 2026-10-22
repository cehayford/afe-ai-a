"""Domain errors. Services raise these; the API turns them into the standard error envelope
and the web pages show the message as-is, so messages are written for people."""


class DomainError(Exception):
    status_code = 400
    code = "invalid"

    def __init__(self, message: str, reasons: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.reasons = reasons or []


class InvalidInput(DomainError):
    status_code = 422
    code = "invalid_input"


class RuleViolation(DomainError):
    """A trust rule stopped the action (e.g. verifying a home without a field visit)."""

    status_code = 409
    code = "rule_violation"


class NotAllowed(DomainError):
    status_code = 403
    code = "not_allowed"


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class UploadRejected(InvalidInput):
    """A file was refused for safety. The flag and audit record written before refusing are
    kept (the request commits them before returning the error)."""
