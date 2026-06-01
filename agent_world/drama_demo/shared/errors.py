"""HTTP-mapped service errors for HBM demo (Phase 5)."""

from __future__ import annotations


class DramaServiceError(Exception):
    """Base error with an HTTP status for Flask routes."""

    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RunnerNotReadyError(DramaServiceError):
    http_status = 503


class DatabaseReadError(DramaServiceError):
    http_status = 503


class IpcFailedError(DramaServiceError):
    http_status = 502


class IpcTimeoutError(DramaServiceError):
    http_status = 504


class LlmServiceError(DramaServiceError):
    http_status = 502


class WorldLoopDisabledError(DramaServiceError):
    http_status = 503
