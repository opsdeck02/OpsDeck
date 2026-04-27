from fastapi import APIRouter

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("")
def list_rules() -> list[dict[str, str | int]]:
    return [
        {"name": "eta_drift_hours", "value": 12},
        {"name": "document_missing_grace_hours", "value": 6},
    ]

