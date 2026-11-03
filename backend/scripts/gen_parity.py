"""Writes rules/parity.json: inputs + Python-engine signatures. The JS engine must reproduce them."""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import engine


def random_input(r):
    inp = {}
    inp["gestation_weeks"] = r.choice([None] + [float(x) for x in range(1, 43)])
    inp["hb"] = r.choice([None, None] + [round(r.uniform(4, 15), 1) for _ in range(8)] + [7.0, 9.5, 10.0, 10.5, 11.0])
    inp["pallor"] = r.choice(["none", "none", "some", "severe"])
    inp["bp_sys"] = r.choice([None, None, 100, 120, 139, 140, 150, 159, 160, 175])
    inp["bp_dia"] = r.choice([None, None, 60, 80, 89, 90, 100, 109, 110, 115])
    inp["distance_km"] = r.choice([None, 2, 9.9, 10, 25])
    for k in engine.BOOLS:
        inp[k] = r.random() < 0.15
    inp["bp_age"] = r.choice([None, "today", "today", "earlier", "weird", 5])
    inp["hb_age"] = r.choice([None, "recent", "recent", "earlier", "weird", True])
    for k in ("gestation_weeks", "hb", "bp_sys", "bp_dia", "distance_km"):
        if inp[k] is not None and r.random() < 0.12:
            inp[k] = r.choice([str(inp[k]), " " + str(inp[k]) + " ", "0x10", "1e2", "abc", "", ".5", "5.", "-3", True])
    if r.random() < 0.05:
        inp["pallor"] = r.choice(["purple", 3, None])
    return inp

def main():
    rules = engine.load_rules()
    r = random.Random(7)
    inputs = [c["input"] for c in json.load(open(engine.RULES_DIR / "cases.json"))["cases"]]
    inputs += [random_input(r) for _ in range(500)]
    rows = [{"input": i, "expected": engine.signature(engine.evaluate(rules, i))} for i in inputs]
    json.dump(rows, open(engine.RULES_DIR / "parity.json", "w"))
    print(f"wrote {len(rows)} parity rows")

if __name__ == "__main__":
    main()
