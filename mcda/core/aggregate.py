from __future__ import annotations

import math
from statistics import median

from .errors import AnalysisError


def _available(entries_by_participant: dict[str, dict | None]) -> list[dict]:
    return [
        entry
        for entry in entries_by_participant.values()
        if entry is not None and not entry.get("abstention") and entry.get("value") is not None
    ]


def aggregate_values(
    entries_by_participant: dict[str, dict | None],
    strategy: str,
    participants: dict[str, dict],
    missing_policy: str = "exclude-participant",
    abstention_policy: str | None = None,
) -> float:
    entries = _available(entries_by_participant)
    if not entries:
        raise AnalysisError("No resolvable values for aggregate.")
    values = [float(entry["value"]) for entry in entries]
    if strategy == "mean":
        return sum(values) / len(values)
    if strategy == "median":
        return float(median(values))
    if strategy == "geomean":
        if any(value <= 0 for value in values):
            raise AnalysisError("Geometric mean requires positive values.")
        return math.prod(values) ** (1 / len(values))
    if strategy == "confidence-weighted-mean":
        weights = [float(entry.get("confidence", 0.5)) for entry in entries]
        total = sum(weights)
        if total <= 0:
            raise AnalysisError("Confidence-weighted mean has zero total confidence.")
        return sum(value * weight for value, weight in zip(values, weights)) / total
    if strategy.startswith("facilitator:"):
        participant_id = strategy.split(":", 1)[1]
        entry = entries_by_participant.get(participant_id)
        if entry is None or entry.get("abstention") or entry.get("value") is None:
            raise AnalysisError(f"Participant {participant_id} has no value for requested aggregate.")
        return float(entry["value"])
    if strategy.startswith("trait-weighted:"):
        trait = strategy.split(":", 1)[1]
        weighted = []
        for entry in entries:
            participant = participants.get(entry["participant"], {})
            trait_value = participant.get("traits", {}).get(trait)
            if isinstance(trait_value, (int, float)):
                weighted.append((float(entry["value"]), float(trait_value)))
        if not weighted:
            raise AnalysisError(f"No numeric trait values found for {trait}.")
        total = sum(weight for _, weight in weighted)
        if total <= 0:
            raise AnalysisError(f"Trait {trait} has zero total weight.")
        return sum(value * weight for value, weight in weighted) / total
    raise AnalysisError(f"Unknown aggregation strategy: {strategy}")


def aggregate_thresholds(
    entries_by_participant: dict[str, dict | None],
    strategy: str,
    participants: dict[str, dict],
    missing_policy: str = "exclude-participant",
) -> tuple[dict, list[dict]]:
    warnings: list[dict] = []
    resolved: dict[str, float | None] = {}
    for key in ("q", "p", "v"):
        component_entries: dict[str, dict | None] = {}
        saw_null_veto = False
        for participant_id, entry in entries_by_participant.items():
            if entry is None:
                component_entries[participant_id] = None
                continue
            component = entry.get(key)
            if key == "v" and component is None:
                saw_null_veto = True
                component_entries[participant_id] = None
                continue
            if not isinstance(component, dict) or component.get("value") is None:
                component_entries[participant_id] = None
                continue
            component_entries[participant_id] = {
                "participant": participant_id,
                "value": component["value"],
                "confidence": component.get("confidence", 0.5),
            }
        if key == "v" and not _available(component_entries):
            resolved[key] = None
            continue
        if key == "v" and saw_null_veto:
            warnings.append({"code": "mixed_veto", "message": "Some participants disabled veto while others set veto."})
        resolved[key] = aggregate_values(component_entries, strategy, participants, missing_policy)
    return resolved, warnings
