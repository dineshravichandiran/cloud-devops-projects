from ops_mcp import cli
from ops_mcp.approvals import ApprovalStore


def test_pending_lists_requests_and_approve_needs_a_terminal(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPS_MCP_STATE_DIR", str(tmp_path))
    aid = ApprovalStore(tmp_path).request("k8s_rollout_restart", {"namespace": "shop", "deployment": "web"}, "stuck")
    assert cli.main(["pending"]) == 0
    assert aid in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    assert cli.main(["approve", aid]) == 1                      # no terminal, no approval
    assert ApprovalStore(tmp_path).pending()[aid]["status"] == "pending"


def test_approve_at_a_terminal_records_the_person(tmp_path, monkeypatch):
    monkeypatch.setenv("OPS_MCP_STATE_DIR", str(tmp_path))
    aid = ApprovalStore(tmp_path).request("k8s_rollout_restart", {"namespace": "shop", "deployment": "web"}, "stuck")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert cli.main(["approve", aid]) == 0
    assert ApprovalStore(tmp_path)._load()[aid]["status"] == "approved"
