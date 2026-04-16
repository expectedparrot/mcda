from __future__ import annotations

from collections import defaultdict

from .errors import AnalysisError


def criteria_by_id(criteria: list[dict]) -> dict[str, dict]:
    return {criterion["id"]: criterion for criterion in criteria}


def leaf_criteria(criteria: list[dict]) -> list[dict]:
    parents = {criterion.get("parent") for criterion in criteria if criterion.get("parent")}
    return [criterion for criterion in criteria if criterion["id"] not in parents and criterion.get("direction") in {"min", "max"}]


def children_by_parent(criteria: list[dict]) -> dict[str | None, list[dict]]:
    children: dict[str | None, list[dict]] = defaultdict(list)
    for criterion in criteria:
        children[criterion.get("parent")].append(criterion)
    for values in children.values():
        values.sort(key=lambda item: item["id"])
    return children


def validate_tree(criteria: list[dict]) -> list[str]:
    issues: list[str] = []
    by_id = criteria_by_id(criteria)
    for criterion in criteria:
        parent = criterion.get("parent")
        if parent and parent not in by_id:
            issues.append(f"Criterion {criterion['id']} references missing parent {parent}.")
    for criterion in criteria:
        seen = set()
        current = criterion
        while current.get("parent"):
            parent = current["parent"]
            if parent in seen:
                issues.append(f"Criteria hierarchy contains a cycle at {criterion['id']}.")
                break
            seen.add(parent)
            current = by_id.get(parent, {})
            if not current:
                break
    return issues


def compute_global_weights(criteria: list[dict], local_weights: dict[str, float]) -> dict[str, float]:
    children = children_by_parent(criteria)
    issues: list[str] = []
    normalized: dict[str, float] = {}
    for parent, siblings in children.items():
        total = 0.0
        for sibling in siblings:
            value = local_weights.get(sibling["id"])
            if value is None:
                issues.append(f"Missing local weight for criterion {sibling['id']}.")
            else:
                total += value
        if total <= 0:
            issues.append(f"Sibling group under {parent or 'root'} has no positive weights.")
            continue
        for sibling in siblings:
            if sibling["id"] in local_weights:
                normalized[sibling["id"]] = local_weights[sibling["id"]] / total
    if issues:
        raise AnalysisError("Unable to resolve criteria weights.", {"issues": issues})

    by_id = criteria_by_id(criteria)
    leaves = leaf_criteria(criteria)

    def product_to_root(criterion_id: str) -> float:
        value = normalized[criterion_id]
        parent = by_id[criterion_id].get("parent")
        while parent:
            value *= normalized[parent]
            parent = by_id[parent].get("parent")
        return value

    return {leaf["id"]: product_to_root(leaf["id"]) for leaf in leaves}
