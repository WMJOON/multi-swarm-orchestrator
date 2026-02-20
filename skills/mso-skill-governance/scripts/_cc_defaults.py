#!/usr/bin/env python3
"""Embedded CC contract defaults for runtime workspace v0.0.3."""

from __future__ import annotations

import copy
from typing import Any, Dict, List

CC_VERSION = "0.0.3"

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
        "required_output_keys": ["run_id", "node_chart_map", "local_charts", "output_contract", "bundle_ref"],
        "required_input_keys": ["run_id", "nodes", "assigned_dqs", "theta_gt_band"],
        "compatibility_policy": "strict",
        "status": "ok",
        "validation_rule": "execution_graph 각 노드의 chart_ids가 bundle chart id에 존재해야 함",
        "producer_output_path": "workspace/.mso-context/active/{run_id}/20_mental-model/mental_model_bundle.json",
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

