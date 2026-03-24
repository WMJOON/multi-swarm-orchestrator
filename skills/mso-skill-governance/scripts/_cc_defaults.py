#!/usr/bin/env python3
"""Embedded CC contract defaults for runtime workspace v0.0.10."""

from __future__ import annotations

import copy
from typing import Any, Dict, List

CC_VERSION = "0.1.0"

_AUDIT_LOG_KEYS = ["run_id", "artifact_uri", "status", "work_type"]


def _make_audit_producer_contract(
    cc_id: str, producer: str, output_path: str, validation_note: str
) -> Dict[str, Any]:
    """Factory for optimizer→audit-log CC contracts (shared key pattern)."""
    return {
        "id": cc_id,
        "producer": producer,
        "consumer": "mso-agent-audit-log",
        "required_output_keys": list(_AUDIT_LOG_KEYS),
        "required_input_keys": list(_AUDIT_LOG_KEYS),
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": validation_note,
        "producer_output_path": output_path,
    }

DEFAULT_CC_CONTRACTS: List[Dict[str, Any]] = [
    {
        "id": "CC-01",
        "producer": "mso-workflow-topology-design",
        "consumer": "mso-execution-design",
        "required_output_keys": ["run_id", "nodes", "edges", "topology_type", "rsv_total"],
        "required_input_keys": ["run_id", "nodes", "topology_type"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "execution_graph 노드 ID가 topology node id에 존재해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/10_topology/workflow_topology_spec.json",
    },
    {
        "id": "CC-02",
        "producer": "mso-mental-model-design",
        "consumer": "mso-execution-design",
        "required_output_keys": ["run_id", "bindings", "unbound_nodes", "metadata"],
        "required_input_keys": ["run_id", "nodes", "vertex_type"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "execution_graph 각 노드의 directive_refs가 binding의 directive_id에 존재해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/20_mental-model/directive_binding.json",
    },
    {
        "id": "CC-03",
        "producer": "mso-task-context-management",
        "consumer": "mso-agent-collaboration",
        "required_output_keys": ["id", "status", "task_context_id", "owner", "due_by", "dependencies", "tags"],
        "required_input_keys": ["id", "task_context_id", "status", "owner"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "collab는 ticket frontmatter 키를 요구사항대로 수신해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/40_collaboration/task-context/tickets",
    },
    {
        "id": "CC-04",
        "producer": "mso-agent-collaboration",
        "consumer": "mso-agent-audit-log",
        "required_output_keys": [
            "dispatch_mode",
            "handoff_payload",
            "requires_manual_confirmation",
            "fallback_reason",
        ],
        "required_input_keys": ["run_id", "dispatch_mode", "status"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "협업 결과는 audit-ready 페이로드로 직렬화 가능해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/40_collaboration/task-context/tickets",
    },
    {
        "id": "CC-05",
        "producer": "mso-agent-audit-log",
        "consumer": "mso-observability",
        "required_output_keys": ["run_id", "artifact_uri", "status", "errors", "warnings", "next_actions", "metadata"],
        "required_input_keys": ["run_id", "artifact_uri", "event_type", "correlation"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "observability는 audit 스키마를 입력으로 읽고 이벤트를 재생성 가능해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/50_audit/agent_log.db",
    },
    {
        "id": "CC-06",
        "producer": "mso-execution-design",
        "consumer": "mso-agent-audit-log",
        "required_output_keys": ["run_id", "execution_graph", "fallback_rules"],
        "required_input_keys": ["run_id", "node_id", "node_type", "parent_refs", "tree_hash_ref"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "execution_graph 노드가 node_snapshots 테이블에 스냅샷으로 기록 가능해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/30_execution/execution_plan.json",
    },
    {
        "id": "CC-07",
        "producer": "mso-observability",
        "consumer": "mso-workflow-optimizer",
        "required_output_keys": ["event_type", "payload", "correlation"],
        "required_input_keys": ["user_feedback.feedback_text", "callback.event_type", "callback.payload.severity"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "observability callback JSON과 user_feedback 테이블이 optimizer Phase 1에 소비 가능해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/60_observability",
    },
    _make_audit_producer_contract(
        "CC-08", "mso-workflow-optimizer",
        "workspace/.mso-context/active/{run_id}/optimizer",
        "optimizer decision_output이 audit_global.db audit_logs 행으로 직렬화 가능해야 함",
    ),
    {
        "id": "CC-09",
        "producer": "mso-workflow-optimizer",
        "consumer": "mso-task-context-management",
        "required_output_keys": ["next_automation_level", "optimization_directives", "carry_over_issues", "approved_by"],
        "required_input_keys": ["id", "status", "priority", "owner", "tags"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "goal.json의 optimization_directives가 TKT 티켓으로 등록 가능해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/optimizer/goal.json",
    },
    {
        "id": "CC-10",
        "producer": "mso-workflow-optimizer",
        "consumer": "mso-agent-collaboration",
        "required_output_keys": ["id", "status", "owner_agent", "dispatch_mode", "tags", "task_id"],
        "required_input_keys": ["run_id", "task_id", "owner_agent", "role", "objective", "workflow_name"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "optimizer Phase 0에서 생성한 teammate 티켓이 mso-agent-collaboration dispatch 요건을 충족해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/40_collaboration/task-context/tickets",
        "activation_condition": "mso-agent-collaboration 모드 활성화 시에만 적용. 단일 세션 모드에서는 warn 처리",
    },
    {
        "id": "CC-11",
        "producer": "mso-workflow-optimizer",
        "consumer": "mso-model-optimizer",
        "required_output_keys": ["trigger_type", "target"],
        "required_input_keys": ["trigger_type", "target.tool_name", "target.inference_pattern"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "Handoff Payload가 handoff_payload.schema.json을 충족하고 target.tool_name에 해당하는 Smart Tool manifest가 존재해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/optimizer/handoff_payload.json",
        "activation_condition": "Tier Escalation 발생 + Phase 5 goal에 model_replacement_needed=true 시에만 적용",
    },
    _make_audit_producer_contract(
        "CC-12", "mso-model-optimizer",
        "workspace/.mso-context/active/{run_id}/model-optimizer",
        "model-optimizer 평가 결과가 audit_global.db audit_logs 행으로 직렬화 가능해야 함 (work_type=model_optimization)",
    ),
    {
        "id": "CC-13",
        "producer": "mso-model-optimizer",
        "consumer": "mso-task-context-management",
        "required_output_keys": ["tool_name", "version", "model_artifact_path", "inference_slot", "runtime", "reproducibility", "evaluation", "rollback", "approved_by"],
        "required_input_keys": ["id", "status", "priority", "owner", "tags"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "deploy_spec.json의 배포 지시가 TKT 티켓으로 등록 가능해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/model-optimizer/deploy_spec.json",
    },
    {
        "id": "CC-14",
        "producer": "mso-observability",
        "consumer": "mso-model-optimizer",
        "required_output_keys": ["tool_name", "rolling_f1", "drift_detected"],
        "required_input_keys": ["tool_name", "inference_pattern", "trigger_type"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "observability 모니터링 이벤트가 model-optimizer Phase 0 트리거 컨텍스트로 소비 가능해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/60_observability",
        "activation_condition": "배포된 모델이 존재하고 rolling_f1 모니터링이 활성화된 경우에만 적용",
    },
]


def get_default_contracts() -> List[Dict[str, Any]]:
    """Return a deep copy of canonical CC defaults."""
    return copy.deepcopy(DEFAULT_CC_CONTRACTS)


def get_contract_index() -> Dict[str, Dict[str, Any]]:
    """Return CC defaults keyed by contract id."""
    return {str(item["id"]): copy.deepcopy(item) for item in DEFAULT_CC_CONTRACTS}


def get_required_skill_ids() -> List[str]:
    """Return unique producer/consumer skill ids from CC defaults."""
    skills = {
        str(item["producer"])
        for item in DEFAULT_CC_CONTRACTS
        if isinstance(item, dict) and "producer" in item and "consumer" in item
    } | {
        str(item["consumer"])
        for item in DEFAULT_CC_CONTRACTS
        if isinstance(item, dict) and "producer" in item and "consumer" in item
    }
    return sorted(skills)

