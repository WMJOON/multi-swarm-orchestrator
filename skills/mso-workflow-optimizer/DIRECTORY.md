# mso-workflow-optimizer — Directory Structure

> 이 문서는 스킬의 파일 구성과 각 파일의 역할을 정의한다.
> 새 모듈 추가 시 이 템플릿의 규약을 따른다.

---

## 디렉토리 트리

```
{mso-workflow-optimizer}/
├── SKILL.md                                # 스킬 진입점. frontmatter + 실행 프로세스 + 모듈 요약
├── DIRECTORY.md                            # 이 파일. 디렉토리 구성 명세
├── core.md                                 # 용어 정의 + Input/Output 인터페이스 + 처리 규칙 + 에러 핸들링
├── .env.example                            # llm-as-a-judge API 키 템플릿 (실제 API 키 미포함)
│
├── configs/
│   └── llm-model-catalog.yaml              # provider별 분석 중심 모델 후보 + 권장 기본값 + 출처 URL
│
├── modules/
│   ├── modules_index.md                    # 모듈 인덱스. Core/Operational 분류
│   │
│   │   # ── Core Modules (Phase 기반) ──
│   ├── module.analysis-optimizing.md      # Phase 1–5: 전체 오케스트레이션 + operation-agent 루프
│   ├── module.agent-decision.md            # Phase 2: 3-Signal Automation Level 판단
│   ├── module.automation-level.md          # Phase 3: Level 10/20/30 실행 흐름
│   ├── module.hitl-feedback.md             # Phase 5: HITL 피드백 수렴 + goal 산출
│   │
│   │   # ── Operational Modules (반복 최적화) ──
│   ├── module.process-optimizing.md        # 프로세스 실행·분석·평가 반복 워크플로우
│   └── module.llm-as-a-judge.md    # LLM 라벨링 + TF-PN 정량 검증 + HITL 루프
│
├── scripts/
│   └── select_llm_model.py                 # 카탈로그 조회/검증 + env export 헬퍼
│
└── schemas/
    └── optimizer_result.schema.json        # 실행 결과 JSON Schema (decision_output + goal + llm_as_a_judge)
```

---

## 파일 역할 정의

### 루트 파일

| 파일 | 역할 | 로드 조건 |
|------|------|-----------|
| `SKILL.md` | **항상 최초 로드**. 스킬 개요, 5-Phase 프로세스 요약, Operational Modules 요약, Pack 관계, 파일 참조 테이블 | 스킬 호출 시 |
| `DIRECTORY.md` | 디렉토리 구성 명세. 신규 모듈 추가·구조 변경 시 참조 | 구조 변경 시 |
| `core.md` | 용어 사전, Input/Output 인터페이스 명세, Processing Rules, Error Handling, Security, when_unsure | SKILL.md에서 참조 시 |
| `.env.example` | `llm-as-a-judge`용 ENV 템플릿 (`LLM_API_PROVIDER`, `LLM_API_KEY` 등) | API 연결 설정 시 |

### configs/

| 파일 | 역할 | 로드 조건 |
|------|------|-----------|
| `llm-model-catalog.yaml` | Provider별 분석 중심 모델 카탈로그 + 권장 default + 1차 출처 URL | 모델 선택/교체 시 |

### modules/

| 파일 | 분류 | 로드 조건 |
|------|------|-----------|
| `modules_index.md` | 인덱스 | 모듈 탐색 시 |
| `module.analysis-optimizing.md` | Core | 5-Phase 전체 흐름 + operation-agent 루프 참조 시 |
| `module.agent-decision.md` | Core | Phase 2 실행 시 |
| `module.automation-level.md` | Core | Phase 3 실행 시 |
| `module.hitl-feedback.md` | Core | Phase 5 실행 시 |
| `module.process-optimizing.md` | Operational | 프로세스 최적화 요청 시 |
| `module.llm-as-a-judge.md` | Operational | llm-as-a-judge 평가 요청 시 (독립 또는 서브프로세스) |

### schemas/

| 파일 | 역할 | 로드 조건 |
|------|------|-----------|
| `optimizer_result.schema.json` | 실행 결과 출력 검증 스키마 | 결과 저장·검증 시 |

### scripts/

| 파일 | 역할 | 로드 조건 |
|------|------|-----------|
| `select_llm_model.py` | 카탈로그 기반 모델 목록 출력/검증 + env export 명령 생성 | 사용자가 provider/model을 고를 때 |

---

## 모듈 분류 체계

```
Core Modules ──── Phase 기반. 5-Phase 프로세스의 특정 Phase에 종속.
                  SKILL.md의 실행 프로세스 흐름에서 직접 참조됨.

Operational Modules ── 반복 최적화. Phase에 종속되지 않고 독립/서브프로세스로 실행.
                       SKILL.md의 Operational Modules 섹션에서 참조됨.
```

---

## 모듈 추가 규약

새 모듈을 추가할 때 다음 체크리스트를 따른다:

### 1. 모듈 파일 생성

```
modules/module.{module-name}.md
```

**필수 섹션:**

| 섹션 | 설명 |
|------|------|
| `# module.{name}` + blockquote | 한 줄 요약 |
| `## 개요` | 모듈 목적과 기존 구조와의 관계 |
| `## 워크플로우` | **Mermaid** 플로우 다이어그램 (drawio 대응) |
| `## 노드 정의` | 노드명, 유형, 설명 테이블 |
| `## 실행 단계` | Step N 형식으로 순차 기술 |
| `## 에러 처리` | 상황-처리 테이블 |

> **다이어그램 규칙**: 워크플로우·흐름 다이어그램은 **반드시 Mermaid(`\`\`\`mermaid`)** 로 작성한다.
> ASCII 다이어그램은 사용하지 않는다. Obsidian 렌더링 호환을 위해 `flowchart TD`/`flowchart LR`을 기본으로 사용한다.

**선택 섹션 (해당 시):**

| 섹션 | 조건 |
|------|------|
| `## 호출 인터페이스` | 다른 모듈에서 서브프로세스로 호출될 때 |
| `## 반환값` | 호출자에게 돌려줄 결과가 있을 때 |
| `## HITL 피드백 처리` | human-in-the-loop이 포함될 때 |
| `## 수렴 기준` | 반복 루프가 포함될 때 |
| `## 산출물 구조` | 리포트·데이터 템플릿이 있을 때 |

### 2. 인덱스 업데이트

`modules/modules_index.md`에 해당 분류(Core/Operational)에 행 추가.

### 3. SKILL.md 업데이트

- Core Module → 해당 Phase 섹션에 참조 링크 추가
- Operational Module → `## Operational Modules` 섹션에 요약 + 흐름도 추가
- `## 상세 파일 참조` 테이블에 행 추가

### 4. core.md 업데이트

- `## Terminology`에 새 용어 추가
- `## Security / Constraints`에 해당 규칙 추가 (있을 경우)

### 5. schemas/ 업데이트

`optimizer_result.schema.json`의 `properties`에 모듈 결과 필드 추가 (선택적, optional 필드로).

### 6. 검증

- [ ] drawio 원본의 노드·엣지와 모듈 문서의 워크플로우 다이어그램 일치 확인
- [ ] 이중 입력(fan-in), 분기(fan-out) 관계가 정확히 기술되었는지 확인
- [ ] 호출 인터페이스의 입력·반환값이 호출자와 피호출자 양쪽에서 일치하는지 확인
- [ ] 산출물 경로가 `{workspace}/.mso-context/active/<run_id>/optimizer/` 하위로 일관되는지 확인
- [ ] modules_index.md, SKILL.md, core.md 교차 참조 정합성 확인

---

## 산출물 경로 규약

모든 런타임 산출물은 아래 네임스페이스를 따른다:

```
{workspace}/.mso-context/active/<run_id>/optimizer/
├── level10_report.md                   # Phase 3: Level 10
├── level20_report.md                   # Phase 3: Level 20
├── level30_report.md                   # Phase 3: Level 30
├── goal.json                           # Phase 5: 최종 goal
│
├── process/                            # process-optimizing 모듈
│   ├── analysis-report.md
│   ├── evaluation-report.md
│   └── improvement-evaluation-report.md
│
└── llm-as-a-judge/                              # llm-as-a-judge 모듈
    ├── sample.csv
    ├── labeled-data.csv
    ├── TF-PN.csv
    └── report.md
```

**네이밍 규칙:**
- Core Phase 산출물: 루트에 `level{N}_report.md`, `goal.json`
- Operational Module 산출물: `{module-short-name}/` 하위 디렉토리
- 모듈 경로명: process-optimizing → `process/`, llm-as-a-judge → `llm-as-a-judge/`
