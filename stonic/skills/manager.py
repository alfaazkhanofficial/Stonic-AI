import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator
from pydantic import Field, create_model, field_validator
from stonic.core.models import ActionResult, Contract, PermissionLevel
from stonic.tools.registry import Tool
from stonic.security.process import sanitized_environment


class SkillTool(Contract):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")
    description: str = Field(min_length=5, max_length=1000)
    permission: int = Field(ge=0, le=3)
    input_schema: dict
    output_schema: dict

    @field_validator("input_schema", "output_schema")
    @classmethod
    def schema(cls, value):
        from jsonschema.exceptions import SchemaError
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as error:
            raise ValueError("Invalid JSON schema") from error
        if value.get("type") != "object":
            raise ValueError("Skill schemas must describe an object")
        # No remote schema resolution, network retrieval, or recursive schemas.
        def inspect(node):
            if isinstance(node, dict):
                if "$ref" in node or "$dynamicRef" in node:
                    raise ValueError("Skill schemas must be self-contained without references")
                for child in node.values():
                    inspect(child)
            elif isinstance(node, list):
                for child in node:
                    inspect(child)
        inspect(value)
        return value


class Manifest(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=5, max_length=2000)
    entrypoint: str = Field(pattern=r"^[a-zA-Z0-9_/.-]+\.py$")
    tools: list[SkillTool] = Field(min_length=1, max_length=20)
    config_schema: dict = Field(default_factory=lambda: {"type": "object", "additionalProperties": False})

    @field_validator("config_schema")
    @classmethod
    def configuration(cls, value):
        return SkillTool.schema(value)


class SkillManager:
    """Process isolation protects service availability, not OS privileges. Skills are trusted code."""
    def __init__(self, directory, db, registry, events):
        self.directory, self.db, self.registry, self.events = Path(directory), db, registry, events
        self.directory.mkdir(parents=True, exist_ok=True)
        db.execute("CREATE TABLE IF NOT EXISTS skills (id TEXT PRIMARY KEY, enabled INTEGER NOT NULL, digest TEXT NOT NULL, config TEXT NOT NULL)")
        self.loaded = {}
        self.failures = {}
        for record in db.query("SELECT * FROM skills WHERE enabled=1"):
            try:
                self.enable(record["id"], record["digest"], json.loads(record["config"]))
            except (ValueError, OSError):
                self.failures[record["id"]] = "Skill changed or could not initialize. Review it before enabling again."

    def inspect(self, identifier):
        if not isinstance(identifier, str) or not __import__("re").fullmatch(r"[a-z][a-z0-9_]{0,40}", identifier):
            raise ValueError("Invalid skill identifier")
        folder = (self.directory / identifier).resolve()
        if folder.parent != self.directory.resolve():
            raise ValueError("Skill directory is outside the skills folder")
        manifest_path = folder / "skill.json"
        if not manifest_path.is_file() or manifest_path.stat().st_size > 100000:
            raise ValueError("Skill manifest missing or too large")
        manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if manifest.id != identifier or len({t.name for t in manifest.tools}) != len(manifest.tools):
            raise ValueError("Skill identity or tool names are invalid")
        entry = (folder / manifest.entrypoint).resolve()
        if not entry.is_relative_to(folder) or not entry.is_file():
            raise ValueError("Skill entrypoint must exist inside its folder")
        digest = hashlib.sha256()
        total = 0
        files = sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        if len(files) > 200:
            raise ValueError("Skill bundle contains too many files")
        for path in files:
            if path.is_symlink() or not path.resolve().is_relative_to(folder):
                raise ValueError("Skill files cannot link outside their bundle")
            total += path.stat().st_size
            if total > 20_000_000:
                raise ValueError("Skill code bundle exceeds 20 MB")
            digest.update(path.relative_to(folder).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
        return manifest, digest.hexdigest(), entry

    def list(self):
        result = []
        for path in sorted(self.directory.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            try:
                manifest, digest, _ = self.inspect(path.name)
                rows = self.db.query("SELECT config FROM skills WHERE id=?", (manifest.id,))
                result.append({**manifest.model_dump(), "digest": digest, "enabled": manifest.id in self.loaded,
                    "config": json.loads(rows[0]["config"]) if rows else {}, "error": self.failures.get(manifest.id),
                    "execution_permission": 3})
            except (ValueError, OSError):
                result.append({"id": path.name, "name": path.name, "enabled": False, "error": "Invalid skill bundle; inspect skill.json and its schemas."})
        return result

    def disable(self, identifier):
        for name in self.loaded.pop(identifier, []):
            self.registry.tools.pop(name, None)
        self.db.execute("UPDATE skills SET enabled=0 WHERE id=?", (identifier,))
        self.events.publish("skills", "A skill was disabled and its tools unregistered.")

    def enable(self, identifier, expected_digest, configuration):
        manifest, digest, entry = self.inspect(identifier)
        if digest != expected_digest:
            raise ValueError("Skill files changed since review. Refresh and review the new bundle.")
        errors = list(Draft202012Validator(manifest.config_schema).iter_errors(configuration))
        if errors:
            raise ValueError("Skill configuration does not match its schema")
        self.disable(identifier)
        names = []
        for declaration in manifest.tools:
            name = f"skill.{identifier}.{declaration.name}"
            arguments = create_model(f"Skill_{identifier}_{declaration.name}", __base__=Contract,
                inputs=(dict[str, Any], Field(json_schema_extra=declaration.input_schema)),
                plugin_digest=(str, digest))
            async def invoke(args, spec=declaration, model=manifest, pinned=digest, script=entry, cfg=configuration):
                return await self.execute(model, spec, pinned, script, cfg, args)
            self.registry.register(Tool(name, declaration.description + " Runs trusted local skill code; review every invocation.",
                arguments, PermissionLevel.CRITICAL, invoke, timeout=35))
            names.append(name)
        self.loaded[identifier] = names
        self.failures.pop(identifier, None)
        self.db.execute("INSERT INTO skills VALUES(?,1,?,?) ON CONFLICT(id) DO UPDATE SET enabled=1,digest=excluded.digest,config=excluded.config",
            (identifier, digest, json.dumps(configuration)))
        self.events.publish("skills", "A reviewed skill was enabled with validated schemas and critical action permissions.")

    async def execute(self, manifest, declaration, digest, entry, configuration, args):
        if manifest.id not in self.loaded or args.plugin_digest != digest or self.inspect(manifest.id)[1] != digest:
            raise ValueError("The approved skill is disabled or its code changed")
        if list(Draft202012Validator(declaration.input_schema).iter_errors(args.inputs)):
            raise ValueError("Skill input failed schema validation")
        # No application credentials are inherited; trusted skill code still has normal user OS access.
        environment = sanitized_environment(extra={"PYTHONUTF8": "1"})
        process = await asyncio.create_subprocess_exec(sys.executable, "-I", "-B", str(entry), cwd=entry.parent,
            env=environment, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, creationflags=0x08000000 if os.name == "nt" else 0)
        try:
            async with asyncio.timeout(30):
                request = {"request_id": str(uuid4()), "tool": declaration.name, "inputs": args.inputs, "config": configuration}
                process.stdin.write(json.dumps(request).encode())
                await process.stdin.drain()
                process.stdin.close()
                output = bytearray()
                while block := await process.stdout.read(8192):
                    output.extend(block)
                    if len(output) > 256000:
                        raise ValueError("Skill output exceeded its size limit")
                if await process.wait() != 0:
                    raise ValueError("Skill process failed")
                result = ActionResult.model_validate_json(output)
                if list(Draft202012Validator(declaration.output_schema).iter_errors(result.data)):
                    raise ValueError("Skill output failed schema validation")
                if result.success and not result.verification:
                    raise ValueError("Skill returned no verification evidence")
                return result
        except BaseException:
            self.failures[manifest.id] = "The last skill run failed or was cancelled. Other Stonic features remain available."
            raise
        finally:
            if process.returncode is None:
                if os.name == "nt":
                    killer = await asyncio.create_subprocess_exec("taskkill.exe", "/PID", str(process.pid), "/T", "/F",
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, creationflags=0x08000000)
                    await killer.wait()
                else:
                    process.kill()
                await process.wait()
