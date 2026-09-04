from __future__ import annotations

import hashlib
import json

from labsre.models import ProposedAction


def action_digest(incident_id: str, action: ProposedAction) -> str:
    payload = {
        "incident_id": incident_id,
        "action": action.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
