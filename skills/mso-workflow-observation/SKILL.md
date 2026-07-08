---
name: mso-workflow-observation
version: "0.8.2"
description: "Workflow observation alias. `mso-graph-observability`의 workflow scope를 감싸 `execution-rail.md`, `artifact-stream-graph.md`, `repository-graph.md`를 생성한다."
triggers:
  - "mso-workflow-observation"
  - "workflow observation"
  - "workflow graph 노출"
  - "workflow graph 보여줘"
  - "워크플로우 그래프 노출"
  - "워크플로우 관측"
---

# mso-workflow-observation

`mso-graph-observability`의 workflow 관측 기능을 더 좁고 명시적인 이름으로 노출하는 alias skill이다.

## What

Workflow TTL ABox를 읽어 사람이 확인 가능한 execution rail / artifact stream / repository graph Markdown을 생성한다.

주요 산출물:

- `agent-context/observability/graph/workflow-subgraph-index.md`
- `agent-context/observability/graph/<scope>/execution-rail.md`
- `agent-context/observability/graph/<scope>/repository-graph.md`
- `agent-context/observability/graph/<scope>/artifact-stream-graph.md`
- `agent-context/observability/workflow-ssot-report.md`

## Rule

- 원본은 `agent-context/workflow/**/*.abox.ttl`이다.
- Markdown graph는 파생 산출물이므로 직접 고치지 않는다.
- graph 누락이나 잘못된 edge는 workflow TTL을 수정한 뒤 observation을 재실행한다. `execution-rail.md`는 control-only, `repository-graph.md`는 artifact stream까지 포함한 통합 뷰다.
- legacy YAML은 topology source가 아니라 migration input이다.

## CLI

프로젝트 루트에서 실행한다.

```bash
python3 skills/mso-workflow-observation/scripts/mso-workflow-observation.py --root .
```

이 명령은 내부적으로 다음 canonical renderer를 호출한다.

```bash
python3 skills/mso-graph-observability/scripts/observe_graph.py --root .
```

## Relationship

- Canonical implementation: `mso-graph-observability`
- Workflow shape owner: `mso-workflow-design`
- Generated graph consumer: human/operator, downstream repository docs, review workflow
