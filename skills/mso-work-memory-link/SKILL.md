---
name: mso-work-memory-link
description: >
  연관 저장소(하위 서브모듈, 루트 밖 별도 경로의 MSO 저장소)의 work-memory 를 한 세션에서 함께 기록·커밋하도록
  설정하고 점검하는 절차 스킬. mso-work-memory 의 --repo/--repo-name, linked-repos.yaml, commit/check 훅
  확장을 한 번에 다룬다. 다음 상황에서 사용한다:
  (1) "하위 레포 work-memory 에도 기록/커밋", "서브모듈 work-memory 가 안 쌓인다", "stop hook 이 안 돈다"
      류의 증상 점검 (status),
  (2) 연관 저장소 등록·제거와 autocommit 켜기/끄기 (add, remove, autocommit),
  (3) 프로젝트의 .claude/.codex 훅 사본이 스킬 최신판과 다른지 확인하고 갱신 (sync-hooks, 기본 dry-run),
  (4) 등록 경로·git 건강 상태·훅 문법·해석기 동작 점검 (verify).
  훅 등록(settings.json) 자체는 mso-repository-setup --hook 이 맡고, 이 스킬은 이미 등록된 훅의 사본 갱신과
  연관 저장소 설정만 다룬다.
metadata:
  version: "0.1.0"
---

# MSO Work Memory Link

루트(엄브렐러) 세션에서 일해도 하위·연관 저장소의 work-memory 에 기록이 남고 커밋되도록 돕는다.
핵심 구현은 mso-work-memory 에 있다(`wm_repos.py`, `wm_node.py --repo/--repo-name`, 훅). 이 스킬은 그 위의
**설정·점검 절차**다.

## 먼저 알 것

- 세션의 프로젝트 루트(`CLAUDE_PROJECT_DIR`) 훅은 루트 work-memory 만 본다. 서브모듈 work-memory 는 별도 git 저장소라 따로 등록해야 커밋된다.
- 자동 발견된 서브모듈은 `autocommit: false`다. 자동 커밋은 등록부에서 켠 저장소에만 한다.
- `.claude/` 훅 사본 변경은 사용자 승인(HITL) 대상이다. `sync-hooks` 는 기본 dry-run 이고 `--apply` 가 있어야 쓴다.
- push 는 하지 않는다. 서브모듈 포인터는 건드리지 않는다.

## 절차

```bash
S=~/.claude/skills/mso-work-memory-link/scripts/wm_link.py
python3 $S status   [--root R]                    # 1. 현황: 등록·발견 저장소, autocommit, 훅 사본 일치, git 건강, 미커밋 work-memory
python3 $S add <name> <path> [--autocommit]       # 2. 등록 (루트 밖 경로도 가능, ~ 허용)
python3 $S autocommit <name> on|off               #    자동 커밋 켜기/끄기 (발견만 된 서브모듈은 항목을 새로 만든다)
python3 $S remove <name>                          #    등록 제거 (발견된 서브모듈은 .gitmodules 에서 오므로 off 로 둔다)
python3 $S sync-hooks [--scripts-dir D] [--apply] # 3. 훅 사본 vs 스킬 최신판 비교, --apply 시 교체(백업 .bak 을 만들지 않고 diff 만 출력)
python3 $S verify   [--root R]                    # 4. 점검: 경로, git HEAD, bash -n, 해석기
```

기록은 `wm_node.py new <type> --title ... --repo-name <name>` 으로 한다(`--repo <경로>` 도 가능).

## 판단 가이드

| 상황 | 조치 |
|---|---|
| 서브모듈 work-memory 가 `M` 으로 남음 | status → 그 저장소 `autocommit on` (work-memory 경로만 커밋됨) |
| 포함 git 의 HEAD 가 손상(`bad object HEAD`) | verify 가 표시한다. autocommit 을 끄고 저장소를 먼저 복구한다 |
| 훅 사본이 구판 | sync-hooks 로 diff 확인 후 사용자 승인 받아 `--apply` |
| 루트에서 열지 않고 하위에서 열 수 있다 | 하위에서 세션을 열면 그 저장소 자체 설정의 훅이 쓰인다. 이 스킬은 루트 세션용 보완이다 |
