---
name: mso-intent-registry
version: "0.3.1"
description: >
  MSO 도메인 NLU 어휘의 단일 정본 보관소.
  LinkML schema(nlu_intent.yaml) · TTL instances · SKOS taxonomy · intent matrix를 소유.
  mso-utterance-grounding · mso-conversation-analytics에 lookup API를 제공한다.
schema_owner: true
schema_path: references/schemas/nlu_intent.yaml
role: data
triggers: []
depends_on: []
---

# MSO Intent Registry (v0.3.1)

MSO NLU 레이어의 **데이터 skill**. 런타임 로직 없음 — 정본 데이터 + lookup API만.

## 파일 구조

```
references/schemas/nlu_intent.yaml   ← [정본] LinkML schema — 3 skill 공유
instances/intents.ttl                ← 10 canonical intent 인스턴스
taxonomy/intent_taxonomy.ttl         ← verb 4개 SKOS
taxonomy/target_taxonomy.ttl         ← target 5개 + 하위 분류 SKOS
matrix/intent_matrix.ttl             ← (verb × target) 10 filled + planned/rejected
src/lookup.py                        ← Lookup API
tools/build.sh                       ← LinkML gen-owl/gen-shacl/gen-json-schema
generated/                           ← 자동 산출 (git-ignored)
```

## Lookup API

```python
from mso_intent_registry.lookup import (
    list_intents,          # 전체 intent 목록
    lookup_intent,         # intent_id → dict
    lookup_target,         # entity_ref → target_concepts
    get_trigger_keywords,  # intent_id → [str]
    list_matrix_cells,     # status 필터 → cell 목록
)
```

## Build (M1 DoD)

```bash
cd repository-test/skills/mso-intent-registry
bash tools/build.sh
```

gen-owl / gen-shacl / gen-json-schema 3종이 `generated/`에 산출되어야 M1 통과.

## Test (M2 DoD)

```bash
pip install rdflib pytest
python -m pytest tests/ -v
```

10 case 전체 PASS = M2 통과.

## Schema 소유권

`references/schemas/nlu_intent.yaml` 편집은 이 skill만 가능.  
다른 skill은 이 경로를 읽기 전용으로 참조한다.
