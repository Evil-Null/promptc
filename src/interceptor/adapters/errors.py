"""Backend execution errors — precise, testable exception types."""

from __future__ import annotations


class MissingApiKeyError(Exception):
    """Required API key environment variable is not set."""

    def __init__(self, env_var: str, backend: str) -> None:
        self.env_var = env_var
        self.backend = backend
        super().__init__(
            f"Missing API key: set {env_var} environment variable for {backend}"
        )


class BackendRequestError(Exception):
    """HTTP request to backend provider failed."""

    def __init__(self, backend: str, status_code: int, detail: str) -> None:
        self.backend = backend
        self.status_code = status_code
        self.detail = detail
        super().__init__(
            f"{backend} request failed (HTTP {status_code}): {detail}"
        )


class BackendResponseParseError(Exception):
    """Backend returned an unparseable response payload."""

    def __init__(self, backend: str, detail: str) -> None:
        self.backend = backend
        self.detail = detail
        super().__init__(f"{backend} response parse error: {detail}")
