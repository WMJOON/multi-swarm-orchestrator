# module.mode-policy

## 규칙
- high θ_GT(node) -> `dontAsk`
- medium θ_GT -> `default`
- low θ_GT -> `plan`
- loop topology -> fallback 노드에 `bypassPermissions`
