---
name: mso-orchestration
description: |
  MSO(Multi-Swarm Orchestrator) 스킬 팩의 진입점.
  다음 상황에 사용한다:
  (1) MSO 스킬 팩 설치·설치 상태 확인
  (2) 특정 요청을 어떤 MSO 스킬이 처리해야 하는지 판단
  (3) MSO 팩 거버넌스 검증 실행
  팩 정의(required_skills, version 등)는 references/pack_config.json이 단일 소스.
---

# mso-orchestration

팩 정의: [references/pack_config.json](references/pack_config.json)

## 설치

```bash
git clone https://github.com/WMJOON/multi-swarm-orchestrator.git
cd multi-swarm-orchestrator
./install.sh
```

## 거버넌스 검증

```bash
python3 ~/.claude/skills/mso-skill-governance/scripts/validate_gov.py \
  --pack-root ~/.claude --pack mso --json
```

## 서브스킬 On-Demand 로딩

`~/.claude/skills/`에 서브스킬이 없을 때(minimal 설치 상태), 아래 명령으로 실제 경로를 확인 후 Read한다.

```bash
python3 -c "
import pathlib
p = pathlib.Path('~/.claude/skills/mso-orchestration').expanduser().resolve().parent
print(p / 'SKILL_NAME' / 'SKILL.md')
"
```

`SKILL_NAME`을 아래 라우팅 테이블의 스킬명으로 교체하면 절대 경로가 반환된다. 반환된 경로를 Read 도구로 읽으면 해당 스킬이 로드된다.

## 스킬 라우팅

| 요청 유형 | 담당 스킬 |
|----------|----------|
| Goal → Task Graph 설계 | `mso-workflow-topology-design` |
| Mental Model · Directive 바인딩 | `mso-mental-model` |
| Execution Graph 설계 | `mso-execution-design` |
| 워크플로우 실행 · Fallback | `mso-task-execution` |
| 티켓 관리 · 멀티에이전트 Dispatch | `mso-agent-collaboration` |
| 실행 로그 · SQLite SoT | `mso-agent-audit-log` |
| 패턴 분석 · HITL 체크포인트 | `mso-observability` |
| Automation Level 판단 · 최적화 | `mso-workflow-optimizer` |
| 경량 모델 학습 · 배포 | `mso-model-optimizer` |
| 스킬 구조 · CC 계약 검증 | `mso-skill-governance` |
