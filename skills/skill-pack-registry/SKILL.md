---
name: skill-pack-registry
description: |
  스킬 팩(mso, msm 등)의 prefix, required_skills, overload_threshold 정의를 조회할 때 사용.
  거버넌스 검증, 스킬 팩 범위 확인, pack별 스킬 목록 조회 시 references/pack_registry.json을 참조한다.
  validate_gov.py 실행 시 --pack 인자로 팩을 지정하면 이 레지스트리를 자동으로 읽는다.
---

# skill-pack-registry

팩 정의 단일 소스: [references/pack_registry.json](references/pack_registry.json)

## 거버넌스 검증 실행

```bash
python3 {mso-skill-governance}/scripts/validate_gov.py \
  --pack-root ~/.claude \
  --pack mso \
  --json
```

`--pack` 생략 시 REQUIRED_SKILLS 하드코딩 값으로 폴백한다.
