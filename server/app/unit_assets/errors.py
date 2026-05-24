"""Domain errors for unit asset persistence."""

from __future__ import annotations

from typing import Any


class UnitAssetServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class UnitAssetNotFoundError(UnitAssetServiceError):
    def __init__(self, asset_id: str) -> None:
        super().__init__(
            "unit_asset_not_found",
            "unit asset not found",
            details={"id": asset_id},
        )


class UnitAssetForbiddenError(UnitAssetServiceError):
    def __init__(self, asset_id: str, reason: str = "forbidden") -> None:
        super().__init__(
            "unit_asset_forbidden",
            reason,
            details={"id": asset_id},
        )


class UnitAssetInvalidError(UnitAssetServiceError):
    def __init__(self, field: str, reason: str) -> None:
        super().__init__(
            "unit_asset_invalid",
            f"{field}: {reason}",
            details={"field": field, "reason": reason},
        )


class UnitAssetConflictError(UnitAssetServiceError):
    def __init__(self, asset_type: str, name: str) -> None:
        super().__init__(
            "unit_asset_conflict",
            "unit asset already exists",
            details={"type": asset_type, "name": name},
        )

