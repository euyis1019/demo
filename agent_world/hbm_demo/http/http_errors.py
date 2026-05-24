"""HTTP error helpers for HBM demo routes (Phase 5)."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from agent_world.hbm_demo.shared.errors import HbmServiceError


def service_error_payload(exc: Exception) -> Tuple[Dict[str, Any], int]:
    """Map service exceptions to JSON body + HTTP status."""
    if isinstance(exc, HbmServiceError):
        return {"success": False, "error": exc.message}, exc.http_status
    if isinstance(exc, RuntimeError):
        return {"success": False, "error": str(exc)}, 503
    if isinstance(exc, KeyError):
        return {"success": False, "error": str(exc)}, 404
    return {"success": False, "error": str(exc)}, 500
