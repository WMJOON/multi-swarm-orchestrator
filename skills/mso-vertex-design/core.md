# mso-mental-model-design — Core Rules

## Terminology

| 용어 | 정의 |
|------|------|
| Directive | Vertex에 바인딩되는 도메인 지식 단위 (MD 파일). type: framework / instruction / prompt |
| Vertex Registry | Directive를 택소노미로 분류·저장·검색하는 저장소 |
| Directive Binding | topology 노드 ↔ directive 매핑 결과 (Run별 생성) |
| taxonomy_path | Directive의 계층 분류 경로 (예: `[analysis, decomposition]`) |

## Input Interface

- `workflow_topology_spec.json` (nodes[].id, vertex_type, motif)
- Directive Registry (해석 순서):
  1. `~/.mso-registry/<domain>/` (글로벌)
  2. `{workspace}/.mso-context/vertex_registry/<domain>/` (워크스페이스 fallback)
  3. `{mso-mental-model-design}/directives/` (seed fallback)

## Output Interface

- `{workspace}/.mso-context/active/<run_id>/20_mental-model/directive_binding.json`

필수 키:
- `run_id`, `bindings[]` (node_id, vertex_type, directives[]), `unbound_nodes[]`, `metadata`

## Directive Frontmatter 필수 키

- `id` — 고유 식별자 (`dir-NNN` 패턴)
- `type` — `framework` | `instruction` | `prompt`
- `name` — 사람이 읽을 수 있는 이름
- `domain` — 소속 도메인 (디렉토리명과 일치)
- `taxonomy_path` — 계층 분류 배열

## Processing Rules

1. topology의 각 노드에 최소 1개 directive를 바인딩한다
2. 바인딩 실패 노드는 `unbound_nodes[]`에 기록한다
3. directive가 없는 도메인은 `general` fallback 검색을 시도한다
4. 사용자가 신규 directive를 작성하면 frontmatter 유효성 검증 후 등록한다

## Error Handling

- topology가 비었거나 노드가 부재하면 fail-fast
- directive frontmatter에 필수 키 누락 시 등록 거부
- 글로벌 registry(`~/.mso-registry/`)가 없으면 `init_global_registry.py`를 실행하여 초기화한다
