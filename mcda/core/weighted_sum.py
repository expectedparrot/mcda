from __future__ import annotations

from .ranking import filter_ranking, rank_score_items


def normalize_performance(criteria: list[dict], perf: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    normalized: dict[str, dict[str, float]] = {alternative_id: {} for alternative_id in perf}
    for criterion in criteria:
        criterion_id = criterion["id"]
        values = [float(perf[alternative_id][criterion_id]) for alternative_id in perf]
        low = min(values)
        high = max(values)
        span = high - low
        for alternative_id in perf:
            raw = float(perf[alternative_id][criterion_id])
            if span == 0:
                score = 1.0
            elif criterion["direction"] == "max":
                score = (raw - low) / span
            else:
                score = (high - raw) / span
            normalized[alternative_id][criterion_id] = round(score, 6)
    return normalized


def analyze(
    alternatives: list[dict],
    criteria: list[dict],
    weights: dict[str, float],
    perf: dict[str, dict[str, float]],
) -> dict:
    normalized = normalize_performance(criteria, perf)
    scores = {}
    contributions = {}
    for alternative_id, criterion_scores in normalized.items():
        contributions[alternative_id] = {
            criterion_id: round(weights[criterion_id] * criterion_scores[criterion_id], 6)
            for criterion_id in weights
        }
        scores[alternative_id] = round(sum(contributions[alternative_id].values()), 6)

    ranking = rank_score_items(scores)
    candidate_ids = {alt["id"] for alt in alternatives if alt.get("type") == "candidate"}
    reference_ids = {alt["id"] for alt in alternatives if alt.get("type") == "reference"}
    return {
        "normalized_perf": normalized,
        "weighted_contributions": contributions,
        "scores": scores,
        "ranking": ranking,
        "candidate_ranking": filter_ranking(ranking, candidate_ids),
        "reference_ranking": filter_ranking(ranking, reference_ids),
    }
