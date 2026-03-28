# module.tool-lifecycle

> Smart Tool의 Lifecycle(Local → Symlinked → Global) 승격·강등·검증 절차를 정의한다.

---

## 역할

Tool Lifecycle은 "어디에 배치할 것인가"(배치 scope)의 관심사다. `mso-workflow-optimizer`의 Tier Escalation("어떤 수준으로 처리할 것인가")과는 직교하는 별개의 축이다.

이 모듈은 **거버넌스**의 관심사로, 승격/강등 절차의 정의와 검증을 담당한다. "승격할 때가 됐다"는 신호는 `mso-observability`의 `module.model-monitoring`이 발생시킨다(CC-15).

---

## Lifecycle 상태

```
[Local]  ──── frequency↑ + pattern stable ────►  [Symlinked]  ──── abstraction 검증 ────►  [Global]
 workspace 내                                       global_links 경유                        global registry 등록
 특화 로직 포함                                      여러 workspace 재사용                     SKILL.md 공식화
 직접 path 참조                                      symlink 경유 참조                         전역 트리거 적용
```

| 상태 | 경로 패턴 | 의미 |
|------|-----------|------|
| Local | `{workspace}/tools/{tool_name}/` | workspace 내 특화. 생성 시 기본 상태. |
| Symlinked | `~/.claude/global_links/{tool_name}/` ← symlink | global_links 경유로 여러 workspace에서 재사용. |
| Global | `~/.claude/skills/{tool_name}/SKILL.md` | 전역 등록. SKILL.md 공식화 + 트리거 적용. |

> **직접 Global 등록도 허용**: 처음부터 범용으로 설계된 Tool은 lifecycle을 건너뛰고 global에 등록할 수 있다.

---

## 승격 판정 기준

| 지표 | 의미 | Local → Symlinked | Symlinked → Global |
|------|------|-------------------|---------------------|
| `pattern_stability` | `frequency × success_rate` | ≥ 0.4 | ≥ 0.7 |
| `workspace_count` | 재사용된 workspace 수 | ≥ 2 | ≥ 3 |
| `abstraction_score` | workspace-specific 코드 비율 (낮을수록 좋음) | — | ≤ 0.2 |

### `abstraction_score` 측정 방법

```
abstraction_score = (workspace-specific 코드 라인 수) / (전체 코드 라인 수)
```

workspace-specific으로 분류되는 항목:
- 절대 경로 / workspace명 하드코딩
- 특정 도메인 상수 (예: 도메인 전용 라벨셋, 고객사 고유 스키마)
- 특정 workspace의 `audit_global.db` 직접 참조

---

## 승격 절차

### 입력

- 승격 요청: `mso-observability` CC-15 payload 또는 사용자 직접 요청
- `tool_registry.json`의 해당 Tool 엔트리

### 절차

```
1. 승격 요청 수신
   ├── CC-15 payload: { tool_name, current_state, proposed_state, metrics }
   └── 사용자 요청: "이 Tool을 global로 승격해줘"
   ↓
2. abstraction 검증
   ├── workspace-specific 라인 자동 스캔
   │   ├── 절대 경로 패턴: /Users/*, /home/*, C:\*
   │   ├── 도메인 상수: 하드코딩된 라벨셋, 고객사 ID
   │   └── 직접 DB 참조: audit_global.db 절대 경로
   ├── abstraction_score 산출
   └── abstraction_score > 0.2 (Global 승격 시)
       → 승격 보류
       → 파라미터화 작업 목록 제시
   ↓
3. 추상화 실행 (HITL 검토 포함)
   ├── 하드코딩 → config/env 추출
   ├── 도메인 상수 → 파라미터 default로 이동
   └── 직접 DB 참조 → 인터페이스 추상화
   ↓
4. manifest.json의 lifecycle_state 갱신
   ↓
5. 배치 실행
   ├── Symlinked: global_links/ symlink 생성
   └── Global: ~/.claude/skills/{tool_name}/ 디렉토리 생성 + SKILL.md 공식화
   ↓
6. tool_registry.json 갱신
   ├── lifecycle_state 업데이트
   ├── promotion.candidate = false
   └── promotion.blockers = []
   ↓
7. 검증 (Global 승격 시)
   └── N개 workspace에서 정상 동작 확인 후 트리거 등록
```

### 출력

- `manifest.json` — `lifecycle_state` 갱신
- `tool_registry.json` — 해당 엔트리 갱신
- Symlinked: `~/.claude/global_links/{tool_name}/` symlink 생성
- Global: `~/.claude/skills/{tool_name}/SKILL.md` 생성

---

## Symlink 규약

### 경로 패턴

```
# Local 상태
{workspace}/tools/{tool_name}/manifest.json
  → lifecycle_state: "local"

# Symlinked 상태
~/.claude/global_links/{tool_name}/
  → symlink target: {owner_workspace}/tools/{tool_name}/
  → manifest.json의 lifecycle_state: "symlinked"

# Global 상태
~/.claude/skills/{tool_name}/SKILL.md
  → manifest.json의 lifecycle_state: "global"
```

### 쓰기 권한 규칙

| 상태 | 쓰기 권한 | 근거 |
|------|-----------|------|
| Local | 해당 workspace만 | 소유자 workspace |
| Symlinked | `owner_workspace`만 | 다른 workspace는 read-only 참조. 충돌 방지. |
| Global | HITL 승인 후 갱신 | 전역 영향이 있으므로 사람 승인 필수 |

---

## 강등/제거 정책

### 강등 트리거

| 조건 | 강등 방향 | 행동 |
|------|-----------|------|
| `rolling_f1 < critical_threshold` 연속 N회 | Global → Symlinked | 강등 후보 제안 (HITL 승인 필요) |
| `workspace_count = 0` (N일 이상 미사용) | Symlinked → Local | 강등 후보 제안 (HITL 승인 필요) |
| 사용자 직접 요청 | 지정된 방향 | 즉시 실행 |

### 강등 규칙

| 규칙 | 내용 |
|------|------|
| **자동 강등 금지** | 모든 강등은 HITL 승인 필요. 자동 강등은 허용하지 않는다. |
| **강등 시 데이터 보존** | symlink만 제거하고, 원본 Tool 파일은 삭제하지 않는다. |
| **강등 기록** | `tool_registry.json`에 강등 이력 기록 (이전 상태, 강등 사유, 강등 시점). |

### 제거 절차

Tool 완전 제거는 강등과 별개의 행위다.

1. HITL 승인 필수
2. 해당 Tool을 참조하는 다른 Tool/스킬이 없는지 확인 (연결형 KO의 `downstream` 검사)
3. 참조가 있으면 제거 불가 → 참조 제거 후 재시도
4. `tool_registry.json`에서 엔트리 삭제 (soft delete: `lifecycle_state: "removed"`)

---

## CC-15 계약

| 필드 | 내용 |
|------|------|
| CC 번호 | CC-15 |
| 발신 | mso-observability (`module.model-monitoring`) |
| 수신 | mso-skill-governance (`module.tool-lifecycle`) |
| activation_condition | `pattern_stability ≥ promotion_threshold` 감지 시 |
| Payload | `{ tool_name, current_state, proposed_state, metrics: { pattern_stability, workspace_count, abstraction_score }, evidence_refs: [] }` |
| 수신 측 행동 | 승격 절차 Step 2(abstraction 검증)부터 시작 |

---

## 기존 모듈과의 관계

| 모듈 | 관계 |
|------|------|
| `module.registry-scan` | 스킬 폴더 구조 정합성 검사. tool-lifecycle은 Smart Tool의 배치 scope 관리. |
| `module.contract-sync` | CC 계약 정합성 검증. CC-15 추가 시 이 모듈에도 반영 필요. |
| `module.frontmatter-policy` | Tool의 manifest.json 메타데이터 규칙 검증. |

---

## when_unsure

- 승격 요청이 CC-15와 사용자 직접 요청으로 동시에 들어온 경우: 사용자 요청을 우선한다.
- `abstraction_score`를 자동 산출할 수 없는 경우 (스크립트 미구현): 사용자에게 수동 평가를 요청한다.
- Symlinked 상태에서 owner_workspace가 삭제된 경우: 다른 workspace가 소유권을 인계받거나, Global로 승격한다.
