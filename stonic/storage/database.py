"""Durable local SQLite storage with transactional schema upgrades and recovery."""
from __future__ import annotations
import json,sqlite3,shutil
from datetime import datetime,timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4
from stonic.core.models import utc_now
SCHEMA_VERSION=4
class Database:
    def __init__(self,path:Path)->None:
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=RLock();self.recovery=None;self.migration_backup=None;self.connection=None;self._open_and_initialize()
    def _connect(self):
        c=sqlite3.connect(self.path,check_same_thread=False,timeout=15);c.row_factory=sqlite3.Row;c.execute("PRAGMA busy_timeout=15000");return c
    def _integrity_ok(self,c):
        try:return c.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        except sqlite3.DatabaseError:return False
    def _quarantine_corrupt(self):
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");target=self.path.with_name(f"{self.path.stem}.corrupt-{stamp}{self.path.suffix}");i=1
        while target.exists():target=self.path.with_name(f"{self.path.stem}.corrupt-{stamp}-{i}{self.path.suffix}");i+=1
        if self.path.exists():self.path.replace(target)
        for suffix in ("-wal","-shm"):Path(str(self.path)+suffix).unlink(missing_ok=True)
        return target
    def _backup_before_migration(self):
        d=self.path.parent/"backups";d.mkdir(exist_ok=True);stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");target=d/f"{self.path.stem}-pre-migration-{stamp}.sqlite";i=1
        while target.exists():target=d/f"{self.path.stem}-pre-migration-{stamp}-{i}.sqlite";i+=1
        src=self._connect()
        try:
            dst=sqlite3.connect(target)
            try:src.backup(dst)
            finally:dst.close()
        finally:src.close()
        backups=sorted(d.glob(f"{self.path.stem}-pre-migration-*.sqlite"),key=lambda p:p.stat().st_mtime,reverse=True)
        for old in backups[5:]:old.unlink(missing_ok=True)
        return target
    def _open_and_initialize(self):
        existed=self.path.exists()
        try:
            c=self._connect()
            if existed and not self._integrity_ok(c):
                c.close();corrupt=self._quarantine_corrupt();self.recovery={"kind":"database_corrupt","quarantined":str(corrupt)};c=self._connect();existed=False
            self.connection=c;version=int(c.execute("PRAGMA user_version").fetchone()[0])
            if version>SCHEMA_VERSION:raise ValueError("Database belongs to a newer STONIC version")
            backup=self._backup_before_migration() if existed and version<SCHEMA_VERSION else None;self.migration_backup=backup
            try:self._migrate(version)
            except Exception:
                c.close();self.connection=None
                if backup and backup.exists():self.path.unlink(missing_ok=True);shutil.copy2(backup,self.path)
                raise
        except sqlite3.DatabaseError as error:
            if self.connection is not None:
                try:self.connection.close()
                except Exception:pass
                self.connection=None
            if self.path.exists():
                corrupt=self._quarantine_corrupt();self.recovery={"kind":"database_corrupt","quarantined":str(corrupt),"error":type(error).__name__}
            self.connection=self._connect();self._migrate(0)
    def _columns(self,table):return {r[1] for r in self.connection.execute(f'PRAGMA table_info("{table}")').fetchall()}
    def _ensure_column(self,table,column,definition):
        if column not in self._columns(table):self.connection.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')
    def _create_tables(self):
        self.connection.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY,session_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY,time TEXT NOT NULL,subsystem TEXT NOT NULL,level TEXT NOT NULL,message TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1),current TEXT NOT NULL,previous TEXT)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,session_id TEXT NOT NULL,goal TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS schedules (id TEXT PRIMARY KEY,title TEXT NOT NULL,due_at TEXT NOT NULL,interval_seconds INTEGER,status TEXT NOT NULL,created_at TEXT NOT NULL,last_fired TEXT)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,source TEXT NOT NULL,created_at TEXT NOT NULL,read INTEGER NOT NULL DEFAULT 0,dedup_key TEXT UNIQUE)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS preferences (id TEXT PRIMARY KEY,category TEXT NOT NULL,value TEXT NOT NULL,approved INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS memory_metadata (record_id TEXT PRIMARY KEY,category TEXT NOT NULL DEFAULT 'user')")
        self.connection.execute("CREATE TABLE IF NOT EXISTS triggers (id TEXT PRIMARY KEY,payload TEXT NOT NULL,state TEXT,last_fired TEXT)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS skills (id TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 0,digest TEXT NOT NULL DEFAULT '',config TEXT NOT NULL DEFAULT '{}')")
        self.connection.execute("CREATE TABLE IF NOT EXISTS briefings (day TEXT PRIMARY KEY,payload TEXT NOT NULL,generated_at TEXT NOT NULL,viewed_at TEXT)")
    def _repair_columns(self):
        repairs={"records":{"kind":"TEXT NOT NULL DEFAULT 'notes'","title":"TEXT NOT NULL DEFAULT ''","content":"TEXT NOT NULL DEFAULT ''","status":"TEXT NOT NULL DEFAULT 'open'","created_at":"TEXT NOT NULL DEFAULT ''","updated_at":"TEXT NOT NULL DEFAULT ''"},"messages":{"session_id":"TEXT NOT NULL DEFAULT 'main'","role":"TEXT NOT NULL DEFAULT 'user'","content":"TEXT NOT NULL DEFAULT ''","created_at":"TEXT NOT NULL DEFAULT ''"},"audit":{"time":"TEXT NOT NULL DEFAULT ''","subsystem":"TEXT NOT NULL DEFAULT 'storage'","level":"TEXT NOT NULL DEFAULT 'info'","message":"TEXT NOT NULL DEFAULT ''"},"settings":{"previous":"TEXT"},"jobs":{"session_id":"TEXT NOT NULL DEFAULT 'main'","goal":"TEXT NOT NULL DEFAULT ''","status":"TEXT NOT NULL DEFAULT 'paused'","payload":"TEXT NOT NULL DEFAULT '{}'","created_at":"TEXT NOT NULL DEFAULT ''","updated_at":"TEXT NOT NULL DEFAULT ''"},"schedules":{"title":"TEXT NOT NULL DEFAULT 'Reminder'","due_at":"TEXT NOT NULL DEFAULT ''","interval_seconds":"INTEGER","status":"TEXT NOT NULL DEFAULT 'active'","created_at":"TEXT NOT NULL DEFAULT ''","last_fired":"TEXT"},"notifications":{"title":"TEXT NOT NULL DEFAULT ''","body":"TEXT NOT NULL DEFAULT ''","source":"TEXT NOT NULL DEFAULT 'system'","created_at":"TEXT NOT NULL DEFAULT ''","read":"INTEGER NOT NULL DEFAULT 0","dedup_key":"TEXT"},"preferences":{"category":"TEXT NOT NULL DEFAULT 'communication'","value":"TEXT NOT NULL DEFAULT ''","approved":"INTEGER NOT NULL DEFAULT 0","created_at":"TEXT NOT NULL DEFAULT ''"},"memory_metadata":{"category":"TEXT NOT NULL DEFAULT 'user'"},"triggers":{"payload":"TEXT NOT NULL DEFAULT '{}'","state":"TEXT","last_fired":"TEXT"},"skills":{"enabled":"INTEGER NOT NULL DEFAULT 0","digest":"TEXT NOT NULL DEFAULT ''","config":"TEXT NOT NULL DEFAULT '{}'"},"briefings":{"payload":"TEXT NOT NULL DEFAULT '{}'","generated_at":"TEXT NOT NULL DEFAULT ''","viewed_at":"TEXT"}}
        for table,cols in repairs.items():
            for col,definition in cols.items():self._ensure_column(table,col,definition)
        now=utc_now();self.connection.execute("UPDATE records SET created_at=? WHERE created_at='' OR created_at IS NULL",(now,));self.connection.execute("UPDATE records SET updated_at=created_at WHERE updated_at='' OR updated_at IS NULL",());self.connection.execute("UPDATE messages SET created_at=? WHERE created_at='' OR created_at IS NULL",(now,));self.connection.execute("UPDATE audit SET time=? WHERE time='' OR time IS NULL",(now,));self.connection.execute("UPDATE jobs SET created_at=? WHERE created_at='' OR created_at IS NULL",(now,));self.connection.execute("UPDATE jobs SET updated_at=created_at WHERE updated_at='' OR updated_at IS NULL");self.connection.execute("UPDATE preferences SET created_at=? WHERE created_at='' OR created_at IS NULL",(now,));self.connection.execute("UPDATE schedules SET created_at=? WHERE created_at='' OR created_at IS NULL",(now,));self.connection.execute("UPDATE briefings SET generated_at=? WHERE generated_at='' OR generated_at IS NULL",(now,))
        if "id" not in self._columns("records"):
            rows=[dict(r) for r in self.connection.execute("SELECT * FROM records").fetchall()];self.connection.execute("DROP TABLE IF EXISTS records_new");self.connection.execute("CREATE TABLE records_new (id TEXT PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
            for row in rows:self.connection.execute("INSERT INTO records_new VALUES(?,?,?,?,?,?,?)",(str(uuid4()),row.get("kind") or "notes",row.get("title") or "",row.get("content") or "",row.get("status") or "open",row.get("created_at") or now,row.get("updated_at") or row.get("created_at") or now))
            self.connection.execute("DROP TABLE records");self.connection.execute("ALTER TABLE records_new RENAME TO records")
    def _create_indexes(self):
        self.connection.execute("CREATE INDEX IF NOT EXISTS records_kind_date ON records(kind,created_at DESC)");self.connection.execute("CREATE INDEX IF NOT EXISTS messages_session_date ON messages(session_id,created_at DESC)");self.connection.execute("CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status)");self.connection.execute("CREATE INDEX IF NOT EXISTS schedules_status_due ON schedules(status,due_at)")
        self.connection.execute("CREATE TRIGGER IF NOT EXISTS memory_metadata_delete AFTER DELETE ON records BEGIN DELETE FROM memory_metadata WHERE record_id=old.id; END")
        self.connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_index USING fts5(id UNINDEXED,title,content)")
        self.connection.execute("CREATE TRIGGER IF NOT EXISTS memory_insert AFTER INSERT ON records WHEN new.kind='memory' BEGIN INSERT INTO memory_index(id,title,content) VALUES(new.id,new.title,new.content); END")
        self.connection.execute("CREATE TRIGGER IF NOT EXISTS memory_delete AFTER DELETE ON records WHEN old.kind='memory' BEGIN DELETE FROM memory_index WHERE id=old.id; END")
        self.connection.execute("CREATE TRIGGER IF NOT EXISTS memory_update AFTER UPDATE ON records WHEN new.kind='memory' BEGIN DELETE FROM memory_index WHERE id=new.id;INSERT INTO memory_index(id,title,content) VALUES(new.id,new.title,new.content); END")
        self.connection.execute("INSERT INTO memory_index(id,title,content) SELECT id,title,content FROM records WHERE kind='memory' AND id NOT IN (SELECT id FROM memory_index)")
    def _migrate(self,version):
        with self.lock,self.connection:self._create_tables();self._repair_columns();self._create_indexes();self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    def query(self,sql,values=()):
        with self.lock:return [dict(r) for r in self.connection.execute(sql,values).fetchall()]
    def execute(self,sql,values=()):
        with self.lock,self.connection:return self.connection.execute(sql,values).rowcount
    def records(self,kind):
        if kind=="memory":return self.query("SELECT r.*,COALESCE(m.category,'user') AS memory_type FROM records r LEFT JOIN memory_metadata m ON m.record_id=r.id WHERE r.kind='memory' ORDER BY r.created_at DESC")
        return self.query("SELECT * FROM records WHERE kind=? ORDER BY created_at DESC",(kind,))
    def classify_memory(self,identifier,category):
        if category not in {"user","conversation","task","environment"}:raise ValueError("Unsupported memory category")
        self.execute("INSERT INTO memory_metadata VALUES(?,?) ON CONFLICT(record_id) DO UPDATE SET category=excluded.category",(identifier,category))
    def create_record(self,kind,title,content):
        identifier,now=str(uuid4()),utc_now();self.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?)",(identifier,kind,title.strip(),content,"open",now,now));return self.query("SELECT * FROM records WHERE id=?",(identifier,))[0]
    def update_record(self,kind,identifier,changes):
        selected={k:v for k,v in changes.items() if k in {"title","content","status"} and v is not None};selected["updated_at"]=utc_now();columns=", ".join(f"{k}=?" for k in selected);self.execute(f"UPDATE records SET {columns} WHERE kind=? AND id=?",(*selected.values(),kind,identifier));rows=self.query("SELECT * FROM records WHERE kind=? AND id=?",(kind,identifier));return rows[0] if rows else None
    def add_message(self,session,role,content):
        record={"id":str(uuid4()),"session_id":session,"role":role,"content":content,"created_at":utc_now()};self.execute("INSERT INTO messages VALUES(?,?,?,?,?)",tuple(record.values()));return record
    def messages(self,session):return list(reversed(self.query("SELECT * FROM messages WHERE session_id=? ORDER BY rowid DESC LIMIT 100",(session,))))
    def settings(self):
        rows=self.query("SELECT current FROM settings WHERE id=1");return json.loads(rows[0]["current"]) if rows else None
    def settings_rows(self):
        rows=self.query("SELECT current,previous FROM settings WHERE id=1");return rows[0] if rows else None
    def save_settings(self,values):
        current=json.dumps(values,ensure_ascii=False);rows=self.settings_rows();previous=None
        if rows:
            try:json.loads(rows["current"]);previous=rows["current"]
            except (json.JSONDecodeError,TypeError):previous=rows.get("previous")
        self.execute("INSERT INTO settings(id,current,previous) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET previous=excluded.previous,current=excluded.current",(current,previous))
    def replace_settings(self,values,previous=None):self.execute("INSERT INTO settings(id,current,previous) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET previous=excluded.previous,current=excluded.current",(json.dumps(values,ensure_ascii=False),json.dumps(previous,ensure_ascii=False) if previous is not None else None))
    def cleanup(self,retention_days=0):
        if retention_days<=0:return {"messages":0,"research":0,"notifications":0,"briefings":0}
        cutoff=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()-retention_days*86400,timezone.utc).isoformat();return {"messages":self.execute("DELETE FROM messages WHERE created_at<?",(cutoff,)),"research":self.execute("DELETE FROM records WHERE kind='research' AND created_at<?",(cutoff,)),"notifications":self.execute("DELETE FROM notifications WHERE created_at<? AND read=1",(cutoff,)),"briefings":self.execute("DELETE FROM briefings WHERE generated_at<?",(cutoff,))}
    def close(self):
        with self.lock:self.connection.close()
