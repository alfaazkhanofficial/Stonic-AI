import os
import platform
from time import monotonic
from pathlib import Path

import psutil

from stonic.core.models import HealthCheck


class Diagnostics:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.started = monotonic()
        self.llm = HealthCheck(id="llm", name="Intelligence provider", status="unconfigured",
                               detail="Configure a model in Settings → AI & Providers, then test the connection.")
        psutil.cpu_percent()
        # Optional subsystems report themselves here; each returns a HealthCheck or None.
        self.extra_checks: list = []

    def metrics(self) -> dict:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(self.data_dir.resolve().anchor))
        try:
            battery = psutil.sensors_battery()
        except (OSError, FileNotFoundError, RuntimeError):
            battery = None
        return {
            "cpu_percent": psutil.cpu_percent(), "memory_percent": memory.percent,
            "memory_used_gb": round(memory.used / 1024**3, 1),
            "memory_total_gb": round(memory.total / 1024**3, 1),
            "disk_percent": disk.percent, "uptime_seconds": int(monotonic() - self.started),
            "uptime_scope": "Stonic service only, not operating system uptime",
            "platform": platform.system(), "cpu_count": os.cpu_count(),
            "battery_percent": battery.percent if battery else None,
            "battery_present": battery is not None,
        }

    def checks(self) -> list[HealthCheck]:
        return [self.llm, *(check for check in (extra() for extra in self.extra_checks) if check is not None)]
