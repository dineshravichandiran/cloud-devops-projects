"""Input checks and output limits shared by every tool."""
from __future__ import annotations

import re

MAX_OUTPUT_CHARS = 20_000

_K8S_NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
_LOG_GROUP = re.compile(r"^[A-Za-z0-9_/.#-]{1,512}$")
_ASG_NAME = re.compile(r"^[A-Za-z0-9 _.:/@+=,-]{1,255}$")
_INSTANCE = re.compile(r"^i-[0-9a-f]{8,17}$")
_ARN = re.compile(r"^arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:\d{12}:[A-Za-z0-9:/_.-]+$")

_REDACT = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[redacted-aws-key-id]"),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[redacted]"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|aws_secret_access_key)\b(\s*[=:]\s*)[^\s,;\"']+"), r"\1\2[redacted]"),
]


class InvalidInput(ValueError):
    pass


def _check(pattern: re.Pattern, value: str, what: str) -> str:
    if not isinstance(value, str) or not pattern.match(value):
        raise InvalidInput(f"invalid {what}: {str(value)[:60]!r}")
    return value


def k8s_name(value: str, what: str = "name") -> str:
    """A Kubernetes object name. Rejects anything starting with '-', so it can never be read as a kubectl flag."""
    return _check(_K8S_NAME, value, what)


def log_group(value: str) -> str:
    return _check(_LOG_GROUP, value, "log group")


def asg_name(value: str) -> str:
    return _check(_ASG_NAME, value, "Auto Scaling group name")


def instance_id(value: str) -> str:
    return _check(_INSTANCE, value, "instance id")


def arn(value: str) -> str:
    return _check(_ARN, value, "ARN")


def bounded(value: int, low: int, high: int, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise InvalidInput(f"{what} must be an integer from {low} to {high}")
    return value


def redact(text: str) -> str:
    """Mask obvious secrets in log text. A safety net, not a guarantee: it only knows a few patterns."""
    for pat, repl in _REDACT:
        text = pat.sub(repl, text)
    return text


def clip(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n[output cut at {limit} characters]"
