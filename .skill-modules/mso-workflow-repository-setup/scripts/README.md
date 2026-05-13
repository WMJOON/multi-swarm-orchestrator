# Scripts

`mso-workflow-repository-setup` is currently a v0.2.2 planning/spec skill.

## Phase 4: audit-log 환경 초기화

레포지토리 환경 세팅 시 `mso-agent-audit-log`의 setup 명령을 실행한다:

```bash
python3 ~/.skill-modules/mso-skills/mso-agent-audit-log/scripts/setup.py \
  --project-root <workspace_root> \
  [--worklog-dir <path>] \
  [--dry-run]
```

워크로그 디렉터리 생성, audit DB 초기화, 세션 훅 주입을 한 번에 수행한다.
DB와 훅 주입은 멱등 동작한다.

## Future scripts

- workflow repository validator
- scaffold generator
- harness setup input generator
- memory boundary checker
