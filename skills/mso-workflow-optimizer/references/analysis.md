# 분석 기준

모든 분석기는 `scripts/wm_analyze.py` 의 순수 함수다. 입력은 entry 목록(`load_entries`)과 `now`, 출력은 제안 목록이다.
제안 = `{id, kind, priority, title, why, suggestion, evidence[entry id], data}`. 정렬은 종류 → 우선순위 → 근거 수 → id 로 결정적이다.

## 입력

`track-record/`, `insight-record/`, `release-record/` 의 `*.jsonl`. 깨진 줄은 건너뛰고 통계에 남긴다. `auditlog/`·`worklog/` 는 읽지 않는다(도구 호출 로그라 의미 분석 대상이 아니다).

## 군집 (promotion, workflow)

제목·본문·root_cause 등을 한글 음절 bigram + 영문 토큰으로 쪼개 TF-IDF cosine 유사도를 구하고 single-link 로 묶는다. 외부 의존이 없다.
기본 임계값 0.18 은 실제 work-memory(약 430 entry)에서 같은 원인으로 해결된 TS 가 묶이도록 낮춘 값이다. 군집이 너무 크거나 작으면 `analyze_*` 의 `threshold` 를 조정한다.

## promotion

| 제안 | 조건 |
|---|---|
| EP 후보 | EP/PT/PR 에 참조되지 않은 TS·IN 이 군집 3건 이상. 5건 이상이면 high |
| PT 후보 | 어떤 PT 의 instances 에도 없는 EP 가 군집 2건 이상 |
| PR 후보 | `crystallized-in` 이 없는 PT 중 `metadata.instances` 가 3건 이상 |

"참조됨" = EP/PT/PR 의 `relations`, `metadata.spans/instances/sources/crystallized_from/evidence`, 본문에 적힌 id.

## workflow

| 제안 | 조건 |
|---|---|
| 재발 root cause | `root_cause` 가 비슷한 TS 가 2건 이상(4건 이상이면 high). pattern 의 countermeasures 에 이미 언급된 수를 함께 적는다 |
| 모듈 핫스팟 | 모듈(표기 정규화: `_`↔`-`)에 열린 issue 5건 이상, 또는 3건 이상이고 고위험(열린 것만) 3건 이상 |
| 재발 issue | resolved issue 와 유사도 0.6 이상인 open/fixing issue |

모듈이 없는 issue 는 핫스팟에서 빼고 quality 로 보낸다.

## stale

| 제안 | 조건 |
|---|---|
| 사라진 경로 | UD/AD/PT/PR 본문의 경로 중 프로젝트 루트의 **존재하는 최상위 디렉터리** 안에서 파일이 없는 것(외부 경로·모델 ID 오탐을 줄이려는 보수적 기준) |
| 릴리스 뒤 미확인 | 최신 RN 보다 오래된 구조·정책 UD 중 그 RN 으로의 `verified-in`/`invalidated-by` 가 없는 것 |
| supersede 누락 | 같은 모듈의 UD 쌍이 유사도 0.55 이상인데 어떤 관계로도 연결되지 않음 |
| 낮은 확신 AD | 30일 이상, confidence 낮음, `followed-by` 없음 |

## quality

중복 id, 끊긴 relation target, status/severity 누락, 권장 어휘 밖 값(`minor/major` 등), `resolved` 인데 해결 TS 연결 없음, TS 가 연결됐는데 issue 가 open, 60일 넘게 열린 무진행 issue, TS 의 root_cause/fix_summary 누락, issue 와 연결 없는 TS, AD 의 rationale/alternatives/confidence 누락, 표기만 다른 태그, module 누락(5건 이상).

## 모델 요약 (선택)

`draft_pack.json` = `{instruction, expects, stats, proposals[]}`. control plane 은 근거 entry 를 열어 확인하고 `{summary, proposals:{id:{rewrite}}}` 를 `resume` 으로 돌려준다.
`rewrite` 는 해당 제안의 설명을 대체해 `report.md` 에 들어간다. 근거에 없는 사실을 만들지 않는다.
