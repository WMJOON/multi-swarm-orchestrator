# module.directive-taxonomy

## Purpose

Directive의 택소노미 구조와 frontmatter 규칙을 정의한다.

---

## 택소노미 구조

```
vertex_registry/
├── analysis/              ← domain
│   ├── dir-001-mece-decomposition.md
│   └── dir-002-root-cause-analysis.md
├── research/
│   └── dir-003-market-size-estimation.md
├── nlp/
│   └── dir-010-summarizer-prompt.md
└── general/               ← fallback domain
    └── dir-999-generic-reasoning.md
```

### 파일명 규칙

`dir-{NNN}-{kebab-case-name}.md`

- `NNN`: 3자리 일련번호 (도메인 내 고유)
- kebab-case: name 필드의 축약형

### taxonomy_path 규칙

- 최소 1단계, 최대 3단계: `[domain]` 또는 `[domain, subcategory]` 또는 `[domain, subcategory, leaf]`
- 1단계는 반드시 디렉토리명(domain)과 일치
- 예: `[analysis, decomposition]`, `[research, quantitative, market_sizing]`

---

## Directive type별 body 가이드

| type | body에 포함할 내용 |
|------|-------------------|
| `framework` | 개념 설명, 적용 절차, 판단 기준, 예시 |
| `instruction` | 단계별 실행 절차, 입출력 형식, 제약 조건 |
| `prompt` | 시스템 프롬프트 전문, 변수 placeholder, 예상 출력 형식 |

---

## Reserved Domains

| domain | 소유자 | 설명 |
|--------|--------|------|
| `mso-governance` | `mso-skill-governance` | MSO 내부 프로세스 규약 (직접 등록하지 않음, 참조만) |
| `general` | system | fallback directive. 도메인 특화 없이 범용 적용 |
