import importlib.util
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import compile_workflow  # noqa: E402


TTL = """\
@prefix wf: <https://mso.dev/ontology/workflow#> .

<https://mso.dev/ontology/workflow#project/demo> a wf:Project ;
    wf:label "Demo Workflow" .

<https://mso.dev/ontology/workflow#phase/discovery> a wf:Phase ;
    wf:label "Discovery" ;
    wf:status "active" ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/discovery-s-001>,
        <https://mso.dev/ontology/workflow#node/discovery-d-001>,
        <https://mso.dev/ontology/workflow#node/discovery-v-001> .

<https://mso.dev/ontology/workflow#node/discovery-s-001> a wf:Node, wf:Step ;
    wf:label "Collect inputs" ;
    wf:instruction "Collect input files" ;
    wf:status "active" .

<https://mso.dev/ontology/workflow#node/discovery-d-001> a wf:Node, wf:Decision ;
    wf:label "Review inputs" ;
    wf:judge "HITLFE" ;
    wf:owner "owner@example.com" ;
    wf:threshold "missing inputs" ;
    wf:hasBranch <https://mso.dev/ontology/workflow#node/discovery-d-001_branch_approve>,
        <https://mso.dev/ontology/workflow#node/discovery-d-001_branch_rework> .

<https://mso.dev/ontology/workflow#node/discovery-d-001_branch_approve> a wf:Branch ;
    wf:on "approve" ;
    wf:goto "discovery-v-001" ;
    wf:label "Proceed" .

<https://mso.dev/ontology/workflow#node/discovery-d-001_branch_rework> a wf:Branch ;
    wf:on "rework" ;
    wf:goto "discovery-s-001" ;
    wf:label "Rework" .

<https://mso.dev/ontology/workflow#node/discovery-v-001> a wf:Node, wf:Validation ;
    wf:label "Validate inputs" ;
    wf:harness "pytest" ;
    wf:passCriteria "tests pass" .
"""


def _load_generated_graph(graph_py: Path):
    spec = importlib.util.spec_from_file_location("generated_graph", graph_py)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_workmem(tmp_path: Path) -> Path:
    workmem = tmp_path / "agent-context" / "work-memory"
    principles = workmem / "insight-record" / "principles"
    decisions = workmem / "track-record" / "user-decision"
    issues = workmem / "track-record" / "issue-note"
    principles.mkdir(parents=True)
    decisions.mkdir(parents=True)
    issues.mkdir(parents=True)

    (principles / "PR-0001.jsonl").write_text(json.dumps({
        "id": "PR-0001",
        "type": "principle",
        "title": "Input collection must be explicit",
        "text": "Collect inputs before validation and preserve provenance.",
        "tags": ["discovery", "discovery-s-001", "step"],
        "created_at": "2026-06-01T00:00:00Z",
        "relations": [{"type": "references", "target": "UD-0001"}],
        "metadata": {"scope": "project"},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    (decisions / "UD-0001.jsonl").write_text(json.dumps({
        "id": "UD-0001",
        "type": "user-decision",
        "title": "Review gate requires human-visible context",
        "text": "HITLFE review nodes must show prior decisions and relevant issues.",
        "tags": ["discovery", "HITLFE", "decision"],
        "created_at": "2026-06-02T00:00:00Z",
        "relations": [],
        "metadata": {"boundary": "review.context", "criterion": "show context pack"},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    (issues / "IN-0001.jsonl").write_text(json.dumps({
        "id": "IN-0001",
        "type": "issue-note",
        "title": "Validation missed missing files",
        "text": "A previous validation passed without checking all input files.",
        "tags": ["discovery-v-001", "validation", "pytest"],
        "created_at": "2026-06-03T00:00:00Z",
        "relations": [],
        "metadata": {"severity": "major"},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    return workmem


def test_compile_ttl_to_langgraph_artifacts(tmp_path):
    ttl = tmp_path / "workflow.abox.ttl"
    ttl.write_text(TTL, encoding="utf-8")

    artifact_dir = compile_workflow.compile_workflow(ttl, tmp_path / "generated", None, "cost")

    assert (artifact_dir / "graph.py").exists()
    assert (artifact_dir / "workflow_ir.json").exists()
    assert (artifact_dir / "optimizer_policy.json").exists()
    assert (artifact_dir / "manifest.json").exists()

    ir = json.loads((artifact_dir / "workflow_ir.json").read_text(encoding="utf-8"))
    assert ir["workflow_id"] == "Demo_Workflow"
    assert ir["mode"] == "cost"
    assert ir["entrypoints"] == ["discovery"]
    assert any(edge["kind"] == "branch" and edge["on"] == "approve" for edge in ir["edges"])

    nodes = {node["id"]: node for node in ir["nodes"]}
    assert nodes["discovery-s-001"]["provider"] == "local-ollama"
    assert nodes["discovery-v-001"]["provider"] == "python"
    assert nodes["discovery-d-001"]["provider"] == "codex-chatgpt"

    generated = _load_generated_graph(artifact_dir / "graph.py")
    generated.LANGGRAPH_AVAILABLE = False
    state = generated.invoke({"decisions": {"discovery-d-001": "approve"}})
    assert state["langgraph_available"] is False
    assert [item["node_id"] for item in state["trace"]]


def test_policy_overrides_provider_routing(tmp_path):
    ttl = tmp_path / "workflow.abox.ttl"
    ttl.write_text(TTL, encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({
        "mode": "speed",
        "providers": {
            "default": "openai-api",
            "step": "openai-api",
            "validation": "python",
            "decision": {"HITLFE": "openai-api"},
        },
    }), encoding="utf-8")

    artifact_dir = compile_workflow.compile_workflow(ttl, tmp_path / "generated", policy, None)
    ir = json.loads((artifact_dir / "workflow_ir.json").read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in ir["nodes"]}

    assert ir["mode"] == "speed"
    assert nodes["discovery-s-001"]["provider"] == "openai-api"
    assert nodes["discovery-d-001"]["provider"] == "openai-api"


def test_work_memory_context_pack_and_writeback_queue(tmp_path):
    ttl = tmp_path / "workflow.abox.ttl"
    ttl.write_text(TTL, encoding="utf-8")
    workmem = _write_workmem(tmp_path)

    artifact_dir = compile_workflow.compile_workflow(
        ttl,
        tmp_path / "generated",
        None,
        "cost",
        workmem_dir=workmem,
    )
    ir = json.loads((artifact_dir / "workflow_ir.json").read_text(encoding="utf-8"))

    assert ir["workmem_entry_count"] == 3
    assert ir["workmem_sha256"]
    assert "discovery-s-001" in ir["context_packs"]
    step_context_ids = {entry["id"] for entry in ir["context_packs"]["discovery-s-001"]["entries"]}
    assert "PR-0001" in step_context_ids
    decision_context_ids = {entry["id"] for entry in ir["context_packs"]["discovery-d-001"]["entries"]}
    assert "UD-0001" in decision_context_ids

    generated = _load_generated_graph(artifact_dir / "graph.py")
    generated.LANGGRAPH_AVAILABLE = False
    state = generated.invoke({
        "node_results": {
            "discovery-s-001": {
                "memory_writeback": {
                    "type": "agent-decision",
                    "title": "Use explicit input collection",
                    "text": "Collected input paths before validation.",
                    "tags": ["discovery-s-001"],
                }
            }
        }
    })
    assert state["active_context"]["discovery-s-001"]["entries"]
    assert state["memory_writeback_queue"][0]["status"] == "proposed"
    assert state["memory_writeback_queue"][0]["requires_review"] is True


def test_execution_plane_escalates_decisions_to_control_plane(tmp_path):
    ttl = tmp_path / "workflow.abox.ttl"
    ttl.write_text(TTL, encoding="utf-8")

    artifact_dir = compile_workflow.compile_workflow(ttl, tmp_path / "generated", None, "cost")
    generated = _load_generated_graph(artifact_dir / "graph.py")
    generated.LANGGRAPH_AVAILABLE = False

    state = generated.invoke({
        "node_results": {
            "discovery-d-001": {
                "control_plane_event": {
                    "action": "propose_alternatives",
                    "summary": "Inputs are incomplete; ask the user to choose rework or proceed.",
                    "alternatives": [
                        {"n": 1, "name": "rework", "trade_off": "slower but complete"},
                        {"n": 2, "name": "proceed", "trade_off": "faster but risky"},
                    ],
                },
                "memory_writeback": {
                    "type": "user-decision",
                    "title": "User selected proceed",
                    "text": "This must not be written by execution plane.",
                    "tags": ["discovery-d-001"],
                },
            }
        }
    })

    assert state["halted"] is True
    assert state["halt_reason"] == "propose_alternatives"
    assert state["control_plane_events"][0]["status"] == "pending-control-plane"
    assert state["control_plane_events"][0]["control_plane_agents"] == ["claude-code", "codex"]
    assert state["memory_writeback_queue"][0]["status"] == "rejected"
    assert "cannot record user-decision" in state["memory_writeback_queue"][0]["reason"]
