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
PROJECT = ROOT / "examples" / "output" / "vendor_selection"
FIGURES = ROOT / "docs" / "figures"

PARTICIPANTS = {
    "ops": "Operations Lead",
    "security": "Security Lead",
    "finance": "Finance Lead",
}

ALTERNATIVES = {
    "balanced_vendor": ("Balanced Vendor", "candidate"),
    "budget_vendor": ("Budget Vendor", "candidate"),
    "premium_vendor": ("Premium Vendor", "candidate"),
    "current_vendor": ("Current Vendor", "reference"),
}

CRITERIA = {
    "annual_cost": {"name": "Annual cost", "direction": "min", "unit": "thousands USD per year"},
    "uptime": {"name": "Uptime", "direction": "max", "unit": "percent"},
    "security": {"name": "Security", "direction": "max", "unit": "score 0-100"},
    "migration_effort": {"name": "Migration effort", "direction": "min", "unit": "person-weeks"},
}

WEIGHTS = {
    "ops": {"annual_cost": 20, "uptime": 35, "security": 30, "migration_effort": 15},
    "security": {"annual_cost": 15, "uptime": 30, "security": 40, "migration_effort": 15},
    "finance": {"annual_cost": 25, "uptime": 30, "security": 35, "migration_effort": 10},
}

THRESHOLDS = {
    "annual_cost": {"q": 10, "p": 30, "v": 100},
    "uptime": {"q": 0.1, "p": 0.5, "v": 1.5},
    "security": {"q": 3, "p": 8, "v": 20},
    "migration_effort": {"q": 1, "p": 3, "v": 8},
}

PERFORMANCE = {
    "balanced_vendor": {"annual_cost": 115, "uptime": 99.95, "security": 94, "migration_effort": 3},
    "budget_vendor": {"annual_cost": 80, "uptime": 99.10, "security": 74, "migration_effort": 5},
    "premium_vendor": {"annual_cost": 180, "uptime": 99.99, "security": 96, "migration_effort": 6},
    "current_vendor": {"annual_cost": 110, "uptime": 99.50, "security": 78, "migration_effort": 0},
}

DISPLAY_NAMES = {
    "balanced_vendor": "Balanced Vendor",
    "budget_vendor": "Budget Vendor",
    "premium_vendor": "Premium Vendor",
    "current_vendor": "Current Vendor",
    "annual_cost": "Annual cost",
    "uptime": "Uptime",
    "security": "Security",
    "migration_effort": "Migration effort",
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
    mcda(["init", str(PROJECT), "--description", "Choose the best cloud vendor for production hosting."], project=False)

    for participant_id, name in PARTICIPANTS.items():
        mcda(["participant", "add", participant_id, name])

    for alternative_id, (name, alt_type) in ALTERNATIVES.items():
        mcda(["alt", "add", alternative_id, name, "--type", alt_type])

    for criterion_id, spec in CRITERIA.items():
        mcda(["crit", "add", criterion_id, spec["name"], "--direction", spec["direction"], "--unit", spec["unit"]])

    for participant_id, entries in WEIGHTS.items():
        for criterion_id, value in entries.items():
            mcda(["weights", "set", participant_id, criterion_id, str(value), "--confidence", "1"])

    for participant_id in PARTICIPANTS:
        for criterion_id, values in THRESHOLDS.items():
            mcda(
                [
                    "thresholds",
                    "set",
                    participant_id,
                    criterion_id,
                    "--q",
                    str(values["q"]),
                    "--p",
                    str(values["p"]),
                    "--v",
                    str(values["v"]),
                ]
            )

    for participant_id in PARTICIPANTS:
        for alternative_id, entries in PERFORMANCE.items():
            for criterion_id, value in entries.items():
                mcda(["perf", "set", participant_id, alternative_id, criterion_id, str(value), "--confidence", "1"])

    return mcda(["analyze", "run", "--method", "weighted-sum"])


def save_json(result: dict) -> None:
    path = ROOT / "docs" / "vendor_selection_result.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_mermaid_outranking_graph(result: dict, filename: str) -> None:
    alternatives = list(PERFORMANCE)
    lines = [
        "flowchart LR",
        "  balanced_vendor[Balanced Vendor]",
        "  budget_vendor[Budget Vendor]",
        "  premium_vendor[Premium Vendor]",
        "  current_vendor[(Current Vendor<br/>reference)]",
        "  classDef candidate fill:#eef6ff,stroke:#4C78A8,stroke-width:1px;",
        "  classDef reference fill:#f7f7f7,stroke:#666,stroke-dasharray:4 3;",
        "  class balanced_vendor,budget_vendor,premium_vendor candidate;",
        "  class current_vendor reference;",
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
    (ROOT / "docs" / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalized_performance(result: dict) -> dict[str, dict[str, float]]:
    perf = result["resolved_perf"]
    normalized = {alt: {} for alt in perf}
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


def plot_weights(result: dict) -> None:
    weights = result["resolved_weights"]
    criteria = list(weights)
    values = [weights[criterion] for criterion in criteria]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([DISPLAY_NAMES[c] for c in criteria], values, color=["#4C78A8", "#F58518", "#54A24B", "#B279A2"])
    ax.set_ylabel("Resolved global weight")
    ax.set_title("Vendor selection priorities")
    for idx, value in enumerate(values):
        ax.text(idx, value + 0.01, f"{value:.2f}", ha="center", va="bottom")
    ax.set_ylim(0, max(values) * 1.25)
    fig.autofmt_xdate(rotation=15, ha="right")
    fig.tight_layout()
    fig.savefig(FIGURES / "vendor_selection_weights.png", dpi=160)
    plt.close(fig)


def plot_performance(result: dict) -> None:
    normalized = normalized_performance(result)
    alternatives = list(PERFORMANCE)
    criteria = list(CRITERIA)
    matrix = np.array([[normalized[alt][criterion] for criterion in criteria] for alt in alternatives])
    fig, ax = plt.subplots(figsize=(8, 4.8))
    image = ax.imshow(matrix, cmap="viridis", vmin=0, vmax=1)
    ax.set_xticks(range(len(criteria)), [DISPLAY_NAMES[c] for c in criteria], rotation=20, ha="right")
    ax.set_yticks(range(len(alternatives)), [DISPLAY_NAMES[a] for a in alternatives])
    ax.set_title("Vendor performance normalized by criterion direction")
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            ax.text(col, row, f"{matrix[row, col]:.2f}", ha="center", va="center", color="white" if matrix[row, col] < 0.45 else "black")
    fig.colorbar(image, ax=ax, label="0 = worst observed, 1 = best observed")
    fig.tight_layout()
    fig.savefig(FIGURES / "vendor_selection_normalized_performance.png", dpi=160)
    plt.close(fig)


def plot_credibility(result: dict) -> None:
    alternatives = list(PERFORMANCE)
    matrix = np.full((len(alternatives), len(alternatives)), np.nan)
    for row, a in enumerate(alternatives):
        for col, b in enumerate(alternatives):
            if a != b:
                matrix[row, col] = result["credibility"][a][b]
    fig, ax = plt.subplots(figsize=(7.5, 6))
    image = ax.imshow(np.ma.masked_invalid(matrix), cmap="magma", vmin=0, vmax=1)
    ax.set_xticks(range(len(alternatives)), [DISPLAY_NAMES[a] for a in alternatives], rotation=25, ha="right")
    ax.set_yticks(range(len(alternatives)), [DISPLAY_NAMES[a] for a in alternatives])
    ax.set_title("Credibility that row vendor outranks column vendor")
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            if np.isnan(matrix[row, col]):
                ax.text(col, row, "-", ha="center", va="center")
            else:
                ax.text(col, row, f"{matrix[row, col]:.2f}", ha="center", va="center", color="white" if matrix[row, col] < 0.65 else "black")
    fig.colorbar(image, ax=ax, label="credibility")
    fig.tight_layout()
    fig.savefig(FIGURES / "vendor_selection_credibility.png", dpi=160)
    plt.close(fig)


def plot_ranking(result: dict) -> None:
    ranks = {}
    for group in result["candidate_ranking"]:
        for alternative_id in group["alternatives"]:
            ranks[alternative_id] = group["rank"]
    candidates = [alt for alt, (_, alt_type) in ALTERNATIVES.items() if alt_type == "candidate"]
    rank_values = [ranks[alt] for alt in candidates]
    y = np.arange(len(candidates))
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.barh(y, [max(rank_values) + 1 - rank for rank in rank_values], color=["#54A24B", "#F58518", "#4C78A8"])
    ax.set_yticks(y, [DISPLAY_NAMES[alt] for alt in candidates])
    ax.set_xlabel("Higher bar = better rank")
    ax.set_title("Clear candidate ranking")
    for idx, rank in enumerate(rank_values):
        ax.text(max(rank_values) + 1 - rank + 0.03, idx, f"rank {rank}", va="center")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIGURES / "vendor_selection_candidate_ranking.png", dpi=160)
    plt.close(fig)


def plot_score_contributions(result: dict) -> None:
    candidates = [alt for alt, (_, alt_type) in ALTERNATIVES.items() if alt_type == "candidate"]
    criteria = list(CRITERIA)
    bottoms = np.zeros(len(candidates))

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    colors = ["#4C78A8", "#F58518", "#54A24B", "#B279A2"]
    for idx, criterion_id in enumerate(criteria):
        values = [result["weighted_contributions"][alt][criterion_id] for alt in candidates]
        ax.bar([DISPLAY_NAMES[alt] for alt in candidates], values, bottom=bottoms, label=DISPLAY_NAMES[criterion_id], color=colors[idx])
        bottoms += np.array(values)

    ax.set_ylabel("Weighted normalized contribution")
    ax.set_title("Why the balanced vendor wins")
    ax.legend(loc="upper right")
    for idx, total in enumerate(bottoms):
        ax.text(idx, total + 0.015, f"{total:.3f}", ha="center", va="bottom")
    ax.set_ylim(0, min(1.1, max(bottoms) * 1.25))
    fig.autofmt_xdate(rotation=10, ha="center")
    fig.tight_layout()
    fig.savefig(FIGURES / "vendor_selection_score_contributions.png", dpi=160)
    plt.close(fig)


def print_summary(result: dict) -> None:
    print("Vendor selection demo complete")
    print(f"Project data: {PROJECT}")
    print("Candidate ranking:")
    for group in result["candidate_ranking"]:
        names = ", ".join(DISPLAY_NAMES[alt] for alt in group["alternatives"])
        print(f"  Rank {group['rank']}: {names}")
    print("Figures:")
    for path in sorted(FIGURES.glob("vendor_selection_*.png")):
        print(f"  {path.relative_to(ROOT)}")


def main() -> None:
    result = build_project()
    save_json(result)
    plot_weights(result)
    plot_performance(result)
    plot_ranking(result)
    plot_score_contributions(result)
    electre_result = mcda(["analyze", "run", "--method", "electre-iii", "--lambda", "0.75"])
    write_mermaid_outranking_graph(electre_result, "vendor_selection_outranking_graph.mmd")
    plot_credibility(electre_result)
    print_summary(result)


if __name__ == "__main__":
    main()
