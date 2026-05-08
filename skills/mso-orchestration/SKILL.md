---
name: mso-orchestration
description: |-
  MSO(Multi-Swarm Orchestrator) 스킬 팩 오케스트레이터. 상시 로드 스킬.
  워크플로우 설계·실행·최적화·거버넌스 관련 모든 요청의 진입점.
  트리거: "워크플로우 설계", "태스크 그래프", "실행 설계", "Goal→Task",
  "멀티에이전트 협업", "에이전트 디스패치", "티켓 관리",
  "워크플로우 최적화", "automation level 판단", "프로세스 최적화",
  "APO", "프롬프트 튜닝", "경량 모델", "llm-as-a-judge",
  "MSO", "mso", "거버넌스 검증", "감사 로그", "CC 계약",
  "멀티 프로바이더", "second opinion", "provider 비교", "collaborate",
  "codex 비교", "gemini 비교", "여러 모델", "ai-collaborator".
---

# mso-orchestration

팩 정의: [references/pack_config.json](references/pack_config.json)

---

## 오케스트레이터 역할

라우터 + 파이프라인 제어기다. 서브스킬 내부 로직(Fallback Policy, OTel 등)은 복제하지 않고 서브스킬에 위임한다.  
컨텍스트 전달은 파일 기반: `.mso-context/active/<run_id>/`

---

## 1. 요청 분석 — 인텐트 → 파이프라인 매핑

| 인텐트 | 신호 키워드 | 파이프라인 |
|--------|-----------|----------|
| 신규 워크플로우 설계 | "워크플로우 만들어", "태스크 그래프", "Goal→", "새 자동화" | [A] |
| 기존 워크플로우 최적화 | "병목", "automation level", "최적화", "느려" | [B] |
| 모델·프롬프트 개선 | "APO", "프롬프트 튜닝", "라벨 불일치", "경량 모델" | [C] |
| 거버넌스·감사 | "검증", "governance", "감사 로그", "CC 계약" | [D] |
| 멀티 프로바이더 실행 | "second opinion", "멀티 프로바이더", "여러 모델 비교", "collaborate", "codex/gemini 비교" | [E] |

특정 서브스킬이 직접 언급된 경우: 해당 스킬만 로드하여 위임.

---

## 2. 서브스킬 로드 절차

```
1. 인텐트 → 파이프라인 결정
2. Read: ~/.skill-modules/mso-skills/{SKILL_NAME}/SKILL.md
3. 입력 스펙 확인 → context 파일 경로 파악
4. 스킬 워크플로우 실행 위임
5. 완료 아티팩트 경로 사용자에게 보고
```

---

## 3. 캐노니컬 파이프라인

### [A] 신규 워크플로우 설계

```
mso-workflow-topology-design  →  workflow_topology_spec.json
mso-mental-model              →  directive_binding.json
mso-execution-design          →  execution_graph.json
mso-task-execution            →  node_snapshots + 실행 결과
```

각 스킬은 이전 스킬의 출력 파일을 입력으로 소비한다.

### [B] 기존 워크플로우 최적화

```
mso-observability      →  병목 리포트
mso-workflow-optimizer →  최적화 제안 / Automation Level 판정
```

### [C] 모델·프롬프트 개선

```
mso-apo-prompt-optimization  →  불일치 분석 + 프롬프트 후보
mso-model-optimizer          →  경량 모델 학습 계획 (선택)
```

### [D] 거버넌스·감사

| 목적 | 스킬 |
|------|------|
| CC 계약 검증 | `mso-skill-governance` |
| 실행 로그 조회 | `mso-agent-audit-log` |
| 멀티에이전트 디스패치 | `mso-agent-collaboration` |

### [E] 멀티 프로바이더 실행

```
mso-agent-collaboration (collaborate.py)  →  provider별 응답 JSON
```

`mso-agent-collaboration` 스킬 로드 후 `collaborate.py` 사용:
- `run --all`: 전체 프로바이더에 동일 프롬프트 전송 (second opinion)
- `run --tasks "provider@model:prompt:id"`: 프로바이더별 역할 분리
- `swarm start`: tmux 기반 장기 실행 swarm 세션

---

## 4. 실행 종료 조건

| 파이프라인 | 종료 조건 |
|-----------|---------|
| [A] 신규 설계 | `execution_graph.json` 존재 + 모든 node_snapshot 완료 상태 |
| [B] 최적화 | 최적화 보고서 생성 + 사용자 승인 |
| [C] APO | 프롬프트 후보 출력 완료 |
| [D] 거버넌스 | 검증 결과 출력 |
| [E] 멀티 프로바이더 | provider별 응답 JSON 출력 완료 |

결과 요약을 사용자에게 보고하고 아티팩트 경로를 명시한다.

---

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
