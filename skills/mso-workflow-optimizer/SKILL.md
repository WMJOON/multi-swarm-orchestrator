---
name: mso-workflow-optimizer
metadata:
  version: "1.0.0"
description: >
  work-memory 를 읽기 전용으로 분석해 개선 제안 리포트를 만드는 optimizer 스킬(LangGraph).
  TTL 을 컴파일하지 않는다. agent-context/work-memory 의 IN/AD/UD/TS/EP/PT/PR 를 결정적 코드로 분석해
  (1) 회고 승격 후보(IN/TS → EP, EP → PT, PT → PR), (2) workflow 개선안(재발 root cause·모듈 핫스팟),
  (3) 낡은 결정·교훈 점검, (4) 기록 누락·품질을 근거 entry id 와 함께 제안한다.
  모델은 선택적 요약 단계에만 쓰고(control plane 위임), work-memory 에는 절대 쓰지 않는다.
  다음 상황에서 사용한다: (1) "work-memory 분석", "회고 후보", "패턴으로 올릴 만한 게 있나",
  (2) "같은 문제가 반복되나", "workflow 개선점", (3) "낡은 결정 점검", "기록 품질 점검",
  (4) 릴리스·정기 회고 전에 승격·정리 대상을 뽑을 때.
---

# MSO Workflow Optimizer — work-memory 분석

작업 기록(work-memory)에서 **무엇을 바꾸면 좋을지**를 제안한다. 제안만 하고 고치지 않는다. 확정과 기록은 사람과 control plane(Claude Code/Codex)이 한다.

## 왜 컴파일이 아닌가

v0.9 까지는 workflow TTL 을 LangGraph 로 컴파일했다. TTL 에서 나오는 것은 제어 구조뿐이고 노드가 실제로 하는 일은 TTL 에 없어서, 컴파일 결과는 실행되지 않는 골격이었다. 실제 가치는 구조를 코드로 찍어내는 데 있지 않고 **기록에서 반복·누락·낡음을 찾아 다음 행동을 제안**하는 데 있다고 보고 방향을 바꿨다(v1.0.0).

## 구조

```
load ─┬─ promotion ─┐
      ├─ workflow  ─┤
      ├─ stale     ─┼─ collect ─┬─ draft(모델 요약, 선택) ─┐
      └─ quality   ─┘           └──────────────────────────┴─ publish → report.md / report.json
```

- **분석은 결정적이다.** LLM 없이도 같은 입력이면 같은 제안이 나온다. 각 제안은 근거 entry id 를 가진다. 분석기는 `scripts/wm_analyze.py`.
- **모델은 선택이다.** `draft` 노드는 체크포인터가 있고 `--draft` 일 때만 LangGraph `interrupt` 로 멈춘다. control plane 이 `draft_pack.json` 을 읽어 요약·문안을 쓰고 `resume` 으로 돌려준다.
- **work-memory 에는 쓰지 않는다.** 결과는 리포트 파일(`generated/work-memory-analysis/<date>/`)로만 남는다. 제안을 채택해 entry 를 만드는 일은 `mso-work-memory` 의 절차(`wm_node.py`)로 사람이 승인한 뒤 한다.

## 분석 4종

| 종류 | 제안하는 것 | 근거 |
|---|---|---|
| promotion | 회고되지 않은 유사 IN/TS 군집 → EP, 비슷한 EP 군 → PT, 인스턴스 3건 이상인 PT → PR | 어휘 유사도 군집(TF-IDF), 기존 EP/PT/PR 의 참조 |
| workflow | 같은 root cause 로 해결된 TS 군 → 게이트·테스트·hook 후보, 열린 issue 가 몰린 모듈, 해결 뒤 다시 열린 유사 issue | root_cause 군집, 모듈별 status/severity |
| stale | 사라진 경로를 인용하는 결정, 최신 릴리스 뒤 재확인(verified-in) 없는 구조·정책 UD, supersede 누락 후보, 확신 낮은 미채택 AD | 프로젝트 파일 존재, release-note 관계 |
| quality | 끊긴·중복 id, 필수 필드 누락, resolved↔TS 불일치, 방치된 open issue, 태그·어휘 드리프트 | schema 와 관계 무결성 |

자세한 기준과 임계값은 [references/analysis.md](references/analysis.md).

## 사용

```bash
# 결정적 분석만 (모델 없음). langgraph 가 없어도 동작한다.
python scripts/analyze_work_memory.py agent-context/work-memory [--out DIR] [--max-per-kind 10]

# 모델 요약을 얹을 때 (체크포인터 필요: pip install -r requirements-langgraph.txt)
python scripts/analyze_work_memory.py agent-context/work-memory --draft --checkpoint run.sqlite --thread t1
#   → draft_pack.json 을 읽고 {"summary": "...", "proposals": {"<id>": {"rewrite": "..."}}} 를 쓴다
python scripts/analyze_work_memory.py --resume t1 --checkpoint run.sqlite --draft-file narrative.json
```

- 출력: `report.md`(읽기용), `report.json`(전체 제안·근거·통계).
- 프로젝트 파일 존재 검사는 `agent-context/work-memory` 의 두 단계 위를 프로젝트 루트로 본다(`--project-root` 로 덮어쓴다).

## 작업 절차 (에이전트)

1. 분석을 돌려 `report.md` 를 읽는다. high 우선순위와 근거 entry 를 먼저 본다.
2. 근거 entry 를 직접 열어 제안이 타당한지 판단한다. 휴리스틱이라 오탐이 있다(특히 군집이 큰 승격 후보).
3. 타당한 것만 사용자에게 제안한다. entry 생성·수정은 사용자 승인 뒤 `mso-work-memory` 절차로 한다.
4. 기각한 제안은 반복해서 나오므로 이유를 사용자에게 알리고, 필요하면 임계값을 조정한다.

## 경계

- 이 스킬은 분석·제안만 한다. 기록은 `mso-work-memory`, workflow 구조는 `mso-workflow-design`, 시각화는 `mso-graph-observability` 가 맡는다.
- 사람이 받아들일 판단(UD)을 대신 내리지 않는다. 제안은 에이전트의 의견이다.
