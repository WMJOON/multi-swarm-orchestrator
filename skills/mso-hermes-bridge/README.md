# MSO Hermes Bridge

MSO workflow에서 **Hermes Agent를 외부 Executor로 위임**하는 스킬이다.

workflow TTL에서 `wf:delegates_to :hermes-executor`로 선언된 step을 Hermes API Server(OpenAI-compatible, port 8642)로 위임하고 Runs API 폴링으로 결과를 수집한다.

- **버전**: v0.8.0
- **MSO ROADMAP**: §7 Execution Metadata — ExecutionMethod=api 구현 사례
- **ExecutionSubject**: Agent (Hermes), **ExecutionMethod**: api

---

## 전제 조건

```bash
# ~/.hermes/.env
echo 'API_SERVER_ENABLED=true' >> ~/.hermes/.env
echo 'API_SERVER_KEY=your-local-key' >> ~/.hermes/.env

# 환경변수
export HERMES_API_KEY=your-local-key
```

---

## 설치 (MSO Repository 초기화)

```bash
# MSO init + Hermes 세팅 한 번에
bash skills/mso-hermes-bridge/scripts/setup-with-hermes.sh . \
     --provider claude \
     --worthy-paths "agent-context .claude README.md"

# 이미 MSO가 초기화된 프로젝트에 Hermes만 추가
bash skills/mso-hermes-bridge/hooks/hermes-repo-setup.sh --root .
```

실행 결과:
- `.hermes/` 디렉토리 생성
- `.hermes/mso-context.md` 배포 (Hermes가 MSO 구조 인식)
- `.hermes/bridge.sh` 심볼릭 링크
- `~/.hermes/.env` 설정 상태 확인/안내

---

## 사용법

```bash
# Hermes 시작
hermes gateway
# → [API Server] API server listening on http://127.0.0.1:8642

# 태스크 위임 (Runs API, 폴링)
bash skills/mso-hermes-bridge/scripts/bridge.sh "분석 요청"
bash skills/mso-hermes-bridge/scripts/bridge.sh "분석 요청" --conversation mso-myproject
bash skills/mso-hermes-bridge/scripts/bridge.sh "분석 요청" --timeout 600

# Python 버전
python3 skills/mso-hermes-bridge/scripts/hermes_bridge.py run "분석 요청" --conversation mso-proj
python3 skills/mso-hermes-bridge/scripts/hermes_bridge.py sync "질문"
```

### workflow TTL 컨텍스트 기반 위임

```bash
CONTEXT=$(python3 skills/mso-hermes-bridge/scripts/workflow_context.py \
    --workflow-dir agent-context/workflow \
    --step-id psd-s-034)
bash skills/mso-hermes-bridge/scripts/bridge.sh "$CONTEXT" --conversation mso-proj
```

---

## workflow TTL 선언

```turtle
@prefix wf: <http://mso.org/workflow#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:hermes-executor a wf:Executor ;
    rdfs:label "Hermes Agent" ;
    wf:executionMethod "api" ;
    wf:hasSubject :hermes-agent-subject ;
    wf:apiEndpoint "http://127.0.0.1:8642" .

:hermes-agent-subject a wf:ExecutionSubject ;
    rdfs:label "Hermes Agent (NousResearch)" ;
    wf:subjectType "Agent" .

:my-task a wf:Task ;
    rdfs:label "Hermes 위임 태스크" ;
    wf:delegates_to :hermes-executor .
```

---

## Artifact 연동

```bash
OUTPUT=$(bash skills/mso-hermes-bridge/scripts/bridge.sh "분석 요청")
echo "$OUTPUT" > agent-context/artifacts/hermes-analysis.md
```

```turtle
:hermes-executor wf:produces_to :artifact-hermes-analysis .
:artifact-hermes-analysis a wf:Artifact ;
    wf:artifactType "document" ;
    wf:location "agent-context/artifacts/hermes-analysis.md" .
```

---

## 에러 코드

| 코드 | 의미 | 해결 |
|---|---|---|
| 0 | 성공 | — |
| 1 | Hermes 미실행 | `hermes gateway` 실행 |
| 2 | timeout 초과 | `--timeout` 늘리기 |
| 3 | run 실패/취소 | Hermes 로그 확인 |
| 4 | 인증 실패 | `HERMES_API_KEY` 확인 |

---

## 파일 구조

```
mso-hermes-bridge/
  README.md
  SKILL.md                           ← MSO 스킬 진입점
  hooks/
    hermes-repo-setup.sh             ← repository init 시 Hermes 세팅
  references/
    hermes-project-context.md.tmpl   ← .hermes/mso-context.md 템플릿
  scripts/
    bridge.sh                        ← Runs API 위임 (bash)
    hermes_bridge.py                 ← Python 버전
    workflow_context.py              ← TTL step 컨텍스트 추출
    setup-with-hermes.sh             ← MSO init + Hermes 통합 래퍼
```

---

## 관련 문서

- [MSO ROADMAP v0.x](../../planning/mso-ROADMAP-v0.x-repository-graph.md)
- [v0.8.0 SPEC: Property Chain](../../planning/mso-v0.8.0-SPEC-property-chain.md)
- [Hermes 소스 분석](../../../../my-knowledge-base/research/hermes-agent-source-analysis.md)
