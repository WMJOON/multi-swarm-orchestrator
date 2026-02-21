#!/usr/bin/env python3
"""Integration tests for MSO skill interactions.

Tests that each skill can run independently and that the full pipeline
(topology -> bundle -> plan -> ticket -> dispatch -> audit -> observability -> governance)
works end-to-end.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Ensure the project root is on sys.path for imports
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd or str(ROOT), capture_output=True, text=True, timeout=60)


def _script(rel: str) -> str:
    return str((ROOT / rel).resolve())


class TestContext:
    """Disposable workspace for a single test run."""

    def __init__(self, name: str):
        self.tmpdir = Path(tempfile.mkdtemp(prefix=f"mso-test-{name}-"))
        self.ws = self.tmpdir / "workspace"
        self.obs = self.tmpdir / "mso-observation-workspace"
        os.environ["MSO_WORKSPACE_ROOT"] = str(self.ws)
        os.environ["MSO_OBSERVATION_ROOT"] = str(self.obs)
        os.environ["MSO_OBSERVER_ID"] = "test-runner"

    def cleanup(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key in ["MSO_WORKSPACE_ROOT", "MSO_OBSERVATION_ROOT", "MSO_OBSERVER_ID"]:
            os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# Individual skill tests
# ---------------------------------------------------------------------------

def test_check_deps():
    """mso-skill-governance: check_deps should always succeed (ai-collaborator is optional)."""
    proc = _run(["python3", _script("skills/mso-skill-governance/scripts/check_deps.py")])
    assert proc.returncode == 0, f"check_deps failed: {proc.stderr}"
    assert "ai-collaborator" in proc.stdout


def test_generate_topology():
    """mso-workflow-topology-design: generate a topology spec."""
    ctx = TestContext("topo")
    try:
        proc = _run([
            "python3", _script("skills/mso-workflow-topology-design/scripts/generate_topology.py"),
            "--goal", "분석 결과를 비교하고 보고서 작성",
            "--risk", "medium",
            "--case-slug", "test-topo",
        ])
        assert proc.returncode == 0, f"generate_topology failed: {proc.stderr}"
        assert "WROTE" in proc.stdout

        # Verify output file
        topo_path = ctx.ws / ".mso-context" / "active" / "20260221-msowd-test-topo" / "10_topology" / "workflow_topology_spec.json"
        # The run_id includes today's date, find it dynamically
        active = ctx.ws / ".mso-context" / "active"
        runs = list(active.glob("*-msowd-test-topo"))
        assert runs, "No topology run directory found"
        topo_file = runs[0] / "10_topology" / "workflow_topology_spec.json"
        assert topo_file.exists(), f"Topology file missing: {topo_file}"
        spec = json.loads(topo_file.read_text())
        assert "nodes" in spec
        assert "topology_type" in spec
        assert "decision_questions" in spec
    finally:
        ctx.cleanup()


def test_build_bundle_from_topology():
    """mso-mental-model-design: build bundle from a generated topology."""
    ctx = TestContext("bundle")
    try:
        # Step 1: Generate topology
        proc1 = _run([
            "python3", _script("skills/mso-workflow-topology-design/scripts/generate_topology.py"),
            "--goal", "테스트 목표",
            "--case-slug", "test-bundle",
        ])
        assert proc1.returncode == 0, f"topology failed: {proc1.stderr}"

        active = ctx.ws / ".mso-context" / "active"
        runs = list(active.glob("*-msowd-test-bundle"))
        assert runs
        run_dir = runs[0]
        topo_file = run_dir / "10_topology" / "workflow_topology_spec.json"

        # Step 2: Build bundle
        proc2 = _run([
            "python3", _script("skills/mso-mental-model-design/scripts/build_bundle.py"),
            "--topology", str(topo_file),
            "--run-id", run_dir.name,
            "--skill-key", "msowd",
            "--case-slug", "test-bundle",
        ])
        assert proc2.returncode == 0, f"build_bundle failed: {proc2.stderr}"

        bundle_file = run_dir / "20_mental-model" / "mental_model_bundle.json"
        assert bundle_file.exists()
        bundle = json.loads(bundle_file.read_text())
        assert "local_charts" in bundle
        assert "node_chart_map" in bundle
    finally:
        ctx.cleanup()


def test_build_execution_plan():
    """mso-execution-design: build plan from topology + bundle."""
    ctx = TestContext("plan")
    try:
        # Generate topology
        _run([
            "python3", _script("skills/mso-workflow-topology-design/scripts/generate_topology.py"),
            "--goal", "실행 계획 테스트",
            "--case-slug", "test-plan",
        ])
        active = ctx.ws / ".mso-context" / "active"
        runs = list(active.glob("*-msowd-test-plan"))
        run_dir = runs[0]
        topo = run_dir / "10_topology" / "workflow_topology_spec.json"

        # Build bundle
        _run([
            "python3", _script("skills/mso-mental-model-design/scripts/build_bundle.py"),
            "--topology", str(topo),
            "--run-id", run_dir.name,
            "--skill-key", "msowd",
            "--case-slug", "test-plan",
        ])
        bundle = run_dir / "20_mental-model" / "mental_model_bundle.json"

        # Build plan
        proc = _run([
            "python3", _script("skills/mso-execution-design/scripts/build_plan.py"),
            "--topology", str(topo),
            "--bundle", str(bundle),
            "--run-id", run_dir.name,
            "--skill-key", "msowd",
            "--case-slug", "test-plan",
        ])
        assert proc.returncode == 0, f"build_plan failed: {proc.stderr}"

        plan = run_dir / "30_execution" / "execution_plan.json"
        assert plan.exists()
        data = json.loads(plan.read_text())
        assert "execution_graph" in data
        assert "fallback_rules" in data
    finally:
        ctx.cleanup()


def test_create_ticket_and_update_status():
    """mso-task-context-management: create ticket and test status transitions."""
    ctx = TestContext("ticket")
    try:
        task_root = ctx.tmpdir / "task-context"

        # Bootstrap
        proc = _run([
            "python3", _script("skills/mso-task-context-management/scripts/bootstrap_node.py"),
            "--path", str(task_root),
        ])
        assert proc.returncode == 0

        # Create ticket
        proc = _run([
            "python3", _script("skills/mso-task-context-management/scripts/create_ticket.py"),
            "테스트 티켓",
            "--path", str(task_root),
            "--status", "todo",
            "--owner", "agent",
        ])
        assert proc.returncode == 0
        ticket_path = Path(proc.stdout.strip())
        assert ticket_path.exists()

        # Update status: todo -> in_progress (valid)
        proc = _run([
            "python3", _script("skills/mso-task-context-management/scripts/update_status.py"),
            str(ticket_path),
            "--status", "in_progress",
        ])
        assert proc.returncode == 0
        assert "todo -> in_progress" in proc.stdout

        # Update status: in_progress -> done (valid)
        proc = _run([
            "python3", _script("skills/mso-task-context-management/scripts/update_status.py"),
            str(ticket_path),
            "--status", "done",
        ])
        assert proc.returncode == 0

        # Update status: done -> todo (invalid - should fail)
        proc = _run([
            "python3", _script("skills/mso-task-context-management/scripts/update_status.py"),
            str(ticket_path),
            "--status", "todo",
        ])
        assert proc.returncode != 0, "done -> todo should be rejected"
    finally:
        ctx.cleanup()


def test_dispatch_fallback():
    """mso-agent-collaboration: dispatch should produce fallback when ai-collaborator missing."""
    ctx = TestContext("dispatch")
    try:
        task_root = ctx.tmpdir / "task-context"
        task_root.mkdir(parents=True)
        (task_root / "tickets").mkdir(parents=True)

        # Create a ticket manually
        ticket = task_root / "tickets" / "TKT-0001-test.md"
        ticket.write_text(
            "---\nid: TKT-0001\ntask_context_id: TKT-0001\nstatus: todo\nowner: agent\ndue_by: 2026-03-01\ndependencies: []\ntags: []\n---\n\n# Test\n"
        )

        proc = _run([
            "python3", _script("skills/mso-agent-collaboration/scripts/dispatch.py"),
            "--ticket", str(ticket),
            "--mode", "run",
            "--case-slug", "test-dispatch",
        ])
        assert proc.returncode == 0
        assert "FALLBACK" in proc.stdout

        result_json = ticket.with_suffix(".agent-collaboration.json")
        assert result_json.exists()
        data = json.loads(result_json.read_text())
        assert data.get("requires_manual_confirmation") is True
    finally:
        ctx.cleanup()


def test_audit_db_init_and_append():
    """mso-agent-audit-log: init db then append a payload."""
    ctx = TestContext("audit")
    try:
        db = ctx.tmpdir / "test.db"

        # Init
        proc = _run([
            "python3", _script("skills/mso-agent-audit-log/scripts/init_db.py"),
            "--db", str(db),
            "--migrate",
            "--schema-version", "1.4.0",
        ])
        assert proc.returncode == 0, f"init_db failed: {proc.stderr}"
        assert db.exists()

        # Pipeline-style args should also work
        proc = _run([
            "python3", _script("skills/mso-agent-audit-log/scripts/init_db.py"),
            "--db", str(db),
            "--run-id", "20260221-msoal-test",
            "--skill-key", "msoal",
            "--case-slug", "test",
            "--observer-id", "test",
        ])
        assert proc.returncode == 0, f"init_db with pipeline args failed: {proc.stderr}"

        # Create payload
        payload = ctx.tmpdir / "payload.json"
        payload.write_text(json.dumps({
            "run_id": "test-run",
            "task_id": "TASK-001",
            "artifact_uri": "/tmp/test",
            "status": "success",
            "task_name": "test-task",
        }))

        proc = _run([
            "python3", _script("skills/mso-agent-audit-log/scripts/append_from_payload.py"),
            str(payload),
            "--db", str(db),
        ])
        assert proc.returncode == 0, f"append failed: {proc.stderr}"

        # Verify row inserted
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()
        conn.close()
        assert row[0] >= 1, "No audit rows inserted"

        # Pipeline-style args should also work
        proc = _run([
            "python3", _script("skills/mso-agent-audit-log/scripts/append_from_payload.py"),
            str(payload),
            "--db", str(db),
            "--run-id", "20260221-msoal-test",
            "--skill-key", "msoal",
            "--case-slug", "test",
            "--observer-id", "test",
        ])
        assert proc.returncode == 0, f"append with pipeline args failed: {proc.stderr}"
    finally:
        ctx.cleanup()


def test_observability_collect():
    """mso-observability: collect observations from audit db."""
    ctx = TestContext("obs")
    try:
        db = ctx.tmpdir / "audit.db"
        out_dir = ctx.tmpdir / "obs-out"

        # Init audit db
        _run([
            "python3", _script("skills/mso-agent-audit-log/scripts/init_db.py"),
            "--db", str(db),
            "--migrate",
        ])

        # Collect (empty db) - run_id must match YYYYMMDD-<skill>-<slug> format
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        proc = _run([
            "python3", _script("skills/mso-observability/scripts/collect_observations.py"),
            "--db", str(db),
            "--run-id", f"{today}-msoobs-test-obs",
            "--out", str(out_dir),
            "--mode", "scheduled",
            "--case-slug", "test-obs",
        ])
        assert proc.returncode == 0, f"collect failed: {proc.stderr}"
        assert "WROTE" in proc.stdout

        # Check callback files exist
        callbacks = list(out_dir.glob("callbacks-*.json"))
        assert callbacks, "No callback files generated"
    finally:
        ctx.cleanup()


def test_full_pipeline():
    """Full integration: run_sample_pipeline.py end-to-end."""
    ctx = TestContext("pipeline")
    try:
        proc = _run([
            "python3", _script("skills/mso-skill-governance/scripts/run_sample_pipeline.py"),
            "--goal", "통합 테스트 목표",
            "--task-title", "통합 테스트 작업",
            "--risk", "low",
            "--case-slug", "e2e-test",
        ], cwd=str(ROOT))
        assert proc.returncode == 0, f"Pipeline failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        assert "[pipeline:" in proc.stdout
        assert "done" in proc.stdout
    finally:
        ctx.cleanup()


def test_validate_all_after_pipeline():
    """Governance: validate_all should pass after a successful pipeline run."""
    ctx = TestContext("valall")
    try:
        # Run pipeline first
        proc1 = _run([
            "python3", _script("skills/mso-skill-governance/scripts/run_sample_pipeline.py"),
            "--goal", "검증용 파이프라인",
            "--task-title", "검증 작업",
            "--risk", "low",
            "--case-slug", "valall-test",
        ])
        assert proc1.returncode == 0, f"Pipeline prep failed: {proc1.stderr}"

        # Extract run_id from output
        for line in proc1.stdout.splitlines():
            if "[pipeline:" in line:
                run_id = line.split("[pipeline:")[1].split("]")[0]
                break
        else:
            raise AssertionError("Could not extract run_id from pipeline output")

        # Now validate_all
        proc2 = _run([
            "python3", _script("skills/mso-skill-governance/scripts/validate_all.py"),
            "--run-id", run_id,
            "--case-slug", "valall-test",
        ])
        assert proc2.returncode == 0, f"validate_all failed:\nstdout: {proc2.stdout}\nstderr: {proc2.stderr}"
        assert "findings=0" in proc2.stdout
    finally:
        ctx.cleanup()


if __name__ == "__main__":
    tests = [
        test_check_deps,
        test_generate_topology,
        test_build_bundle_from_topology,
        test_build_execution_plan,
        test_create_ticket_and_update_status,
        test_dispatch_fallback,
        test_audit_db_init_and_append,
        test_observability_collect,
        test_full_pipeline,
        test_validate_all_after_pipeline,
    ]

    passed = 0
    failed = 0
    errors: list[str] = []

    for test in tests:
        name = test.__name__
        try:
            test()
            passed += 1
            print(f"  PASS  {name}")
        except Exception as exc:
            failed += 1
            errors.append(f"{name}: {exc}")
            print(f"  FAIL  {name}: {exc}")

    print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)} tests")
    if errors:
        print("\nFailures:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    sys.exit(0)
