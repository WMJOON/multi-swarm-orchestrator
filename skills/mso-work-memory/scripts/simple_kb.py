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

Commands:
  simple_kb.py init   --path <dir> --dimension <N>
  simple_kb.py add    --path <dir> --input <root> --recursive --embedder multilingual
  simple_kb.py search --path <dir> "<query>" [--limit N] [--tags TAG] [--embedder multilingual]
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import zvec

DIM_DEFAULT = 384
VECTOR_FIELD = "embedding"
ST_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

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
    overfetch = args.limit * 5 if args.tags else args.limit
    results = coll.query(
        vectors=zvec.VectorQuery(field_name=VECTOR_FIELD, vector=qvec),
        topk=max(overfetch, args.limit),
        output_fields=["type", "title", "tags", "source_path", "snippet"],
    )

    if args.tags:
        results = [d for d in results if args.tags in (d.fields.get("tags") or "")]
    results = results[: args.limit]

    if not results:
        print("(검색 결과 없음)")
        return 0

    for d in results:
        f = d.fields or {}
        print(f"[{d.score:.3f}] {d.id}  ({f.get('type','?')})  {f.get('title','')}")
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
    p_search.set_defaults(func=cmd_search)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
