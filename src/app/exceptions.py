"""Custom exception hierarchy for evergreen-tvevents."""


class TvEventsDefaultError(Exception):
    """Base exception with HTTP status code."""

    status_code = 400

    def __init__(self, message: str = "", status_code: int | None = None):
        """Initialize with optional message and HTTP status code."""
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class TvEventsCatchallError(TvEventsDefaultError):
    """Wraps unexpected errors with 500 status."""

    status_code = 500


class TvEventsMissingRequiredParamError(TvEventsDefaultError):
    """Raised when a required request parameter is missing."""

    status_code = 400


class TvEventsSecurityValidationError(TvEventsDefaultError):
    """Raised when the T1_SALT security hash fails validation."""

    status_code = 400


class TvEventsInvalidPayloadError(TvEventsDefaultError):
    """Raised when the event payload fails type-specific validation."""

    status_code = 400
