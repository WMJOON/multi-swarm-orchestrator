#!/usr/bin/env python3
"""simple_kb.py — zvec-backed semantic index for mso-work-memory.

Colocated with wm_node.py (which calls this via subprocess for `reindex`/
`search`) so mso-work-memory no longer depends on an external
"simple-knowledge-zvec" skill that doesn't exist as a standalone package.

Embedders (--embedder):
  multilingual (default) — sentence-transformers
      "paraphrase-multilingual-MiniLM-L12-v2" (384-dim, local, no API key).
      Real semantic similarity, handles Korean well (unlike zvec's own
      DefaultLocalDenseEmbedding, which defaults to the English-only
      all-MiniLM-L6-v2). First run downloads the model (~420MB) via the
      `sentence-transformers` package; needs network once, then cached
      under ~/.cache/torch/sentence_transformers/.
  hash — deterministic character n-gram (2,3) hashing-trick vector (no
      model, no download, lexical/structural similarity only). Automatic
      fallback if sentence-transformers or the model isn't available.

Reranking (search only, on by default): vector search overfetches a candidate
pool, then Qwen3-Reranker-0.6B(LM Studio, OpenAI 호환 API)가 query-document 쌍마다
"yes"/"no" 다음 토큰 logprob으로 관련성 점수를 매겨 그 풀을 재정렬한다(공식 Qwen3-Reranker
프롬프트 템플릿 + assistant 메시지 프리필로 "<think></think>" 이후 첫 토큰만 봄). LM Studio
서버가 없거나 reranker 모델이 안 떠 있으면 자동으로 건너뛰고 벡터 유사도 순서를 그대로 쓴다
(--no-rerank로도 끌 수 있음).

Commands:
  simple_kb.py init   --path <dir> --dimension <N>
  simple_kb.py add    --path <dir> --input <root> --recursive --embedder multilingual
  simple_kb.py search --path <dir> "<query>" [--limit N] [--tags TAG] [--embedder multilingual] [--no-rerank]
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import zvec

DIM_DEFAULT = 384
VECTOR_FIELD = "embedding"
ST_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
LMSTUDIO_URL_DEFAULT = os.environ.get("LMSTUDIO_URL", "http://localhost:1234/v1")
RERANK_MODEL_DEFAULT = "qwen3-reranker-0.6b"
RERANK_INSTRUCT = "Given a search query, retrieve relevant work-memory records (issues, decisions, patterns) that answer it"
RERANK_SYSTEM = ("Judge whether the Document meets the requirements based on the Query and the "
                  "Instruct provided. Note that the answer can only be 'yes' or 'no'.")
RERANK_POOL_CAP = 30  # 후보 풀 상한 — 후보 하나당 LLM 호출 1번이라 레이턴시 상한선

_st_model = None


def _get_st_model():
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer(ST_MODEL_NAME)
    return _st_model


def embed_texts_semantic(texts: list) -> list:
    """Batch semantic embedding via sentence-transformers. Raises on failure
    (caller decides whether to fall back to hash)."""
    model = _get_st_model()
    vecs = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    return [v.astype(np.float32).tolist() for v in vecs]


def embed_text_hash(text: str, dim: int = DIM_DEFAULT) -> list:
    """Deterministic char-ngram hashing-trick embedding (n=2,3), L2-normalized.
    Lexical/structural fallback — no model, no download, works offline."""
    text = " ".join(text.split()).lower()
    vec = np.zeros(dim, dtype=np.float32)
    for n in (2, 3):
        for i in range(max(0, len(text) - n + 1)):
            gram = text[i:i + n]
            if not gram.strip():
                continue
            h = hashlib.md5(gram.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "big") % dim
            sign = 1.0 if (h[4] & 1) == 0 else -1.0
            vec[idx] += sign
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.astype(np.float32).tolist()


def embed_texts(texts: list, embedder: str) -> list:
    if embedder == "hash":
        return [embed_text_hash(t) for t in texts]
    try:
        return embed_texts_semantic(texts)
    except Exception as e:
        print(f"[warn] semantic embedder({ST_MODEL_NAME}) 사용 불가 ({e}) — hash로 폴백", file=sys.stderr)
        return [embed_text_hash(t) for t in texts]


def rerank_score(query: str, document: str, base_url: str, model: str, timeout: int = 20) -> float:
    """Qwen3-Reranker yes/no 다음 토큰 logprob → [0,1] 관련성 점수(softmax(yes, no)).
    실패 시 None(호출부가 벡터 유사도 순서 유지 여부를 판단)."""
    import requests

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": RERANK_SYSTEM},
            {"role": "user", "content": f"<Instruct>: {RERANK_INSTRUCT}\n<Query>: {query}\n<Document>: {document[:2000]}"},
            {"role": "assistant", "content": "<think>\n\n</think>\n\n"},
        ],
        "max_tokens": 1,
        "temperature": 0,
        "logprobs": True,
        "top_logprobs": 10,
    }
    r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json=body, timeout=timeout)
    r.raise_for_status()
    top = r.json()["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
    logp = {t["token"].strip().lower(): t["logprob"] for t in top}
    yes_lp = logp.get("yes", -20.0)
    no_lp = logp.get("no", -20.0)
    yes_p, no_p = math.exp(yes_lp), math.exp(no_lp)
    return yes_p / (yes_p + no_p) if (yes_p + no_p) > 0 else 0.0


def rerank(query: str, docs: list, base_url: str = LMSTUDIO_URL_DEFAULT, model: str = RERANK_MODEL_DEFAULT):
    """docs: list of zvec.Doc. (rerank_score, doc) 튜플을 관련성 점수 내림차순으로 반환.
    LM Studio/reranker 모델을 못 쓰면 경고만 찍고 (None, doc) 리스트를 벡터 유사도 순서 그대로 반환."""
    scored = []
    for d in docs:
        f = d.fields or {}
        text = f"{f.get('title','')} {f.get('snippet','')}".strip()
        try:
            score = rerank_score(query, text, base_url, model)
        except Exception as e:
            print(f"[warn] rerank 실패({e}) — 벡터 유사도 순서로 폴백", file=sys.stderr)
            return [(None, doc) for doc in docs]
        scored.append((score, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _schema(dim: int) -> "zvec.CollectionSchema":
    return zvec.CollectionSchema(
        name="work_memory",
        fields=[
            zvec.FieldSchema("type", zvec.DataType.STRING, nullable=True),
            zvec.FieldSchema("title", zvec.DataType.STRING, nullable=True),
            zvec.FieldSchema("tags", zvec.DataType.STRING, nullable=True),
            zvec.FieldSchema("source_path", zvec.DataType.STRING, nullable=True),
            zvec.FieldSchema("snippet", zvec.DataType.STRING, nullable=True),
        ],
        vectors=zvec.VectorSchema(
            name=VECTOR_FIELD,
            data_type=zvec.DataType.VECTOR_FP32,
            dimension=dim,
            index_param=zvec.HnswIndexParam(metric_type=zvec.MetricType.COSINE),
        ),
    )


def cmd_init(args):
    path = Path(args.path)
    if path.exists():
        print(f"[init] 이미 존재함, 건너뜀: {path}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    zvec.create_and_open(str(path), _schema(args.dimension))
    print(f"[init] 생성 완료: {path} (dim={args.dimension})")
    return 0


def _iter_jsonl_entries(root: Path):
    for jf in sorted(root.rglob("*.jsonl")):
        rel_parts = jf.relative_to(root).parts[:-1]
        if any(p.startswith(".") for p in rel_parts):
            continue  # .zvec, .migration-archive 등 제외
        for line_num, line in enumerate(jf.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(e, dict):
                continue
            yield jf, line_num, e


def _embedder_marker(path: Path) -> Path:
    return path.parent / f".{path.name}.embedder"


def cmd_add(args):
    path = Path(args.path)
    root = Path(args.input)
    dim = DIM_DEFAULT

    # 재현 가능한 전체 재빌드로 단순화(진짜 incremental upsert 대신) — reindex 용도에 부합.
    if path.exists():
        shutil.rmtree(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    coll = zvec.create_and_open(str(path), _schema(dim))

    batch = []  # list of (id, fields, embed_source)
    n = 0

    def flush():
        nonlocal n
        if not batch:
            return
        vecs = embed_texts([b[2] for b in batch], args.embedder)
        docs = [
            zvec.Doc(id=str(eid), vectors={VECTOR_FIELD: vec}, fields=fields)
            for (eid, fields, _), vec in zip(batch, vecs)
        ]
        coll.insert(docs)
        n += len(docs)
        batch.clear()

    for jf, line_num, e in _iter_jsonl_entries(root):
        eid = e.get("id") or f"{jf.stem}:{line_num}"
        title = e.get("title", "") or ""
        text = e.get("text", "") or ""
        tags = ",".join(e.get("tags", []) or [])
        embed_source = f"{title} {text}"[:2000]
        fields = {
            "type": e.get("type", "") or "",
            "title": title,
            "tags": tags,
            "source_path": str(jf.relative_to(root)),
            "snippet": text[:300],
        }
        batch.append((eid, fields, embed_source))
        if len(batch) >= 128:
            flush()
            print(f"  ... {n}건", file=sys.stderr)
    flush()

    _embedder_marker(path).write_text(args.embedder, encoding="utf-8")
    print(f"[add] {n}건 인덱싱 완료 → {path} (embedder={args.embedder})")
    return 0


def cmd_search(args):
    path = Path(args.path)
    if not path.exists():
        sys.exit(f"[ERROR] 인덱스 없음: {path}")
    coll = zvec.open(str(path))

    marker = _embedder_marker(path)
    embedder = args.embedder
    if marker.exists():
        built_with = marker.read_text(encoding="utf-8").strip()
        if built_with and built_with != embedder:
            print(f"[info] 인덱스는 embedder={built_with}로 빌드됨 — 검색도 동일하게 맞춤", file=sys.stderr)
            embedder = built_with

    qvec = embed_texts([args.query], embedder)[0]
    # rerank 켜져 있으면 재정렬할 후보 풀을 넉넉히 뽑는다(RERANK_POOL_CAP 상한).
    overfetch = args.limit * 5 if args.tags else args.limit
    if not args.no_rerank:
        overfetch = max(overfetch, min(args.limit * 3, RERANK_POOL_CAP))
    results = coll.query(
        vectors=zvec.VectorQuery(field_name=VECTOR_FIELD, vector=qvec),
        topk=max(overfetch, args.limit),
        output_fields=["type", "title", "tags", "source_path", "snippet"],
    )

    if args.tags:
        results = [d for d in results if args.tags in (d.fields.get("tags") or "")]

    reranked = None
    if not args.no_rerank and results:
        reranked = rerank(args.query, results[:RERANK_POOL_CAP], args.lmstudio_url, args.rerank_model)

    pairs = reranked if reranked is not None else [(None, d) for d in results]
    pairs = pairs[: args.limit]

    if not pairs:
        print("(검색 결과 없음)")
        return 0

    for rscore, d in pairs:
        f = d.fields or {}
        score_str = f"rerank={rscore:.3f} vec={d.score:.3f}" if rscore is not None else f"vec={d.score:.3f}"
        print(f"[{score_str}] {d.id}  ({f.get('type','?')})  {f.get('title','')}")
        snippet = (f.get("snippet") or "").replace("\n", " ")
        if snippet:
            print(f"        {snippet[:160]}")
        tags = f.get("tags") or ""
        if tags:
            print(f"        tags: {tags}")
        print()
    return 0


def main():
    p = argparse.ArgumentParser(prog="simple_kb.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--path", required=True)
    p_init.add_argument("--dimension", type=int, default=DIM_DEFAULT)
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add")
    p_add.add_argument("--path", required=True)
    p_add.add_argument("--input", required=True)
    p_add.add_argument("--recursive", action="store_true")
    p_add.add_argument("--embedder", default="multilingual", choices=["multilingual", "hash"])
    p_add.set_defaults(func=cmd_add)

    p_search = sub.add_parser("search")
    p_search.add_argument("--path", required=True)
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--tags", default=None)
    p_search.add_argument("--embedder", default="multilingual", choices=["multilingual", "hash"])
    p_search.add_argument("--no-rerank", action="store_true",
                           help="Qwen3-Reranker 재정렬 끄고 벡터 유사도 순서만 사용(기본은 rerank 켜짐)")
    p_search.add_argument("--lmstudio-url", default=LMSTUDIO_URL_DEFAULT)
    p_search.add_argument("--rerank-model", default=RERANK_MODEL_DEFAULT)
    p_search.set_defaults(func=cmd_search)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
