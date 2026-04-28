# module.motif-vocabulary

> Source: v0.0.7-2 §1 Workflow Topology Motif

## Purpose

반복적으로 발생하는 워크플로우 구조 패턴(Motif)을 정의하고, 기존 `topology_type` 값과 매핑한다.

---

## Motif 정의

| Motif | 구조 | topology_type 매핑 | 적합 상황 |
|-------|------|--------------------|----------|
| **Chain** | `A → B → C → D` | `linear` | 순차 데이터 처리, 보고서 생성, 생산 공정 |
| **Star** | A(hub) ↔ B,C,D,E | `fan_out` (coordinator 변형) | Planner Agent 중심 orchestration, distribution hub |
| **Fork/Join** | A → {B,C} → D | `fan_out` + `fan_in` | multi-agent research, map-reduce |
| **Loop** | A → B → C → A | `loop` | LLM refinement loop, critic-feedback, 품질 검사 |
| **Diamond** | A → {B,C} → D | `fan_in` (명시적 의존) | 데이터 통합, multi-source analysis, dependency build |
| **Switch** | A → B or C (조건) | `fan_out` (mutually exclusive) | intent routing, decision engine, rule-based branching |

---

## Fork/Join vs Diamond 구분

| 특성 | Fork/Join | Diamond |
|------|-----------|---------|
| 분기 목적 | 병렬 독립 처리 | 각 경로가 서로 다른 의존성 충족 |
| 합류 조건 | 모든 경로 완료 후 | 명시적 선행 의존 충족 후 |
| topology_type | `fan_out` + `fan_in` | `fan_in` |

## Star vs Switch 구분

| 특성 | Star | Switch |
|------|------|--------|
| 분기 수 | 다수 동시 활성 | 조건에 따라 하나만 활성 |
| 중앙 노드 역할 | coordinator (지속 관여) | router (경로 선택 후 이탈) |

---

## 사용 규칙

- SKILL.md Phase 2에서 Motif를 먼저 식별한 후 `topology_type`으로 변환한다.
- Workflow spec JSON의 `metadata.motif` 필드에 선택된 Motif 이름을 기록한다.
- 복합 패턴(예: Chain 내부에 Fork/Join)은 `motif_composition[]` 배열로 표현한다.

## Output 필드

```json
"metadata": {
  "motif": "chain|star|fork_join|loop|diamond|switch",
  "motif_composition": []
}
```
