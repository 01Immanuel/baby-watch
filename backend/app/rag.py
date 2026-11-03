"""Tiny BM25 retriever (stdlib only). Rule-linked passages are always included first,
so retrieval can add context but never remove the evidence behind the result."""
import math
import re
from collections import Counter

_STOP = set("a an the of to in is are and or for with be it as on at by from that this can your you if".split())


def tokenize(text):
    return [t for t in re.findall(r"[a-z0-9/]+", text.lower()) if t not in _STOP]


class BM25:
    def __init__(self, passages, k1=1.5, b=0.75):
        self.passages, self.k1, self.b = passages, k1, b
        self.docs = [tokenize(" ".join([p["section"], p["text"], p.get("keywords", "")])) for p in passages]
        self.avg = sum(len(d) for d in self.docs) / max(len(self.docs), 1)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query):
        q = tokenize(query)
        out = []
        for p, d in zip(self.passages, self.docs, strict=True):
            tf, s = Counter(d), 0.0
            for t in q:
                if t in tf:
                    s += self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            out.append((s, p))
        return sorted(out, key=lambda x: -x[0])


def retrieve(bm25, query, must_include=(), k=4):
    by_id = {p["id"]: p for p in bm25.passages}
    chosen = [by_id[i] for i in dict.fromkeys(must_include) if i in by_id]
    for s, p in bm25.scores(query):
        if len(chosen) >= k:
            break
        if s > 0 and p not in chosen:
            chosen.append(p)
    return chosen
