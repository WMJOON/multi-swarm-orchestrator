# Naming Conventions — Project Template

> **이 문서는 예시(template) 입니다.** mso-scaffold-design 스킬은 컨벤션을 강제하지 않습니다.  
> 프로젝트별로 이 파일을 복사·수정하여 `docs/`, `CLAUDE.md` 등 프로젝트 위치에 두고 합의된 규칙으로 사용하세요.

스킬이 보장하는 것:
- 필수 필드 존재 (id, path, description, …)
- 구조적 정합성 (id ↔ path, references → 존재 모듈 id, subdir path 끝 `/`)

아래 컨벤션은 **AI Chatbot 1.0 프로젝트의 예시**입니다.

---

## 1. Module ID

### 패턴
```
{NN}.{name}
```

- `NN` — 2자리 숫자 정렬 prefix (`01`, `02`, ..., `99`)
- `name` — kebab-case 또는 PascalCase 허용. 영문/숫자/`-`/`_` 사용.

### 정렬 Prefix 의미

| Prefix | 용도 | 예 |
|--------|------|---|
| `00.` | meta, framework, project-level | (현재 사용 모듈 없음) |
| `01.` | primary data/analysis | `01.consultdata` |
| `02.` | policy / chatbot-side | `02.AI-Chatbot-Policy` |
| `03.` | sensitive-data / sanitization | `03.sensitive-data-masking` |
| `04.` | external integration / vendor | `04.AIKON7` |
| `10.` | datasets / corpus | `10.RAG-Corpus-Dataset` |
| `99.` | archive / experimental | (현재 사용 모듈 없음) |

### 예시

```
01.consultdata           ✓
02.AI-Chatbot-Policy     ✓
04.AIKON7                ✓
10.RAG-Corpus-Dataset    ✓
consultdata              ✗ (prefix 누락)
1.consultdata            ✗ (NN 한자리)
```

### 불변 원칙

한번 부여된 module id 는 변경 금지. workflow YAML 의 `directories.path` 가 이를 참조한다.

만약 rename이 필요하면:
1. 새 id 로 module 항목 추가
2. 이전 module 에 `status: deprecated` 표시
3. workflow YAML 의 path 참조를 일괄 변경
4. 일정 기간 후 deprecated 항목 삭제

---

## 2. Subdir Path

### 패턴 (권장)
```
{NN}.{kebab-case}/
```

- 끝에 `/` **필수** (디렉토리 표시)
- `NN` — 모듈 내 정렬 prefix
- `kebab-case` — 소문자 + 하이픈

### 예시
```
00.context/        ✓
01.scripts/        ✓
02.data/           ✓
03.reports/        ✓
99.history-policy/ ✓
04.modules/        ✓
04.Modules/        ✗ (대문자)
04.modules         ✗ (끝 / 누락)
```

### 예외: Prefix 없는 도메인 디렉토리

특수 패키지나 컨테이너 디렉토리는 prefix 생략 가능.

```
customer-service-analytics/   ✓ (도메인 디렉토리)
message-editor/               ✓
artifacts_v1.0.0/             ✓ (버전 디렉토리)
```

### Subdir Prefix 컨벤션 (모듈 내)

| Prefix | 통상 역할 (role) |
|--------|----------------|
| `00.` | context, framework, planning_context |
| `01.` | scripts, hand-off-policy (primary) |
| `02.` | data, draft |
| `03.` | reports |
| `04.`, `05.` | modules |
| `99.` | planning, history-*, archive |

---

## 3. Role

`subdirs[].role` 의 enum 값. 통상적인 prefix → role 매핑:

| Path | Role |
|------|------|
| `00.context/` | `context` |
| `00.framework/` | `framework` |
| `01.scripts/` | `scripts` |
| `02.data/` | `data` |
| `02.draft/` | `draft` |
| `03.reports/` | `reports` |
| `04.modules/`, `05.modules/` | `modules` |
| `99.planning/` | `planning` |
| `99.history-*/` | `history` |
| `artifacts_v*/` | `artifacts` |

role 은 optional이지만 명시하면 workflow YAML 의 `directories.role` 과 의미가 정합된다:
- scaffold `role: scripts` ↔ workflow `role: input/output` 매핑 가능

---

## 4. Key Files

`modules[].key_files` 에 명시하는 루트 파일:

| File | 용도 |
|------|------|
| `README.md` | 모듈 개요 |
| `CLAUDE.md` | Claude Code 모듈별 지침 |
| `AGENTS.md` | Agent 정의 |
| `index.yaml` | (sub-)index, 모듈 내 추가 인벤토리 가능 |

---

## 5. Anti-Patterns

### ❌ Module path가 id와 불일치

```yaml
# Bad
- id: 04.AIKON7
  path: aikon7/             # id != path
```

### ❌ 끝 슬래시 누락

```yaml
# Bad
- path: 02.data             # / 없음
```

### ❌ Prefix 없는 모듈 id

```yaml
# Bad
- id: aikon7                # 정렬 prefix 누락
```

### ❌ Deprecated 모듈 직접 삭제

workflow YAML 이 참조 중일 수 있으니 `status: deprecated` 표시 후 일정 기간 유지.
