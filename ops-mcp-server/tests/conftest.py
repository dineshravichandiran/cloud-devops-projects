import json

import boto3
import pytest
from botocore.stub import Stubber

from ops_mcp.approvals import ApprovalStore
from ops_mcp.audit import AuditLog
from ops_mcp.aws_tools import AwsTools
from ops_mcp.k8s_tools import K8sTools


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path)


@pytest.fixture
def approvals(tmp_path, audit, clock):
    return ApprovalStore(tmp_path, audit=audit, ttl_s=900, clock=clock)


@pytest.fixture
def aws_stubs():
    """boto3 clients with botocore's Stubber: no network, every call and its arguments are checked against the real API model."""
    clients, stubbers = {}, {}

    def factory(service):
        if service not in clients:
            clients[service] = boto3.client(service, region_name="ap-south-1", aws_access_key_id="x", aws_secret_access_key="x")
            stubbers[service] = Stubber(clients[service])
            stubbers[service].activate()
        return clients[service]

    factory.stub = lambda service: (factory(service), stubbers[service])[1]
    return factory


@pytest.fixture
def aws(aws_stubs, approvals):
    return AwsTools(aws_stubs, approvals)


class FakeKubectl:
    """Records every command and answers from a table keyed by the first two words."""

    def __init__(self):
        self.calls, self.answers = [], {}

    def __call__(self, args):
        self.calls.append(args)
        for key, (rc, out, err) in self.answers.items():
            if args[: len(key)] == list(key):
                return rc, out, err
        return 0, "", ""


@pytest.fixture
def kubectl():
    return FakeKubectl()


@pytest.fixture
def k8s(kubectl, approvals):
    return K8sTools(kubectl, approvals)


def pods_json():
    def pod(name, phase, ready, restarts, waiting=None):
        state = {"waiting": {"reason": waiting}} if waiting else {"running": {}}
        return {"metadata": {"name": name}, "spec": {"nodeName": "n1"},
                "status": {"phase": phase, "containerStatuses": [{"ready": ready, "restartCount": restarts, "state": state}]}}
    return json.dumps({"kind": "List", "items": [pod("web-1", "Running", True, 0), pod("web-2", "Running", False, 7, "CrashLoopBackOff")]})
