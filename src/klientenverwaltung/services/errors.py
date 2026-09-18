class ServiceError(Exception):
    """Base class for errors raised by the service layer, message text is German."""


class ValidationError(ServiceError):
    """Input data violates a business rule."""


class NotFoundError(ServiceError):
    """The requested record does not exist."""


class ConflictError(ServiceError):
    """The operation would violate a uniqueness or usage rule."""


class SessionOverlapError(ConflictError):
    """A session's time range overlaps with another already-scheduled session."""
