import json,os,socket
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
import psutil
from pydantic import Field,model_validator
from stonic.core.models import Contract
class Trigger(Contract):
    name:str=Field(min_length=1,max_length=200);kind:Literal["file_created","application_opened","task_completed","network_restored","high_cpu","high_memory"];target:str=Field(default="",max_length=1000);threshold:float=Field(default=90,ge=1,le=100);cooldown_seconds:int=Field(default=600,ge=60,le=86400);enabled:bool=True
    @model_validator(mode="after")
    def target_required(self):
        if self.kind in {"file_created","application_opened"} and not self.target.strip():raise ValueError("Choose the folder or exact application executable name")
        if self.kind=="file_created" and (not Path(self.target).is_absolute() or not Path(self.target).is_dir()):raise ValueError("Choose an existing absolute folder path")
        return self
class Triggers:
    def __init__(self,db,scheduler,config):self.db,self.scheduler,self.config=db,scheduler,config;self.failures={};db.execute("CREATE TABLE IF NOT EXISTS triggers (id TEXT PRIMARY KEY,payload TEXT NOT NULL,state TEXT,last_fired TEXT)")
    def list(self):
        result=[]
        for row in self.db.query("SELECT * FROM triggers"):
            try:result.append({"id":row["id"],**json.loads(row["payload"]),"last_fired":row["last_fired"]})
            except (json.JSONDecodeError,TypeError):result.append({"id":row["id"],"name":"Invalid trigger","enabled":False,"error":"Saved trigger data is invalid; remove and recreate it.","last_fired":row["last_fired"]})
        return result
    def save(self,trigger,identifier=None):
        identifier=identifier or str(uuid4());self.db.execute("INSERT INTO triggers VALUES(?,?,NULL,NULL) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,state=NULL",(identifier,trigger.model_dump_json()));return {"id":identifier,**trigger.model_dump()}
    @staticmethod
    def _internet_reachable():
        for host in ("1.1.1.1","8.8.8.8"):
            try:
                with socket.create_connection((host,443),timeout=1.0):return True
            except OSError:continue
        return False
    def sample(self,rule,metrics):
        if rule.kind=="file_created":
            root=Path(rule.target);files=[]
            with os.scandir(root) as entries:
                for entry in entries:
                    if entry.is_file(follow_symlinks=False) and not entry.name.lower().endswith((".tmp",".part",".crdownload",".download")):files.append(entry.name)
            return sorted(files)
        if rule.kind=="application_opened":return sorted(f"{p.pid}:{p.create_time():.3f}" for p in psutil.process_iter(["name","create_time"]) if (p.info.get("name") or "").casefold()==rule.target.casefold())
        if rule.kind=="task_completed":return [row["id"] for row in self.db.query("SELECT id FROM jobs WHERE status='completed' ORDER BY updated_at DESC")]
        if rule.kind=="network_restored":return self._internet_reachable()
        return metrics["cpu_percent" if rule.kind=="high_cpu" else "memory_percent"]>=rule.threshold
    def tick(self,now=None):
        now=now or datetime.now(timezone.utc);permitted=self.config.values.proactive_enabled and not self.scheduler.quiet();metrics=self.scheduler.diagnostics.metrics()
        for row in self.db.query("SELECT * FROM triggers"):
            failed=self.failures.get(row["id"])
            if failed and (now-failed[0]).total_seconds()<min(600,10*2**min(failed[1],6)):continue
            try:rule=Trigger.model_validate_json(row["payload"])
            except ValueError:
                self.failures[row["id"]]=(now,(failed[1]+1) if failed else 1)
                if not failed:self.scheduler.events.publish("triggers","An invalid saved rule was isolated. Edit or remove it in Events.","warning")
                continue
            if not rule.enabled:continue
            try:sample=self.sample(rule,metrics)
            except (OSError,psutil.Error,ValueError):
                self.failures[row["id"]]=(now,(failed[1]+1) if failed else 1)
                if not failed:self.scheduler.events.publish("triggers","A trigger target could not be inspected; retries use bounded backoff. Other rules remain active.","warning")
                continue
            self.failures.pop(row["id"],None)
            try:previous=json.loads(row["state"]) if row["state"] is not None else None
            except json.JSONDecodeError:previous=None
            state_value=previous;changed=False;next_state=sample
            if isinstance(sample,list) and isinstance(previous,list):
                changed=bool(set(sample)-set(previous))
            elif isinstance(sample,bool):
                if isinstance(previous,dict) and isinstance(previous.get("value"),bool):
                    baseline=previous["value"];last_sample=previous.get("sample",baseline);streak=int(previous.get("streak",1))
                elif isinstance(previous,bool):
                    baseline=previous;last_sample=previous;streak=1
                else:
                    baseline=None;last_sample=sample;streak=1
                streak=streak+1 if sample==last_sample else 1
                changed=baseline is False and sample is True and streak>=2
                next_state={"value":sample if permitted else (baseline if baseline is not None else sample),"sample":sample,"streak":streak}
            if previous is None:
                self.db.execute("UPDATE triggers SET state=? WHERE id=?",(json.dumps(next_state),row["id"]));continue
            self.db.execute("UPDATE triggers SET state=? WHERE id=?",(json.dumps(next_state if isinstance(sample,bool) else (sample if permitted else previous)),row["id"]))
            if not permitted:
                continue
            if isinstance(sample,bool) and isinstance(next_state,dict) and next_state.get("value") is sample and changed:
                # Keep the baseline transition committed; notification follows below.
                pass
            if not changed:continue
            if row["last_fired"] and (now-datetime.fromisoformat(row["last_fired"])).total_seconds()<rule.cooldown_seconds:continue
            bucket=int(now.timestamp()//rule.cooldown_seconds)
            if self.scheduler.notify(rule.name,f"Your {rule.kind.replace('_',' ')} condition was observed.","trigger",f"trigger:{row['id']}:{bucket}"):self.db.execute("UPDATE triggers SET last_fired=? WHERE id=?",(now.isoformat(),row["id"]))
