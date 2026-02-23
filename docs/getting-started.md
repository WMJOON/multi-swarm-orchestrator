# 시작하기

## 디렉토리 구조

```
skills/
├── mso-skill-governance/            ← 계약 검증, 구조 점검
├── mso-workflow-topology-design/    ← 목표 → 노드 구조
├── mso-mental-model-design/         ← 노드별 사고 모델
├── mso-execution-design/            ← 실행 계획 생성 (execution_graph)
├── mso-task-context-management/     ← 티켓 관리
│   └── templates/                   ← PRD.md, SPEC.md, ADR.md
├── mso-agent-collaboration/         ← 멀티에이전트 디스패치 (branch/merge)
├── mso-agent-audit-log/             ← 감사 로그 (SQLite, node_snapshots)
│   └── history/                     ← 스키마 버전 스냅샷
├── mso-observability/               ← 관찰, 환류 (패턴 분석)
│   └── templates/                   ← HITL_ESCALATION_BRIEF.md, RUN_RETROSPECTIVE.md
├── mso-orchestrator/                ← 메타 오케스트레이션 (라우팅, 프로세스, 템플릿 인덱스)
└── _shared/                         ← 공통 유틸 (runtime_workspace.py)
rules/
└── ORCHESTRATOR.md                  ← 불변 정책
docs/
├── architecture.md                  ← Git-Metaphor 모델, 전체 아키텍처
├── pipelines.md                     ← 3대 파이프라인, CC 계약, 티켓 생명주기
├── getting-started.md               ← 이 문서
├── usage_matrix.md                  ← Phase × Swarm × Role 매트릭스
└── changelog.md                     ← 버전별 변경 이력
```

각 스킬 디렉토리의 `SKILL.md` 파일만 확인하면 해당 스킬의 목적, 입출력, 실행 절차를 모두 파악할 수 있다. `modules/`나 `schemas/`는 상세 구현 확인 시에만 참조한다.

v0.0.3부터는 별도 `config.yaml` 없이 동작한다. 환경별 오버라이드는 `MSO_WORKSPACE_ROOT`, `MSO_OBSERVATION_ROOT`, `MSO_OBSERVER_ID`로만 처리한다.

---

## 1. 워크플로우 설계 (Design)

```bash
RUN_ID="YYYYMMDD-msowd-onboarding"

# 목표(Goal)를 입력하면 노드 구조(Topology)가 생성된다.
python3 skills/mso-workflow-topology-design/scripts/generate_topology.py \
  --run-id "$RUN_ID" \
  --skill-key msowd \
  --case-slug onboarding \
  --goal "사용자 온보딩 프로세스 설계"

# 각 노드에 사고 모델(Mental Model)을 매핑한다.
python3 skills/mso-mental-model-design/scripts/build_bundle.py \
  --run-id "$RUN_ID" \
  --skill-key msowd \
  --case-slug onboarding

# 두 결과를 통합하여 execution_graph를 생성한다.
python3 skills/mso-execution-design/scripts/build_plan.py \
  --run-id "$RUN_ID" \
  --skill-key msowd \
  --case-slug onboarding
```

---

## 2. 티켓 운영 (Ops)

```bash
TASK_ROOT="workspace/.mso-context/active/$RUN_ID/40_collaboration/task-context"

python3 skills/mso-task-context-management/scripts/create_ticket.py \
  "온보딩 플로우 구현" \
  --path "$TASK_ROOT"

python3 skills/mso-task-context-management/scripts/archive_tasks.py \
  --path "$TASK_ROOT"
```

---

## 3. 검증 (Validation)

```bash
# 스키마 정합성 확인
python3 skills/mso-skill-governance/scripts/validate_schemas.py \
  --run-id "$RUN_ID" \
  --skill-key msogov \
  --case-slug onboarding \
  --json

# 전체 거버넌스 점검
python3 skills/mso-skill-governance/scripts/validate_all.py \
  --run-id "$RUN_ID" \
  --skill-key msogov \
  --case-slug onboarding

# 설계 → 운영 → 인프라 통합 테스트
python3 skills/mso-skill-governance/scripts/run_sample_pipeline.py \
  --goal "테스트 파이프라인" \
  --task-title "샘플 티켓" \
  --skill-key msowd \
  --case-slug onboarding
```
