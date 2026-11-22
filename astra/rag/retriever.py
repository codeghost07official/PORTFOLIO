"""Hybrid retrieval over `doc_chunks`: BM25 (lexical) + cosine similarity
(Gemini embeddings, when enabled). Pure Python - no vector DB needed at
personal-workspace scale. Chunks are cached in-process and refreshed
incrementally whenever `meta.index_version` changes."""
import logging
import math
import re
import threading
from collections import Counter

from ..db import db
from .indexer import unpack_vector

log = logging.getLogger("astra.rag")

STOPWORDS = set("""a an and are as at be but by for from has have i if in into is it its me my of on or our so
that the their them then there these they this to was we were what when where which who why will with you your
do did does done can could should would how about just than too very also any all been being sir please""".split())
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.+#-]*")
_cache = {"version": None, "chunks": {}, "lock": threading.Lock()}


def tokenize(text):
    out = []
    for tok in _TOKEN.findall((text or "").lower()):
        tok = tok.strip(".-")
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        if len(tok) > 4 and tok.endswith("ies"):
            tok = tok[:-3] + "y"
        elif len(tok) > 4 and tok.endswith("es") and not tok.endswith("ses"):
            tok = tok[:-2]
        elif len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        elif len(tok) > 5 and tok.endswith("ing"):
            tok = tok[:-3]
        elif len(tok) > 4 and tok.endswith("ed"):
            tok = tok[:-2]
        out.append(tok)
    return out


def _refresh():
    version = db.scalar("SELECT value FROM meta WHERE key='index_version'", default="0")
    if version == _cache["version"]:
        return _cache["chunks"]
    with _cache["lock"]:
        if version == _cache["version"]:
            return _cache["chunks"]
        light = db.query("SELECT id, content_hash, embedding IS NOT NULL AS has_emb FROM doc_chunks")
        current = _cache["chunks"]
        fresh, need = {}, []
        for r in light:
            c = current.get(r["id"])
            if c and c["hash"] == r["content_hash"] and bool(c["emb"]) == bool(r["has_emb"]):
                fresh[r["id"]] = c
            else:
                need.append(r["id"])
        for start in range(0, len(need), 300):
            ids = need[start:start + 300]
            for r in db.query(
                f"SELECT * FROM doc_chunks WHERE id IN ({','.join('?' * len(ids))})", ids
            ):
                toks = tokenize(r["title"] + " " + r["content"])
                fresh[r["id"]] = {
                    "id": r["id"], "type": r["source_type"], "source_id": r["source_id"],
                    "project_id": r["project_id"], "parent_id": r["parent_id"], "title": r["title"],
                    "content": r["content"], "date": r["source_date"], "hash": r["content_hash"],
                    "tf": Counter(toks), "len": len(toks) or 1, "emb": unpack_vector(r["embedding"]),
                }
        _cache["chunks"], _cache["version"] = fresh, version
        return fresh


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def search(query, k=8, types=None, exclude_types=None, project_id=None, project_boost=1.6,
           exclude_parent=None, query_vector=None, min_score=0.05):
    chunks = list(_refresh().values())
    if types:
        chunks = [c for c in chunks if c["type"] in types]
    if exclude_types:
        chunks = [c for c in chunks if c["type"] not in exclude_types]
    if exclude_parent is not None:
        chunks = [c for c in chunks if not (c["type"] == "conversation" and c["parent_id"] == exclude_parent)]
    if not chunks:
        return []
    q_tokens = list(dict.fromkeys(tokenize(query)))
    n = len(chunks)
    avgdl = sum(c["len"] for c in chunks) / n
    df = Counter()
    for c in chunks:
        for t in q_tokens:
            if t in c["tf"]:
                df[t] += 1
    k1, b = 1.4, 0.75
    lexical = {}
    for c in chunks:
        s = 0.0
        for t in q_tokens:
            f = c["tf"].get(t)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * c["len"] / avgdl))
        lexical[c["id"]] = s
    max_lex = max(lexical.values()) or 1.0
    scored = []
    for c in chunks:
        lex = lexical[c["id"]] / max_lex
        sem = _cosine(query_vector, c["emb"]) if query_vector else 0.0
        if query_vector and c["emb"]:
            score = 0.4 * lex + 0.6 * max(0.0, (sem - 0.3) / 0.7)
        else:
            score = lex
        if project_id and c["project_id"] == project_id:
            score *= project_boost
        if score >= min_score:
            scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    results, seen = [], Counter()
    for score, c in scored:
        key = (c["type"], c["source_id"])
        if seen[key] >= 2:  # at most two chunks per source
            continue
        seen[key] += 1
        results.append({**{x: c[x] for x in ("id", "type", "source_id", "project_id", "parent_id", "title",
                                              "content", "date")}, "score": round(score, 4)})
        if len(results) >= k:
            break
    return results
