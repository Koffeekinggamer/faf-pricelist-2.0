"""PR CI must run Ruff + pytest with no Fly secrets and no catalog DB."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PR_CI = ROOT / ".github" / "workflows" / "pr-ci.yml"
FLY_DEPLOY = ROOT / ".github" / "workflows" / "fly-deploy.yml"
PULL_FLY_DB = ROOT / ".github" / "workflows" / "pull-fly-db.yml"


def test_pr_ci_workflow_exists():
    assert PR_CI.is_file(), "missing .github/workflows/pr-ci.yml"


def test_pr_ci_runs_ruff_and_pytest_on_pull_request():
    text = PR_CI.read_text(encoding="utf-8")
    assert "pull_request" in text
    assert "3.11" in text
    assert "requirements.txt" in text
    assert "run_ruff.sh check" in text
    assert "python -m pytest -q" in text
    assert "FLY_API_TOKEN" not in text
    assert "flyctl" not in text
    assert "superfly" not in text
    assert "master_pricebook.db" not in text


def test_fly_deploy_stays_main_only():
    text = FLY_DEPLOY.read_text(encoding="utf-8")
    assert "pull_request" not in text
    assert "branches:" in text
    assert "- main" in text


def test_pull_fly_db_stays_manual():
    text = PULL_FLY_DB.read_text(encoding="utf-8")
    assert "pull_request" not in text
    assert "workflow_dispatch" in text
