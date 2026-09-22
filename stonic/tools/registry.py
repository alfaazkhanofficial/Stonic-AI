from dataclasses import dataclass
import asyncio
import inspect
from typing import Callable

from pydantic import BaseModel, ValidationError

from stonic.core.models import ActionResult, PermissionLevel
from stonic.security.permissions import PermissionGate


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: type[BaseModel]
    level: PermissionLevel
    run: Callable[[BaseModel], ActionResult]
    retry_safe: bool = False
    timeout: float = 30
    prepare: Callable[[BaseModel], BaseModel] | None = None


class ToolRegistry:
    def __init__(self, permissions: PermissionGate) -> None:
        self.permissions = permissions
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        self.tools[tool.name] = tool

    def execute(self, name: str, arguments: dict, grant: str | None = None) -> ActionResult:
        tool = self.tools.get(name)
        if not tool:
            return ActionResult(success=False, status="unavailable", message="This tool is not registered.")
        try:
            validated = tool.arguments.model_validate(arguments)
        except ValidationError:
            return ActionResult(success=False, status="failed", message="Tool arguments did not match its schema.")
        if not self.permissions.authorize(name, tool.level, grant, validated.model_dump(mode="json")):
            return ActionResult(success=False, status="denied", message="Explicit confirmation is required.", permission_level=tool.level)
        try:
            return tool.run(validated)
        except (OSError, ValueError) as error:
            return ActionResult(success=False, status="failed", message="The tool could not complete.", error=type(error).__name__, permission_level=tool.level)

    def catalog(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "permission_level": t.level,
                 "arguments": t.arguments.model_json_schema(), "retry_safe": t.retry_safe} for t in self.tools.values()]

    async def invoke(self, name: str, arguments: dict, grant: str | None = None) -> ActionResult:
        tool = self.tools.get(name)
        if not tool:
            return ActionResult(success=False, status="unavailable", message="This tool is not registered.")
        try:
            validated = tool.arguments.model_validate(arguments)
        except ValidationError:
            return ActionResult(success=False, status="failed", message="Tool arguments did not match its schema.")
        if not self.permissions.authorize(name, tool.level, grant, validated.model_dump(mode="json")):
            return ActionResult(success=False, status="denied", message="Explicit confirmation is required.", permission_level=tool.level)
        try:
            async with asyncio.timeout(tool.timeout):
                result = tool.run(validated)
                if inspect.isawaitable(result):
                    result = await result
                result = ActionResult.model_validate(result)
                if result.success and not result.verification:
                    return ActionResult(success=False, status="failed", message="Action returned no verification evidence.", permission_level=tool.level)
                if result.success and result.verification_kind == "evidence" and tool.level >= PermissionLevel.SENSITIVE:
                    result.metadata.setdefault("verification_note", "Evidence describes what STONIC observed or delivered; it is not necessarily proof of the final application state.")
                result.permission_level = tool.level
                return result
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Say WHY, for the user's diagnostics panel and for a planner that has to recover. Only errors the tools raise on
            # purpose (ValueError / OSError / timeouts) carry a message worth showing; anything else stays a bare type name.
            detail = ""
            if isinstance(error, TimeoutError):
                detail = f"The action did not finish within {tool.timeout:g} seconds."
            elif isinstance(error, (ValueError, OSError)):
                detail = str(error).strip()[:300]
            return ActionResult(success=False, status="failed", message="The action failed. Inspect its inputs and diagnostics.",
                                error=type(error).__name__, retryable=tool.retry_safe, permission_level=tool.level,
                                data={"error": type(error).__name__, "detail": detail} if detail else {})
