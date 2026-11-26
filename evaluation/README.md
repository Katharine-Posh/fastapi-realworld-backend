# Evaluating AI review quality

Do not treat model-generated examples as ground truth. Build a small benchmark from real
pull requests: have a human reviewer record each distinct actionable defect, then compare
those IDs with findings produced by the bot for the same diffs. Use stable IDs for matching.

Create `evaluation/results.json` in this format:

```json
{
  "gold": ["auth-001", "article-002", "db-003"],
  "predicted": ["auth-001", "article-002", "false-positive-001"]
}
```

Run `python scripts/evaluate_review.py evaluation/results.json`. The script reports TP/FP/FN,
precision, recall and F1. Discuss false positives (overly noisy or speculative comments) and
false negatives (missed defects), and repeat on several PRs before drawing conclusions.
