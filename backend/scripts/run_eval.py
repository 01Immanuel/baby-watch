"""Evaluate the rule engine on the labelled synthetic vignettes. Prints a report and writes docs/eval_report.md."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import engine


def main():
    rules = engine.load_rules()
    cases = json.load(open(engine.RULES_DIR / "cases.json"))["cases"]
    rows = []
    for c in cases:
        res = engine.evaluate(rules, c["input"])
        rows.append((c, res["level"], [t["id"] for t in res["triggered"]]))
    R = engine.RANK
    n = len(rows)
    exact = sum(1 for c, p, _ in rows if p == c["expected_level"])
    under = [(c, p) for c, p, _ in rows if R[p] < R[c["expected_level"]]]
    over = [(c, p) for c, p, _ in rows if R[p] > R[c["expected_level"]]]
    def recall(cls, at_least=False):
        pos = [(c, p) for c, p, _ in rows if (R[c["expected_level"]] >= R[cls] if at_least else c["expected_level"] == cls)]
        hit = [1 for c, p in pos if R[p] >= R[cls]]
        return len(hit), len(pos)
    g_hit, g_n = recall("go_now")
    w_hit, w_n = recall("watch", at_least=True)
    fired_ids = {i for _, _, ids in rows for i in ids}
    uncovered = [r["id"] for r in rules["rules"] if r["id"] not in fired_ids]
    lines = [
        "# Baby Watch: rule engine evaluation on synthetic vignettes", "",
        f"Cases: {n} (synthetic, NOT yet clinician reviewed). Rules version: {rules['version']}.", "",
        f"- Exact agreement: {exact}/{n}",
        f"- Go-now recall: {g_hit}/{g_n}",
        f"- Watch-or-higher recall (any risk caught): {w_hit}/{w_n}",
        f"- Under-triage (engine lower than expected): {len(under)}",
        f"- Over-triage (engine higher than expected): {len(over)}",
        f"- Rules never triggered by any vignette: {', '.join(uncovered) if uncovered else 'none'}", "",
    ]
    for title, items in (("Under-triage cases", under), ("Over-triage cases", over)):
        if items:
            lines.append(f"## {title}")
            for c, p in items:
                lines.append(f"- {c['id']}: expected {c['expected_level']}, engine {p}. {c['note']}")
            lines.append("")
    text = "\n".join(lines)
    print(text)
    if "--write" in sys.argv:
        (engine.ROOT / "docs" / "eval_report.md").write_text(text, encoding="utf-8")
    return len(under)

if __name__ == "__main__":
    main()
