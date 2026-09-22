from time import monotonic
import hashlib
import json

from stonic.core.models import PermissionLevel, PermissionRequest


class PermissionGate:
    """Short-lived, one-use decisions tied to an exact action; default deny."""
    def __init__(self) -> None:
        self.pending: dict[str, tuple[PermissionRequest, float]] = {}
        self.approved: dict[str, tuple[str, float]] = {}

    @staticmethod
    def fingerprint(action: str, arguments: dict | None = None) -> str:
        return hashlib.sha256(json.dumps([action, arguments or {}], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    def request(self, action: str, level: PermissionLevel, description: str, arguments: dict | None = None) -> PermissionRequest:
        now = monotonic()
        self.pending = {key:value for key,value in self.pending.items() if value[1] >= now}
        self.approved = {key:value for key,value in self.approved.items() if value[1] >= now}
        request = PermissionRequest(action=action, level=level, description=description, fingerprint=self.fingerprint(action, arguments))
        self.pending[request.id] = (request, now + 120)
        return request

    def decide(self, identifier: str, approved: bool) -> None:
        item = self.pending.pop(identifier, None)
        if not item or item[1] < monotonic():
            raise ValueError("Permission request expired or does not exist")
        if approved:
            self.approved[identifier] = (item[0].fingerprint, item[1])

    def authorize(self, action: str, level: PermissionLevel, grant: str | None = None, arguments: dict | None = None) -> bool:
        if level <= PermissionLevel.NORMAL:
            return True
        item = self.approved.pop(grant, None) if grant else None
        return bool(item and item[0] == self.fingerprint(action, arguments) and item[1] >= monotonic())
