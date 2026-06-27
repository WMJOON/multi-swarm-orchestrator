---
name: mso-intent-analytics
version: "0.4.2"
description: >
  MSO 도메인 NLU 어휘의 단일 정본(registry) + intent-레벨 analytics 의 집.
  LinkML schema(nlu_intent.yaml) · TTL instances · SKOS taxonomy · intent matrix를 소유.
  registry SoT 는 UUG(uug-grounding)가 멀티-레지스트리 브리지로 소비.
  (구 mso-intent-registry 개명 — §11.) ⚠ analytics(intent 사용·매칭 측정, tier-escalation
  신호 흡수)는 §11.1 상 이 스킬 귀속이나 미구현 — registry 부분만 가동.
schema_owner: true
schema_path: references/schemas/nlu_intent.yaml
role: data
triggers: []
depends_on: []
---

# MSO Intent Analytics (v0.4.0, 구 mso-intent-registry)

MSO NLU 레이어. 현재 **registry(데이터 skill)** — 정본 데이터 + lookup API. 런타임 로직 없음.

> **개명·역할 (§11/§11.1)**: `mso-intent-registry` → `mso-intent-analytics`. registry(Intent/SlotSpec/IntentMatrix SoT)는 그대로 유지하고 UUG 가 소비. 그 위에 얹힐 intent-레벨 analytics(사용·매칭 측정, 최적화) + mso-conversation-analytics 의 **tier-escalation 폐루프 신호**는 이 스킬이 받기로 결정(§11.1)됐으나 **아직 미구현**.

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
cd repository/skills/mso-intent-analytics
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
