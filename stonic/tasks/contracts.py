import json
from typing import Literal
from pydantic import Field, model_validator
from stonic.core.models import Contract


class PlanStep(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    title: str = Field(min_length=1, max_length=200)
    tool: str = Field(min_length=1, max_length=100)
    arguments_json: str = Field(max_length=24000)
    depends_on: list[str] = Field(max_length=20)

    def arguments(self) -> dict:
        result = json.loads(self.arguments_json)
        if not isinstance(result, dict):
            raise ValueError("Step arguments must be an object")
        return result


class Decision(Contract):
    kind: Literal["answer", "clarify", "plan"]
    message: str = Field(min_length=1, max_length=16000)
    steps: list[PlanStep] = Field(max_length=20)

    @model_validator(mode="after")
    def valid_plan(self):
        if self.kind != "plan" and self.steps:
            raise ValueError("Only plans may contain actions")
        if self.kind == "plan" and not self.steps:
            raise ValueError("A plan requires actions")
        seen = set()
        for step in self.steps:
            if step.id in seen or any(dep not in seen for dep in step.depends_on):
                raise ValueError("Steps must have unique ids and dependencies must refer to earlier steps")
            step.arguments()
            seen.add(step.id)
        return self
