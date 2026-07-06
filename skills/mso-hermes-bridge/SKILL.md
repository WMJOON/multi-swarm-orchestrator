---
name: mso-hermes-bridge
version: "0.8.0"
description: "MSO workflow에서 Hermes Agent를 외부 Executor로 위임한다. Hermes API Server(OpenAI-compatible, port 8642)를 통해 태스크를 전달하고 Runs API 폴링으로 결과를 수집한다. ExecutionSubject=Agent(Hermes), ExecutionMethod=api."
roadmap_section: "§7 Execution Metadata ― ExecutionMethod=api 구현 사례"
requires:
  - hermes-agent >= 0.1.0 (API Server 모드)
  - HERMES_API_KEY 환경변수
---

# MSO Hermes Bridge (v0.8.0)

MSO workflow에서 **Hermes Agent를 외부 Executor로 위임**하는 브리지 스킬이다. workflow TTL의 Executor 노드가 `delegates_to: hermes-agent`로 선언된 경우 이 스킬을 통해 HTTP로 태스크를 위임하고 결과를 artifact로 수집한다.

Trigger phrases: hermes 위임, hermes-bridge, 외부 에이전트 위임, hermes agent 실행, hermes gateway 호출, delegates_to hermes.

## 전제 조건

Hermes API Server가 실행 중이어야 한다.

```bash
# ~/.hermes/.env
API_SERVER_ENABLED=true
API_SERVER_KEY=your-local-key   # HERMES_API_KEY 환경변수와 동일
```

```bash
hermes gateway   # 백그라운드로 실행
# → [API Server] API server listening on http://127.0.0.1:8642
```

## 원칙

- **Hermes는 ExecutionSubject=Agent, ExecutionMethod=api**다. workflow TTL ABox에서 Executor 노드로 선언하고, `wf:executionMethod "api"`, `wf:hasSubject <hermes:HermesAgent>`로 표기한다.
- **위임 결과는 반드시 Artifact로 수집**된다. Hermes 응답은 `output` 필드를 artifact 파일로 직렬화한다.
- **상태는 Runs API로 관리**한다. `/v1/chat/completions`(동기)보다 `/v1/runs`(비동기 폴링) 패턴을 기본으로 쓴다 ― MSO 태스크는 장기 실행이 일반적이기 때문이다.
- **conversation 파라미터로 세션 연속성**을 유지한다. multi-turn이 필요한 경우 `conversation: "mso-<project>-<scope>"` 형식을 쓴다.
- **Health check 없이 위임하지 않는다.** `GET /v1/health` 응답이 없으면 즉시 실패를 반환한다 ― Hermes가 꺼진 채로 workflow를 계속 진행하는 것보다 낫다.
- **timeout은 300초 기본**이다. 장기 실행 태스크는 호출 시 `--timeout` 을 명시한다.

## TTL 선언 패턴

workflow ABox에서 Hermes 위임 노드를 이렇게 선언한다:

```turtle
# Hermes Executor 노드 선언
:hermes-executor a wf:Executor ;
    rdfs:label "Hermes Agent" ;
    wf:executionMethod "api" ;
    wf:hasSubject :hermes-agent-subject ;
    wf:apiEndpoint "http://127.0.0.1:8642" .

:hermes-agent-subject a wf:ExecutionSubject ;
    rdfs:label "Hermes Agent (NousResearch)" ;
    wf:subjectType "Agent" .

# 위임 Rail
:task-A wf:delegates_to :hermes-executor .
```

## CLI

프로젝트 루트에서 실행한다.

```bash
# 단순 태스크 위임 (Runs API, 폴링 완료까지 대기)
bash skills/mso-hermes-bridge/scripts/bridge.sh "태스크 설명"

# conversation 세션 지정
bash skills/mso-hermes-bridge/scripts/bridge.sh "태스크 설명" --conversation mso-myproject-analysis

# timeout 지정 (초, 기본 300)
bash skills/mso-hermes-bridge/scripts/bridge.sh "태스크 설명" --timeout 600

# 동기 호출 (단순 Q&A용, 스트리밍 없음)
python3 skills/mso-hermes-bridge/scripts/hermes_bridge.py sync "태스크 설명"

# Runs API (비동기)
python3 skills/mso-hermes-bridge/scripts/hermes_bridge.py run "태스크 설명" --conversation mso-proj
```

## Workflow

1. `GET /v1/health` 응답 확인 ― 실패 시 즉시 종료.
2. `POST /v1/runs` ― `{input, conversation}` 페이로드로 run 생성.
3. run_id 수신 후 5초 간격으로 `GET /v1/runs/{run_id}` 폴링.
4. status=`completed` 또는 `failed` 도달 시 폴링 종료.
5. `.output` 필드를 stdout으로 반환 (artifact 직렬화는 호출자 책임).

## 에러 처리

| 상황 | 동작 |
|---|---|
| Hermes 미실행 | health check 실패 → `exit 1` + 메시지 |
| timeout 초과 | 폴링 종료 → `exit 2` + run_id 출력 (나중에 수동 확인 가능) |
| status=failed | `exit 3` + Hermes 오류 메시지 출력 |
| 인증 실패(401) | `exit 4` + HERMES_API_KEY 확인 요청 |

## Artifact 연동

Hermes 응답 output을 MSO artifact로 저장하는 방법:

```bash
OUTPUT=$(bash skills/mso-hermes-bridge/scripts/bridge.sh "분석 요청")
echo "$OUTPUT" > agent-context/artifacts/hermes-analysis.md
```

workflow TTL에는 이 artifact를 `produces_to` stream으로 선언한다:

```turtle
:hermes-executor wf:produces_to :artifact-hermes-analysis .
:artifact-hermes-analysis a wf:Artifact ;
    wf:artifactType "document" ;
    wf:location "agent-context/artifacts/hermes-analysis.md" .
```

## 보안

- `HERMES_API_KEY`는 환경변수로만 주입한다. 스크립트에 하드코딩하지 않는다.
- API Server는 기본 `127.0.0.1`(localhost)만 bind한다. 외부 노출이 필요한 경우 `API_SERVER_HOST` 설정을 검토한다.
- conversation_id에 프로젝트 경로나 개인정보를 포함하지 않는다.

## 참고

- Hermes API Server 공식 스펙: `POST /v1/runs`, `GET /v1/runs/{id}`, `POST /v1/chat/completions`
- MSO Execution Metadata 스펙: [[mso-v0.9.0-SPEC-provenance-execution-metadata]] §7
- Hermes 소스 분석: `my-knowledge-base/research/hermes-agent-source-analysis.md`
