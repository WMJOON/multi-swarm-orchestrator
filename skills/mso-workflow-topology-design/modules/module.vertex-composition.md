# module.vertex-composition

> Source: v0.0.7-2 §2 Vertex Composition

## Purpose

Topology Motif는 구조만 정의한다.
실제 워크플로우 실행은 각 Vertex(노드)에 배치된 실행 단위 유형이 결정한다.

---

## Vertex 유형

| 유형 | 역할 | 예시 |
|------|------|------|
| **Agent** | 복잡한 판단 및 계획 수행 | PlannerAgent, ResearchAgent, WriterAgent |
| **Skill** | 특정 작업 수행 | SearchSkill, SummarizeSkill, mso-execution-design |
| **Tool** | 외부 시스템 호출 | SearchTool, DatabaseTool, APIClient |
| **Model** | 추론 또는 예측 수행 | IntentClassifier, Embedder, Summarizer |

---

## 공식

```
Workflow Graph = Topology Motif + Vertex Mapping
```

---

## 조합 예시

**Chain motif + Vertex Mapping:**
```
PlannerAgent → SearchSkill → SummarizeSkill → WriterAgent
```

**Fork/Join motif + Vertex Mapping:**
```
ResearchAgent
    ↓
┌─────────────┐
↓             ↓
SearchTool   DatabaseTool
↓             ↓
└──────→ Summarizer(Model)
```

---

## 노드 vertex_type 필드

SKILL.md Phase 3에서 각 노드에 `vertex_type`을 지정한다.

```json
{
  "id": "T1",
  "label": "PlannerAgent",
  "vertex_type": "agent|skill|tool|model"
}
```

---

## 선택 기준

| 상황 | 추천 vertex_type |
|------|-----------------|
| 다단계 판단/계획 필요 | `agent` |
| 반복 가능한 정형 작업 | `skill` |
| 외부 API/DB 호출 | `tool` |
| 분류/임베딩/예측 | `model` |
| LLM reasoning 없이 규칙 실행 | `tool` 또는 `skill` |
