# module.workspace-convention

> Workspace Convention 파일의 로딩·검증·투영을 관리한다. 명시지(visible)와 암묵지(hidden)의 파일시스템 수준 분리를 실행한다.

---

## 역할

MSO의 산출물은 기계가 소비하는 암묵지(`.mso-context/`)와 사람이 확인하는 명시지(`mso-outputs/`)로 분리된다. 이 분리 규칙은 `mso-convention.yaml`에 정의되며, 이 모듈이 convention의 전체 라이프사이클을 관리한다.

---

## Convention 파일 로딩

### 우선순위

```
1. {workspace}/mso-convention.yaml          ← 프로젝트별 커스텀 (최우선)
2. ~/.claude/mso-convention.yaml            ← 사용자 글로벌 커스텀
3. skills/mso-skill-governance/defaults/    ← MSO 기본 convention
   mso-convention.default.yaml
```

### 로딩 규칙

1. 우선순위 순서대로 파일 존재 여부를 확인한다.
2. 첫 번째로 발견된 파일을 로딩한다. (merge가 아닌 override 방식)
3. 어느 경로에도 convention 파일이 없으면, 기본 convention(`mso-convention.default.yaml`)을 사용한다.
4. 로딩된 convention은 `mso-convention.schema.json`으로 스키마 검증한다.

### when_unsure

- convention 파일의 YAML 파싱이 실패한 경우: 에러를 보고하고 기본 convention으로 fallback한다.
- 스키마 검증 실패 시: 어떤 필드가 누락/잘못되었는지 보고하고 기본 convention으로 fallback한다.

---

## Convention 검증

### 스키마 검증

`mso-convention.schema.json`을 기준으로 다음을 확인한다:

| 검증 항목 | 규칙 |
|-----------|------|
| `explicit_knowledge.root` | dot-prefix 금지 (`^[^.]` 패턴) |
| `implicit_knowledge.root` | dot-prefix 필수 (`^\.` 패턴) |
| `projection.trigger` | `on_phase_complete`, `on_run_complete`, `manual` 중 하나 |
| `projection.mode` | `symlink`, `copy`, `render` 중 하나 |
| `structure` 내 각 디렉토리 | `path` + `sources[]` 필수 |
| `sources[].format` | `passthrough` 또는 `md` |

### 의미론적 검증

스키마 검증 외에 추가로 확인하는 항목:

| 검증 항목 | 규칙 |
|-----------|------|
| source 경로 존재 | `sources[].from` 경로 패턴이 `.mso-context/` 하위를 가리키는지 확인 |
| 명시지 루트 충돌 | `explicit_knowledge.root`가 기존 workspace 디렉토리와 충돌하지 않는지 확인 |
| 템플릿 존재 | `projection.mode = "render"` 시 `render_templates`에 정의된 Jinja2 파일 존재 확인 |
| 순환 참조 | source와 target이 서로를 참조하지 않는지 확인 |

---

## 투영(Projection) 실행

### 트리거 시점

| trigger 설정 | 실행 시점 |
|-------------|-----------|
| `on_phase_complete` | 각 Phase(10_topology, 20_mental-model 등) 완료 시 해당 Phase의 투영만 실행 |
| `on_run_complete` | Run 전체 완료 시 모든 투영을 일괄 실행 |
| `manual` | 사용자가 명시적으로 투영을 요청할 때만 실행 |

### 투영 절차

```
1. convention 로딩 + 검증
   ↓
2. 대상 source 경로 resolve
   ├── {run_id} 플레이스홀더를 실제 run_id로 치환
   └── source 경로 존재 확인 (미존재 시 skip + 경고)
   ↓
3. pick 규칙 적용
   ├── glob: 파일 패턴 매칭
   ├── field: JSON 내 특정 필드 추출
   └── field_match: JSON 내 조건부 필터링
   ↓
4. format 적용
   ├── passthrough: 원본 그대로 (symlink/copy)
   └── md: JSON → Markdown 변환 (render_templates 사용)
   ↓
5. 출력 디렉토리 생성 + 파일 배치
   ├── {explicit_root}/{run_id}/{category_path}/
   └── overwrite=false 시 기존 파일 보존
   ↓
6. 투영 로그 기록
   └── .mso-context/active/{run_id}/projection_log.json
```

### 투영 모드별 동작

| mode | 동작 | 장점 | 주의사항 |
|------|------|------|----------|
| `symlink` | 원본에 대한 심볼릭 링크 생성 | 디스크 절약, 실시간 반영 | format: "md" 와 함께 사용 불가 (변환 필요 시 render 사용) |
| `copy` | 파일 복사 | 원본 변경/삭제에 독립 | 디스크 사용량 증가, 동기화 필요 |
| `render` | JSON → Markdown 변환 후 저장 | 사람 가독성 최적화 | Jinja2 템플릿 필수, 원본 변경 시 재투영 필요 |

### format: "md" 변환 규칙

`format: "md"` 인 source에 대해 render 모드가 적용될 때:

1. `render_templates`에서 해당 카테고리의 Jinja2 템플릿을 찾는다.
2. 템플릿이 없으면 기본 변환 규칙을 적용한다:
   - JSON key를 `## Heading`으로
   - 배열은 bullet list로
   - 중첩 객체는 table로
3. 변환된 Markdown 파일의 frontmatter에 `source_path`를 기록한다.

---

## 투영 로그

각 투영 실행 시 `.mso-context/active/{run_id}/projection_log.json`에 기록한다.

```json
{
  "projected_at": "2026-03-28T...",
  "convention_source": "{workspace}/mso-convention.yaml",
  "convention_version": "0.1.0",
  "projections": [
    {
      "source": ".mso-context/active/{run_id}/optimizer/level20_report.md",
      "target": "mso-outputs/{run_id}/reports/level20_report.md",
      "mode": "copy",
      "format": "passthrough",
      "status": "ok"
    }
  ],
  "skipped": [
    {
      "source": ".mso-context/active/{run_id}/60_observability/gate_output_*.json",
      "reason": "no matching files"
    }
  ]
}
```

---

## 정합성 감사

### 주기적 검증

mso-observability 실행 시 투영된 명시지와 원본의 정합성을 확인한다.

| 검증 항목 | 방법 |
|-----------|------|
| symlink 유효성 | 링크 대상 파일 존재 확인 |
| copy 동기화 | 원본과 복사본의 수정 시각 비교 |
| render 동기화 | 원본의 수정 시각과 투영 로그의 `projected_at` 비교 |

정합성 불일치 시 `anomaly_detected` (severity: info) 이벤트를 발생시킨다.

---

## 기존 모듈과의 관계

| 모듈 | 관계 |
|------|------|
| `module.frontmatter-policy` | convention 파일의 메타데이터 규칙과 병행 |
| `module.registry-scan` | 투영 구조가 스킬 디렉토리와 충돌하지 않는지 확인 시 참조 |
| `module.tool-lifecycle` | Tool 승격 시 convention에 따라 명시지 경로도 함께 갱신 |
