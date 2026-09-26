import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from stonic.config.settings import Configuration
from stonic.core.models import PermissionLevel
from stonic.diagnostics.health import Diagnostics
from stonic.events.bus import EventBus
from stonic.events.scheduler import Scheduler
from stonic.events.triggers import Trigger, Triggers
from stonic.security.permissions import PermissionGate
from stonic.skills.manager import SkillManager
from stonic.storage.database import Database
from stonic.tools.registry import ToolRegistry


def make_skill(folder, failure=False):
    folder.mkdir(parents=True)
    manifest={"id":"sample","name":"Test skill","version":"1","description":"A deterministic acceptance fixture", "entrypoint":"main.py",
        "tools":[{"name":"count","description":"Count characters in supplied test text","permission":0,
            "input_schema":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"],"additionalProperties":False},
            "output_schema":{"type":"object","properties":{"count":{"type":"integer"}},"required":["count"],"additionalProperties":False}}]}
    (folder/"skill.json").write_text(json.dumps(manifest))
    (folder/"main.py").write_text('raise RuntimeError("isolated failure")' if failure else 'import json,sys\nr=json.load(sys.stdin)\nprint(json.dumps({"success":True,"status":"completed","message":"Counted input.","data":{"count":len(r["inputs"]["text"])},"verification":"Counted the supplied string in the child process"}))')


async def test_skill_permissions_code_binding_and_isolation(tmp_path):
    with_database=Database(tmp_path/"db.sqlite")
    try:
        registry=ToolRegistry(PermissionGate())
        events=EventBus(with_database)
        make_skill(tmp_path/"skills/sample")
        manager=SkillManager(tmp_path/"skills",with_database,registry,events)
        manifest,digest,_=manager.inspect("sample")
        manager.enable("sample",digest,{})
        assert registry.tools["skill.sample.count"].level == PermissionLevel.CRITICAL
        args={"inputs":{"text":"hello"},"plugin_digest":digest}
        assert not (await registry.invoke("skill.sample.count",args)).success
        grant=registry.permissions.request("skill.sample.count",PermissionLevel.CRITICAL,"count",args)
        registry.permissions.decide(grant.id,True)
        result=await registry.invoke("skill.sample.count",args,grant.id)
        assert result.success and result.data["count"] == 5
        grant=registry.permissions.request("skill.sample.count",PermissionLevel.CRITICAL,"count",args)
        registry.permissions.decide(grant.id,True)
        (tmp_path/"skills/sample/main.py").write_text('raise RuntimeError("edited after approval")')
        assert not (await registry.invoke("skill.sample.count",args,grant.id)).success
        manager.disable("sample")
        manifest,new_digest,_=manager.inspect("sample")
        manager.enable("sample",new_digest,{})
        args["plugin_digest"]=new_digest
        grant=registry.permissions.request("skill.sample.count",PermissionLevel.CRITICAL,"count",args)
        registry.permissions.decide(grant.id,True)
        assert not (await registry.invoke("skill.sample.count",args,grant.id)).success
        assert with_database.query("SELECT 1 AS healthy")[0]["healthy"] == 1
        assert manager.failures["sample"]
    finally:
        with_database.close()


def test_invalid_skill_schema_cannot_crash_discovery(tmp_path):
    db=Database(tmp_path/"db.sqlite")
    try:
        make_skill(tmp_path/"skills/sample")
        path=tmp_path/"skills/sample/skill.json"
        content=json.loads(path.read_text());content["tools"][0]["input_schema"]={"type":"not-a-type"}
        path.write_text(json.dumps(content))
        manager=SkillManager(tmp_path/"skills",db,ToolRegistry(PermissionGate()),EventBus(db))
        assert manager.list()[0]["error"]
    finally:db.close()


def test_file_trigger_restart_dedup_quiet_and_gaming(tmp_path):
    db=Database(tmp_path/"db.sqlite")
    try:
        folder=tmp_path/"downloads";folder.mkdir()
        config=Configuration(db);config.update({"proactive_enabled":True,"quiet_start":0,"quiet_end":0})
        scheduler=Scheduler(db,EventBus(db),config,Diagnostics(tmp_path))
        rules=Triggers(db,scheduler,config)
        rules.save(Trigger(name="Download complete",kind="file_created",target=str(folder)))
        now=datetime.now(timezone.utc)
        rules.tick(now)
        (folder/"pending.crdownload").write_text("incomplete");rules.tick(now)
        assert not db.query("SELECT * FROM notifications")
        (folder/"complete.txt").write_text("ready");rules.tick(now)
        assert len(db.query("SELECT * FROM notifications")) == 1
        Triggers(db,scheduler,config).tick(now+timedelta(seconds=650))
        assert len(db.query("SELECT * FROM notifications")) == 1
        config.update({"gaming_mode":True});(folder/"quiet.txt").write_text("ready")
        rules.tick(now+timedelta(seconds=700))
        assert len(db.query("SELECT * FROM notifications")) == 1
        config.update({"gaming_mode":False});rules.tick(now+timedelta(seconds=800))
        assert len(db.query("SELECT * FROM notifications")) == 2
    finally:db.close()


async def test_vision_ocr_and_capture_expiry(tmp_path):
    import os
    if os.name != "nt":
        pytest.skip("Windows OCR acceptance")
    import base64
    import io
    import shutil
    from PIL import Image,ImageDraw,ImageFont
    from stonic.providers.vision import Vision,VisionRequest
    if not (shutil.which("tesseract") or Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe").is_file()):
        pytest.skip("Tesseract unavailable")
    picture=Image.new("RGB",(800,200),"white")
    font=ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf",48)
    ImageDraw.Draw(picture).text((30,50),"STONIC TEST 7319",font=font,fill="black")
    buffer=io.BytesIO();picture.save(buffer,format="PNG")
    vision=Vision(None,tmp_path/"ocr")
    result=await vision.process(VisionRequest(image="data:image/png;base64,"+base64.b64encode(buffer.getvalue()).decode()))
    assert result.success and "7319" in result.data["text"] and not result.data["uploaded"]
    assert not list((tmp_path/"ocr").iterdir())
    with pytest.raises(ValueError,match="Confirm"):
        await vision.process(VisionRequest(image="data:image/png;base64,"+base64.b64encode(buffer.getvalue()).decode(),mode="analyze"))
    vision.captures["expired"]=(0,b"image")
    with pytest.raises(ValueError,match="expired"):vision.get_capture("expired")
