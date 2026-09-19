"""Application-specific errors retain their identity behind the frozen HTTP contract."""

_PUBLIC_CODE_BY_INTERNAL = {
    "INVALID_INPUT": "VALIDATION_ERROR",
    "INVALID_CURSOR": "VALIDATION_ERROR",
    "INVALID_SOURCE": "VALIDATION_ERROR",
    "EMPTY_DATASET": "VALIDATION_ERROR",
    "INVALID_CREDENTIALS": "UNAUTHENTICATED",
    "PREFERENCES_REQUIRED": "INVALID_STATE",
    "IMMUTABLE_CONFIG": "INVALID_STATE",
    "MODEL_UNVERIFIED": "INVALID_STATE",
    "SOURCE_BUSY": "INVALID_STATE",
    "SOURCE_DISABLED": "INVALID_STATE",
    "BRIEF_NOT_READY": "INVALID_STATE",
    "IDEMPOTENCY_CONFLICT": "VERSION_CONFLICT",
    "CONCURRENCY_LIMIT": "RATE_LIMITED",
    "GENERATION_LIMIT": "RATE_LIMITED",
    "ACCOUNT_CREATION_LIMIT": "RATE_LIMITED",
    "LOGIN_LIMIT": "RATE_LIMITED",
    "MODEL_UNAVAILABLE": "DEPENDENCY_UNAVAILABLE",
    "SERVICE_ERROR": "INTERNAL_ERROR",
}


class AppError(Exception):
    def __init__(self, code, message, status=400, *, retry_after=None, fields=None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.retry_after, self.fields = retry_after, fields

    @property
    def public_code(self):
        # Import lazily: the validator itself raises AppError while loading this module.
        from .contract import CONTRACT

        allowed = CONTRACT["components"]["schemas"]["Error"]["properties"]["code"]["enum"]
        if self.code in allowed:
            return self.code
        if self.code in _PUBLIC_CODE_BY_INTERNAL:
            return _PUBLIC_CODE_BY_INTERNAL[self.code]
        # Some internal identities (CONFIGURATION_REQUIRED, HTTP_ERROR) span statuses.
        # New internal details also stay within the established public categories.
        return {
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "INVALID_STATE",
            429: "RATE_LIMITED",
            503: "DEPENDENCY_UNAVAILABLE",
        }.get(self.status, "INTERNAL_ERROR" if self.status >= 500 else "VALIDATION_ERROR")
