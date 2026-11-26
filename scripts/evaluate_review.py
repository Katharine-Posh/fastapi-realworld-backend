#!/usr/bin/env python3
"""Compute precision/recall/F1 from manually labelled review findings.

Input JSON format: {"gold": ["finding-1", ...], "predicted": ["finding-1", ...]}.
Use stable IDs for the same underlying issue in both lists.
"""
import argparse
import json
from pathlib import Path


def score(gold: set[str], predicted: set[str]) -> dict[str, float | int]:
    tp = len(gold & predicted)
    fp = len(predicted - gold)
    fn = len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="JSON with gold and predicted finding IDs")
    args = parser.parse_args()
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    result = score(set(data["gold"]), set(data["predicted"]))
    print(json.dumps(result, indent=2))
    print("Interpretation: precision measures how many reported findings are valid; recall measures how many known valid findings were found.")


if __name__ == "__main__":
    main()
