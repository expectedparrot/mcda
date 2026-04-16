from __future__ import annotations


def rank_score_items(scores: dict[str, float], higher_is_better: bool = True) -> list[dict]:
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=higher_is_better)
    ranking: list[dict] = []
    previous_score: float | None = None
    current_rank = 0
    for index, (item_id, score) in enumerate(ordered, start=1):
        if previous_score is None or score != previous_score:
            current_rank = index
            ranking.append({"rank": current_rank, "alternatives": [item_id], "score": score})
        else:
            ranking[-1]["alternatives"].append(item_id)
        previous_score = score
    return ranking


def filter_ranking(ranking: list[dict], allowed: set[str]) -> list[dict]:
    filtered = []
    rank = 1
    for group in ranking:
        alternatives = [alt for alt in group["alternatives"] if alt in allowed]
        if alternatives:
            item = {"rank": rank, "alternatives": alternatives}
            if "score" in group:
                item["score"] = group["score"]
            filtered.append(item)
            rank += 1
    return filtered
