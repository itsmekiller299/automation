from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.security import require_admin

router = APIRouter(
    prefix="/api/model",
    tags=["model"],
    dependencies=[Depends(require_admin)],
)


@router.get("/evaluation")
def evaluation_artifact() -> dict:
    """Expose the latest evaluation report to the dashboard.

    The file is produced by `make eval`. Returning `available: false` keeps the
    dashboard useful before the first training run without pretending metrics
    exist.
    """
    path = settings.resolve_path(settings.nlu_evaluation_path)
    if not path.exists():
        return {
            "available": False,
            "hint": f"No evaluation report at {path}. Run `make eval` after training.",
        }
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not read evaluation report: {exc}") from exc
    return {"available": True, "path": str(path), "report": report}
