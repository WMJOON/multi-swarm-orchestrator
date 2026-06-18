# Workflow Conventions — Project Template

> **이 문서는 예시(template) 입니다.** mso-workflow-design 스킬은 네이밍 컨벤션을 강제하지 않습니다.
> 프로젝트별로 이 파일을 복사·수정하여 `docs/`, `CLAUDE.md` 등 프로젝트 위치에 두고 합의된 규칙으로 사용하세요.

스킬이 보장하는 것:
- 노드 type 분류 (step/decision/group/phase) 와 필수 필드
- judge taxonomy (HITL/HITLFE/HOTL/HOOTL) 및 branches.on 정합성
- id unique, status enum 등 구조 invariant

아래 컨벤션은 **AI Chatbot 1.0 프로젝트의 예시**입니다.

---

## 1. 노드 ID 네이밍

### 패턴
```
{module-abbr}-{type-code}-{NNN}
```

- `module-abbr` — 2~3자 소문자 모듈 약어
- `type-code` — `s` (step), `d` (decision), `g` (group)
- `NNN` — 3자리 일련번호

### 모듈 약어 매핑

| 모듈 (index.yaml id) | 약어 |
|--------------------|----|
| `01.ingestion` | `cd` |
| `02.policy-engine` | `acp` |
| `03.data-masking` | `sdm` |
| `04.vendor-x` | `ai7` |
| `10.RAG-Corpus-Dataset` | `rcd` |

### 예시

```
acp-s-001     ✓ step
acp-d-001     ✓ decision
acp-g-001     ✓ group
acp-s-1       ✗ NNN 1자리
acp_s_001     ✗ underscore
```

### 불변 원칙

한번 부여된 id 는 변경 금지 (worklog/auditlog 추적 키).

---

## 2. Label 동사 어휘

`{동사} {목적어} [{맥락}]` 패턴.

| 동사 | 의미 |
|----|----|
| 분석 | 입력을 읽고 결과 도출 |
| 생성 | 새 산출물 작성 |
| 수정 | 기존 파일 변경 |
| 복제 | 파일 복사 |
| 이동 | 파일 위치 변경 |
| 검증 | 품질 확인 |
| 평가 | 측정·채점 |
| 검토 | (HITL) 사람 승인 |

decision 노드는 `검토 / 평가 / 판정` 동사를 권장.

---

## 3. Phase 어휘

MSO 표준 3-phase:

| Phase ID | 의미 |
|----------|----|
| `discovery` | 요구사항·범위·전제 확정 |
| `development` | 산출물 작성 |
| `testing` | 측정·검증 |

프로젝트가 다른 어휘를 쓰려면 여기 명시한다.

### Success Criteria 강제 규칙 (프로젝트 정책)

- `testing` phase 에 `success_criteria` 3개 이상 필수
- `discovery`, `development` 는 optional

---

## 4. Directories Role 어휘

`step.directories[].role` 의 권장 enum:

| Role | 의미 |
|----|----|
| `input` | 이 step 이 읽어오는 소스 |
| `output` | 이 step 이 생성/배포하는 결과 |
| `reference` | 읽기 전용 참고 자료 |
| `instruction` | 실행 규칙·정책 문서 |

`directories.path` 는 scaffold(`index.yaml`)에 등록된 경로여야 한다.

---

## 5. Owner 형식

`decision.owner` — `{name}@example.com` 이메일 형식.

---

## 6. Anti-Patterns

### ❌ 분기를 step 의 boolean 필드로 표현
```yaml
# Bad
- type: step
  id: acp-s-005
  automation_gate: HITL    # ✗ — decision 노드로 분리
```

### ❌ judge 와 어긋난 branch 조건
```yaml
# Bad
- type: decision
  judge: HOTL
  branches:
    - on: approved          # ✗ HOTL 허용값: passed, flagged
```

### ❌ 같은 id 재사용
```yaml
# Bad
- id: acp-s-001  # phase A
...
- id: acp-s-001  # phase B  ✗ unique 위반
```
