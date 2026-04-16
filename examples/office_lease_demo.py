from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mcda-matplotlib")

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples" / "output" / "office_lease_selection"
FIGURES = ROOT / "docs" / "figures"

PARTICIPANTS = {
    "alice": "Alice Rivera",
    "bob": "Bob Chen",
    "carol": "Carol Singh",
}

ALTERNATIVES = {
    "downtown_loft": ("Downtown Loft", "candidate"),
    "midtown_suite": ("Midtown Suite", "candidate"),
    "suburban_campus": ("Suburban Campus", "candidate"),
    "current_office": ("Current Office", "reference"),
}

CRITERIA = {
    "annual_cost": {"name": "Annual cost", "direction": "min", "unit": "thousands USD per year"},
    "commute_time": {"name": "Commute time", "direction": "min", "unit": "average minutes"},
    "space_quality": {"name": "Space quality", "direction": "max", "unit": "score 0-100"},
    "lease_flexibility": {"name": "Lease flexibility", "direction": "max", "unit": "score 0-100"},
}

WEIGHTS = {
    "alice": {"financial": 30, "commute_time": 25, "space_quality": 30, "lease_flexibility": 15, "annual_cost": 1},
    "bob": {"financial": 20, "commute_time": 35, "space_quality": 30, "lease_flexibility": 15, "annual_cost": 1},
    "carol": {"financial": 40, "commute_time": 20, "space_quality": 25, "lease_flexibility": 15, "annual_cost": 1},
}

THRESHOLDS = {
    "annual_cost": {"q": 25, "p": 75, "v": 175},
    "commute_time": {"q": 3, "p": 8, "v": 20},
    "space_quality": {"q": 5, "p": 15, "v": 35},
    "lease_flexibility": {"q": 5, "p": 15, "v": None},
}

PERFORMANCE = {
    "downtown_loft": {"annual_cost": 620, "commute_time": 28, "space_quality": 92, "lease_flexibility": 55},
    "midtown_suite": {"annual_cost": 500, "commute_time": 35, "space_quality": 80, "lease_flexibility": 70},
    "suburban_campus": {"annual_cost": 390, "commute_time": 52, "space_quality": 72, "lease_flexibility": 88},
    "current_office": {"annual_cost": 540, "commute_time": 38, "space_quality": 68, "lease_flexibility": 45},
}

DISPLAY_NAMES = {
    "downtown_loft": "Downtown Loft",
    "midtown_suite": "Midtown Suite",
    "suburban_campus": "Suburban Campus",
    "current_office": "Current Office",
    "annual_cost": "Annual cost",
    "commute_time": "Commute time",
    "space_quality": "Space quality",
    "lease_flexibility": "Lease flexibility",
}


def mcda(args: list[str], project: bool = True) -> dict:
    command = [sys.executable, "-m", "mcda.cli"]
    if project:
        command.extend(["--project", str(PROJECT)])
    command.extend(args)
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{completed.stdout}\n{completed.stderr}")
    return json.loads(completed.stdout)["data"]


def build_project() -> dict:
    if PROJECT.exists():
        shutil.rmtree(PROJECT)
    FIGURES.mkdir(parents=True, exist_ok=True)

    mcda(["init", str(PROJECT), "--description", "Select the best office lease for the next three years."], project=False)

    for participant_id, name in PARTICIPANTS.items():
        mcda(["participant", "add", participant_id, name])

    traits = {
        "alice": ("operations", "10"),
        "bob": ("engineering", "7"),
        "carol": ("finance", "12"),
    }
    for participant_id, (role, years) in traits.items():
        mcda(["participant", "set-trait", participant_id, "role", json.dumps(role)])
        mcda(["participant", "set-trait", participant_id, "years_experience", years])

    for alternative_id, (name, alt_type) in ALTERNATIVES.items():
        mcda(["alt", "add", alternative_id, name, "--type", alt_type])

    mcda(["crit", "add-group", "financial", "Financial"])
    mcda(
        [
            "crit",
            "add",
            "annual_cost",
            "Annual cost",
            "--direction",
            "min",
            "--unit",
            "thousands USD per year",
            "--parent",
            "financial",
        ]
    )
    for criterion_id, spec in CRITERIA.items():
        if criterion_id == "annual_cost":
            continue
        mcda(["crit", "add", criterion_id, spec["name"], "--direction", spec["direction"], "--unit", spec["unit"]])

    for participant_id, entries in WEIGHTS.items():
        for criterion_id, value in entries.items():
            mcda(["weights", "set", participant_id, criterion_id, str(value), "--confidence", "1"])

    for participant_id in PARTICIPANTS:
        for criterion_id, values in THRESHOLDS.items():
            args = [
                "thresholds",
                "set",
                participant_id,
                criterion_id,
                "--q",
                str(values["q"]),
                "--p",
                str(values["p"]),
            ]
            if values["v"] is None:
                args.append("--no-veto")
            else:
                args.extend(["--v", str(values["v"])])
            mcda(args)

    for participant_id in PARTICIPANTS:
        for alternative_id, entries in PERFORMANCE.items():
            for criterion_id, value in entries.items():
                mcda(["perf", "set", participant_id, alternative_id, criterion_id, str(value), "--confidence", "1"])

    return mcda(["analyze", "run"])


def save_json(result: dict) -> None:
    path = ROOT / "docs" / "office_lease_result.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def save_weighted_sum_json(result: dict) -> None:
    path = ROOT / "docs" / "office_lease_weighted_sum_result.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_mermaid_outranking_graph(result: dict, filename: str) -> None:
    alternatives = list(PERFORMANCE)
    lines = [
        "flowchart LR",
        "  downtown_loft[Downtown Loft]",
        "  midtown_suite[Midtown Suite]",
        "  suburban_campus[Suburban Campus]",
        "  current_office[(Current Office<br/>reference)]",
        "  classDef candidate fill:#eef6ff,stroke:#4C78A8,stroke-width:1px;",
        "  classDef reference fill:#f7f7f7,stroke:#666,stroke-dasharray:4 3;",
        "  class downtown_loft,midtown_suite,suburban_campus candidate;",
        "  class current_office reference;",
    ]
    seen_pairs: set[tuple[str, str]] = set()
    for source in alternatives:
        for target in alternatives:
            if source == target:
                continue
            relation = result["relations"][source][target]
            if relation == "outranks":
                credibility = result["credibility"][source][target]
                lines.append(f"  {source} -->|{credibility:.2f}| {target}")
            elif relation == "indifferent":
                pair = tuple(sorted([source, target]))
                if pair not in seen_pairs:
                    credibility = min(result["credibility"][source][target], result["credibility"][target][source])
                    lines.append(f"  {source} <-->|indifferent {credibility:.2f}| {target}")
                    seen_pairs.add(pair)
    lines.extend(
        [
            "  %% No arrows among the three candidate offices means ELECTRE III did not find a decisive outranking relation there.",
            "  %% Downtown Loft is also incomparable with Current Office at lambda 0.75.",
        ]
    )
    (ROOT / "docs" / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_weights(result: dict) -> None:
    weights = result["resolved_weights"]
    criteria = list(weights)
    values = [weights[criterion] for criterion in criteria]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = ["#4C78A8", "#F58518", "#54A24B", "#B279A2"]
    ax.bar([DISPLAY_NAMES[c] for c in criteria], values, color=colors[: len(criteria)])
    ax.set_ylabel("Resolved global weight")
    ax.set_title("What the group decided matters most")
    ax.set_ylim(0, max(values) * 1.25)
    for idx, value in enumerate(values):
        ax.text(idx, value + 0.01, f"{value:.2f}", ha="center", va="bottom")
    fig.autofmt_xdate(rotation=15, ha="right")
    fig.tight_layout()
    fig.savefig(FIGURES / "office_lease_weights.png", dpi=160)
    plt.close(fig)


def normalized_performance(result: dict) -> dict[str, dict[str, float]]:
    perf = result["resolved_perf"]
    normalized: dict[str, dict[str, float]] = {alt: {} for alt in perf}
    for criterion_id, spec in CRITERIA.items():
        values = [perf[alt][criterion_id] for alt in perf]
        low, high = min(values), max(values)
        span = high - low or 1
        for alternative_id in perf:
            raw = perf[alternative_id][criterion_id]
            if spec["direction"] == "max":
                score = (raw - low) / span
            else:
                score = (high - raw) / span
            normalized[alternative_id][criterion_id] = score
    return normalized


def plot_performance(result: dict) -> None:
    normalized = normalized_performance(result)
    alternatives = list(PERFORMANCE)
    criteria = list(CRITERIA)
    matrix = np.array([[normalized[alt][criterion] for criterion in criteria] for alt in alternatives])

    fig, ax = plt.subplots(figsize=(8, 4.8))
    image = ax.imshow(matrix, cmap="viridis", vmin=0, vmax=1)
    ax.set_xticks(range(len(criteria)), [DISPLAY_NAMES[c] for c in criteria], rotation=20, ha="right")
    ax.set_yticks(range(len(alternatives)), [DISPLAY_NAMES[a] for a in alternatives])
    ax.set_title("Performance normalized by criterion direction")
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            ax.text(col, row, f"{matrix[row, col]:.2f}", ha="center", va="center", color="white" if matrix[row, col] < 0.45 else "black")
    fig.colorbar(image, ax=ax, label="0 = worst observed, 1 = best observed")
    fig.tight_layout()
    fig.savefig(FIGURES / "office_lease_normalized_performance.png", dpi=160)
    plt.close(fig)


def plot_credibility(result: dict) -> None:
    alternatives = list(PERFORMANCE)
    matrix = np.ones((len(alternatives), len(alternatives)))
    for row, a in enumerate(alternatives):
        for col, b in enumerate(alternatives):
            if a == b:
                matrix[row, col] = np.nan
            else:
                matrix[row, col] = result["credibility"][a][b]

    fig, ax = plt.subplots(figsize=(7.5, 6))
    masked = np.ma.masked_invalid(matrix)
    image = ax.imshow(masked, cmap="magma", vmin=0, vmax=1)
    ax.set_xticks(range(len(alternatives)), [DISPLAY_NAMES[a] for a in alternatives], rotation=25, ha="right")
    ax.set_yticks(range(len(alternatives)), [DISPLAY_NAMES[a] for a in alternatives])
    ax.set_title("Credibility that row alternative outranks column alternative")
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            if np.isnan(matrix[row, col]):
                ax.text(col, row, "-", ha="center", va="center")
            else:
                ax.text(col, row, f"{matrix[row, col]:.2f}", ha="center", va="center", color="white" if matrix[row, col] < 0.65 else "black")
    fig.colorbar(image, ax=ax, label="credibility")
    fig.tight_layout()
    fig.savefig(FIGURES / "office_lease_credibility.png", dpi=160)
    plt.close(fig)


def plot_ranking(result: dict) -> None:
    candidate_ranks = {}
    for group in result["candidate_ranking"]:
        for alternative_id in group["alternatives"]:
            candidate_ranks[alternative_id] = group["rank"]

    candidates = [alt for alt, (_, alt_type) in ALTERNATIVES.items() if alt_type == "candidate"]
    ranks = [candidate_ranks[alt] for alt in candidates]
    y = np.arange(len(candidates))

    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.barh(y, [max(ranks) + 1 - rank for rank in ranks], color=["#4C78A8", "#F58518", "#54A24B"])
    ax.set_yticks(y, [DISPLAY_NAMES[alt] for alt in candidates])
    ax.set_xlabel("Higher bar = better rank")
    ax.set_title("Candidate ranking from ELECTRE III")
    for idx, rank in enumerate(ranks):
        ax.text(max(ranks) + 1 - rank + 0.03, idx, f"rank {rank}", va="center")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIGURES / "office_lease_candidate_ranking.png", dpi=160)
    plt.close(fig)


def plot_weighted_sum_scores(result: dict) -> None:
    candidates = [alt for alt, (_, alt_type) in ALTERNATIVES.items() if alt_type == "candidate"]
    scores = [result["scores"][alt] for alt in candidates]
    order = np.argsort(scores)[::-1]
    ordered_candidates = [candidates[i] for i in order]
    ordered_scores = [scores[i] for i in order]

    fig, ax = plt.subplots(figsize=(8, 3.8))
    y = np.arange(len(ordered_candidates))
    ax.barh(y, ordered_scores, color=["#54A24B", "#4C78A8", "#F58518"])
    ax.set_yticks(y, [DISPLAY_NAMES[alt] for alt in ordered_candidates])
    ax.set_xlabel("Weighted normalized score")
    ax.set_title("Weighted-sum ranking gives a forced total order")
    for idx, score in enumerate(ordered_scores):
        ax.text(score + 0.01, idx, f"{score:.3f}", va="center")
    ax.set_xlim(0, min(1.05, max(ordered_scores) * 1.2))
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIGURES / "office_lease_weighted_sum_scores.png", dpi=160)
    plt.close(fig)


def plot_relations(result: dict) -> None:
    alternatives = list(PERFORMANCE)
    relation_codes = {
        "outranks": 3,
        "indifferent": 2,
        "incomparable": 1,
        "outranked-by": 0,
    }
    relation_labels = {
        3: "outranks",
        2: "indifferent",
        1: "incomparable",
        0: "outranked by",
    }
    matrix = np.full((len(alternatives), len(alternatives)), np.nan)
    for row, a in enumerate(alternatives):
        for col, b in enumerate(alternatives):
            if a == b:
                continue
            matrix[row, col] = relation_codes[result["relations"][a][b]]

    fig, ax = plt.subplots(figsize=(8, 6))
    cmap = plt.get_cmap("Set2", 4)
    image = ax.imshow(np.ma.masked_invalid(matrix), cmap=cmap, vmin=-0.5, vmax=3.5)
    ax.set_xticks(range(len(alternatives)), [DISPLAY_NAMES[a] for a in alternatives], rotation=25, ha="right")
    ax.set_yticks(range(len(alternatives)), [DISPLAY_NAMES[a] for a in alternatives])
    ax.set_title("Pairwise ELECTRE relation: row alternative vs column alternative")
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            if np.isnan(matrix[row, col]):
                ax.text(col, row, "-", ha="center", va="center")
            else:
                ax.text(col, row, relation_labels[int(matrix[row, col])], ha="center", va="center", fontsize=8)
    cbar = fig.colorbar(image, ax=ax, ticks=[0, 1, 2, 3])
    cbar.ax.set_yticklabels([relation_labels[i] for i in [0, 1, 2, 3]])
    fig.tight_layout()
    fig.savefig(FIGURES / "office_lease_relations.png", dpi=160)
    plt.close(fig)


def lambda_sweep() -> list[dict]:
    rows = []
    for lambda_value in [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]:
        result = mcda(["analyze", "run", "--lambda", f"{lambda_value:.2f}"])
        relations = [
            relation
            for source, targets in result["relations"].items()
            for target, relation in targets.items()
            if source != target
        ]
        rows.append(
            {
                "lambda": lambda_value,
                "outranks": relations.count("outranks"),
                "incomparable": relations.count("incomparable"),
                "indifferent": relations.count("indifferent"),
                "candidate_rank_groups": len(result["candidate_ranking"]),
                "top_candidate_group_size": len(result["candidate_ranking"][0]["alternatives"]),
            }
        )
    path = ROOT / "docs" / "office_lease_lambda_sweep.json"
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rows


def plot_lambda_sensitivity(rows: list[dict]) -> None:
    lambdas = [row["lambda"] for row in rows]

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.plot(lambdas, [row["outranks"] for row in rows], marker="o", label="outranking directions")
    ax.plot(lambdas, [row["incomparable"] for row in rows], marker="o", label="incomparable directions")
    ax.plot(lambdas, [row["top_candidate_group_size"] for row in rows], marker="o", label="top candidate group size")
    ax.set_xlabel("lambda credibility cutoff")
    ax.set_ylabel("count")
    ax.set_title("Sensitivity to the ELECTRE credibility cutoff")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "office_lease_lambda_sensitivity.png", dpi=160)
    plt.close(fig)


def print_summary(result: dict) -> None:
    print("Office lease demo complete")
    print(f"Project data: {PROJECT}")
    print("Resolved weights:")
    for criterion, value in result["resolved_weights"].items():
        print(f"  {DISPLAY_NAMES[criterion]}: {value:.2f}")
    print("Candidate ranking:")
    for group in result["candidate_ranking"]:
        names = ", ".join(DISPLAY_NAMES[alt] for alt in group["alternatives"])
        print(f"  Rank {group['rank']}: {names}")
    print("Figures:")
    for path in sorted(FIGURES.glob("office_lease_*.png")):
        print(f"  {path.relative_to(ROOT)}")


def main() -> None:
    result = build_project()
    weighted_sum = mcda(["analyze", "run", "--method", "weighted-sum"])
    save_json(result)
    save_weighted_sum_json(weighted_sum)
    write_mermaid_outranking_graph(result, "office_lease_outranking_graph.mmd")
    plot_weights(result)
    plot_performance(result)
    plot_credibility(result)
    plot_ranking(result)
    plot_weighted_sum_scores(weighted_sum)
    plot_relations(result)
    sweep_rows = lambda_sweep()
    plot_lambda_sensitivity(sweep_rows)
    print_summary(result)


if __name__ == "__main__":
    main()
