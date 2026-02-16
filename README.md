---
name: multi-swarm-orchestrator
version: "0.0.1"
status: implemented
---

# Multi-Swarm Orchestrator (v0.0.1)

운영 환경 바인딩을 제거하고, `00~07` 스킬(논리 00 = `mso-skill-governance`)을 독립 실행 가능한 팩으로 재구성한 실행 패키지입니다.

## 핵심 목표
- SKILL/모듈/참조/스크립트 구조 정규화
- AAOS/COF/Agora 고정 문자열 제거
- ai-collaborator는 런타임 의존성 + graceful fallback
- CC-01~CC-05 계약 검증 자동화
- 설계/운영 파이프라인 샘플 실행 가이드 제공

## 루트 구성
- `skills/mso-skill-governance/` (논리 00)
- `skills/mso-workflow-topology-design/`
- `skills/mso-mental-model-design/`
- `skills/mso-execution-design/`
- `skills/mso-task-context-management/`
- `skills/mso-agent-collaboration/`
- `skills/mso-agent-audit-log/`
- `skills/mso-observability/`
- `rules/ORCHESTRATOR.md`
- 각 스킬 `scripts/`와 `schemas/`에 내재화된 실행/검증 엔트리
- `config.yaml`

## 실행 진입점(문서 기반)
`01.product/v0.0.1/rules/ORCHESTRATOR.md`는 실행 라우팅 지침을 정의한 문서입니다.
실제 통합 실행은 아래 샘플 CLI를 사용합니다.

```bash
python3 skills/mso-skill-governance/scripts/run_sample_pipeline.py \
  --goal "요구사항 분석을 위한 테스트 파이프라인" \
  --task-title "샘플 티켓 생성"
```

## 필수 산출물 위치
- `02.test/v0.0.1/outputs/workflow_topology_spec.json`
- `02.test/v0.0.1/outputs/mental_model_bundle.json`
- `02.test/v0.0.1/outputs/execution_plan.json`
- `02.test/v0.0.1/task-context/tickets/*.md`
- `02.test/v0.0.1/observations/*.json`

## 의존성 정책
- `mso-agent-collaboration`은 `03_AgentsTools/02_ai-collaborator`를 **런타임 resolve**로만 사용합니다.
- 미설치 시에도 나머지 파이프라인은 실패 없이 `fallback` 결과를 생성합니다.

## AAOS 의존성 제거 체크리스트
- 고정 AAOS 경로/비표준 메타 참조
- 런타임 바인딩 외부 컨텍스트 참조
- scope/lifetime 기반의 고정 라이프사이클 규칙
- legacy path-only 의존성

## 빠른 검증
```bash
python3 skills/mso-skill-governance/scripts/check_deps.py --config config.yaml
python3 skills/mso-skill-governance/scripts/validate_all.py
```

## 6c 스키마 검증 (jsonschema + 대체 경로)
```bash
# 1) jsonschema 설치(원하면 실행)
./skills/mso-skill-governance/scripts/manage_jsonschema_env.sh install
#    (오프라인 환경에서는 설치가 실패할 수 있으며, 이 경우 3번 fallback을 사용하세요.)
#    (설치 대상은 `skills/mso-skill-governance/scripts/requirements-jsonschema.txt`에 선언됩니다.)

# 2) venv 내부 python으로 정식 jsonschema 검증(권장)
./skills/mso-skill-governance/scripts/manage_jsonschema_env.sh run \
  python3 skills/mso-skill-governance/scripts/validate_schemas.py --json

# 3) jsonschema가 없어도 기본 required-key 기반 검증으로 동작
python3 skills/mso-skill-governance/scripts/validate_schemas.py --json

# 4) 필요 시 venv 제거(삭제하면 의존성이 사라짐)
./skills/mso-skill-governance/scripts/manage_jsonschema_env.sh uninstall
```
