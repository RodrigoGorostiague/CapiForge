from __future__ import annotations


class SurfaceError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


def error_response(error: SurfaceError) -> dict:
    return {"status": "error", "error": error.to_dict()}


def unknown_resource(resource: str, identifier: str) -> SurfaceError:
    return SurfaceError("UNKNOWN_RESOURCE", f"unknown {resource}: {identifier}")
