from __future__ import annotations

from collections import defaultdict

from .ranking import filter_ranking


def delta(a_value: float, b_value: float, direction: str) -> float:
    if direction == "max":
        return a_value - b_value
    return b_value - a_value


def partial_concordance(d: float, q: float, p: float) -> float:
    if d >= -q:
        return 1.0
    if d < -p:
        return 0.0
    if p == q:
        return 1.0 if d >= -q else 0.0
    return (d + p) / (p - q)


def discordance(d: float, p: float, v: float | None) -> float:
    if v is None:
        return 0.0
    loss = -d
    if loss <= p:
        return 0.0
    if loss > v:
        return 1.0
    if v == p:
        return 1.0 if loss > p else 0.0
    return (loss - p) / (v - p)


def analyze(
    alternatives: list[dict],
    criteria: list[dict],
    weights: dict[str, float],
    thresholds: dict[str, dict],
    perf: dict[str, dict[str, float]],
    lambda_cut: float,
) -> dict:
    alt_ids = [alt["id"] for alt in alternatives]
    leaf_criteria = [criterion for criterion in criteria if criterion.get("direction") in {"min", "max"}]
    concordance: dict[str, dict[str, float]] = defaultdict(dict)
    credibility: dict[str, dict[str, float]] = defaultdict(dict)
    relations: dict[str, dict[str, str]] = defaultdict(dict)

    for a in alt_ids:
        for b in alt_ids:
            if a == b:
                continue
            partials = []
            discords = []
            for criterion in leaf_criteria:
                cid = criterion["id"]
                t = thresholds[cid]
                d = delta(float(perf[a][cid]), float(perf[b][cid]), criterion["direction"])
                partials.append((weights[cid], partial_concordance(d, float(t["q"]), float(t["p"]))))
                discords.append(discordance(d, float(t["p"]), None if t.get("v") is None else float(t["v"])))
            weight_total = sum(weight for weight, _ in partials)
            c_value = sum(weight * value for weight, value in partials) / weight_total
            sigma = c_value
            if c_value == 1.0:
                sigma = 0.0 if any(disc == 1.0 for disc in discords) else 1.0
            else:
                for disc in discords:
                    if disc > c_value:
                        sigma *= (1 - disc) / (1 - c_value)
            concordance[a][b] = round(c_value, 6)
            credibility[a][b] = round(sigma, 6)

    for a in alt_ids:
        for b in alt_ids:
            if a == b:
                continue
            ab = credibility[a][b] >= lambda_cut
            ba = credibility[b][a] >= lambda_cut
            if ab and not ba:
                relation = "outranks"
            elif ba and not ab:
                relation = "outranked-by"
            elif ab and ba:
                relation = "indifferent"
            else:
                relation = "incomparable"
            relations[a][b] = relation

    final = _rank_from_relations(alt_ids, relations)
    candidate_ids = {alt["id"] for alt in alternatives if alt.get("type") == "candidate"}
    reference_ids = {alt["id"] for alt in alternatives if alt.get("type") == "reference"}
    return {
        "concordance": dict(concordance),
        "credibility": dict(credibility),
        "relations": dict(relations),
        "distillation": {"descending": [item["alternatives"] for item in final], "ascending": [item["alternatives"] for item in final], "final": final},
        "candidate_ranking": filter_ranking(final, candidate_ids),
        "reference_ranking": filter_ranking(final, reference_ids),
    }


def _rank_from_relations(alt_ids: list[str], relations: dict[str, dict[str, str]]) -> list[dict]:
    remaining = set(alt_ids)
    ranking: list[dict] = []
    rank = 1
    while remaining:
        top = []
        for candidate in sorted(remaining):
            outranked_by_remaining = any(
                other != candidate and relations[candidate].get(other) == "outranked-by" for other in remaining
            )
            if not outranked_by_remaining:
                top.append(candidate)
        if not top:
            top = sorted(remaining)
        ranking.append({"rank": rank, "alternatives": top})
        remaining.difference_update(top)
        rank += 1
    return ranking
