class ServiceError(Exception):
    """Base class for errors raised by the service layer, message text is German."""


class DataUnavailableError(ServiceError):
    """The data (the data drive) cannot be reached right now, e.g. unplugged."""


class ValidationError(ServiceError):
    """Input data violates a business rule.

    field is the service method's parameter name of the (first) offending
    input, where there is one - so a form can put the cursor there.
    """

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class NotFoundError(ServiceError):
    """The requested record does not exist."""


class ConflictError(ServiceError):
    """The operation would violate a uniqueness or usage rule."""


class DuplicateClientError(ConflictError):
    """A client with the same name (and no differing birth date) already
    exists. A warning rather than a ban - two people may share a name: the
    message lists the existing clients, and the caller may repeat the call
    with allow_duplicate=True once the user has confirmed."""


class SessionOverlapError(ConflictError):
    """A session's time range overlaps with another already-scheduled session."""
