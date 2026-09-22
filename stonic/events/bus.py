import asyncio,json,os
from collections import deque
from stonic.core.models import RuntimeEvent
from stonic.storage.database import Database
class EventBus:
    def __init__(self,db:Database)->None:self.db=db;self.listeners:set[asyncio.Queue]=set()
    @staticmethod
    def _droppable(event):
        return isinstance(event,dict) and event.get("topic")=="generation" and event.get("data",{}).get("phase")=="delta"
    @staticmethod
    def _evictable(event):
        return EventBus._droppable(event) or (isinstance(event,RuntimeEvent) and event.level=="info" and event.subsystem not in {"startup","security"})
    @classmethod
    def _put(cls,listener,event):
        if not listener.full():listener.put_nowait(event);return
        if cls._droppable(event):return
        retained=deque()
        while not listener.empty():
            old=listener.get_nowait()
            if cls._evictable(old):continue
            retained.append(old)
        while retained and not listener.full():listener.put_nowait(retained.popleft())
        if not listener.full():listener.put_nowait(event)
    def publish(self,subsystem,message,level="info"):
        event=RuntimeEvent(subsystem=subsystem,message=message,level=level)
        if subsystem=="startup" and os.environ.get("STONIC_MANAGED")=="1":print("STONIC_STAGE:"+json.dumps({"message":message}),flush=True)
        self.db.execute("INSERT INTO audit VALUES(?,?,?,?,?)",(event.id,event.time,event.subsystem,event.level,event.message));self.db.execute("DELETE FROM audit WHERE rowid NOT IN (SELECT rowid FROM audit ORDER BY rowid DESC LIMIT 2000)")
        for listener in tuple(self.listeners):self._put(listener,event)
        return event
    def recent(self):return self.db.query("SELECT * FROM audit ORDER BY rowid DESC LIMIT 80")
    def emit(self,topic,data):
        event={"topic":topic,"data":data}
        for listener in tuple(self.listeners):self._put(listener,event)
