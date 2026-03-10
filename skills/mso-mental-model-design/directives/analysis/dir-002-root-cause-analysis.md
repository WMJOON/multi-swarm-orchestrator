---
id: dir-002
type: framework
name: Root Cause Analysis
domain: analysis
taxonomy_path: [analysis, causal_reasoning]
concepts: [5_whys, fishbone, fault_tree]
applicable_vertex_types: [agent]
applicable_motifs: [chain, loop]
related: [dir-001]
---

# Root Cause Analysis

표면 증상이 아닌 **근본 원인**을 추적하는 분석 프레임워크.

## 적용 절차

1. 문제 현상을 명확히 기술한다
2. "왜?" 질문을 반복한다 (5 Whys)
3. 원인-결과 체인이 더 이상 분해 불가능한 지점에서 멈춘다
4. 근본 원인에 대한 대응책을 도출한다

## 도구 선택

| 복잡도 | 도구 |
|--------|------|
| 단순 (원인 1~2개) | 5 Whys |
| 중간 (다요인) | Fishbone (Ishikawa) |
| 복합 (시스템적) | Fault Tree Analysis |

## 주의

- "왜?"의 답이 주관적 판단이면 증거를 요구한다
- 원인이 순환하면 시스템 구조 문제 → 스코프 재설정
