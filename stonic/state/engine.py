from stonic.core.models import Activity


class StateEngine:
    _allowed = {
        Activity.INITIALIZING: {Activity.IDLE, Activity.ERROR, Activity.STOPPED},
        Activity.IDLE: {Activity.THINKING, Activity.EXECUTING, Activity.ERROR, Activity.STOPPED},
        Activity.THINKING: {Activity.EXECUTING, Activity.IDLE, Activity.ERROR, Activity.STOPPED},
        Activity.EXECUTING: {Activity.THINKING, Activity.IDLE, Activity.ERROR, Activity.STOPPED},
        Activity.ERROR: {Activity.IDLE, Activity.STOPPED},
        Activity.STOPPED: set(),
    }

    def __init__(self) -> None:
        self.activity = Activity.INITIALIZING

    def transition(self, target: Activity) -> None:
        if target == self.activity:
            return
        if target not in self._allowed[self.activity]:
            raise ValueError(f"Invalid state transition: {self.activity} → {target}")
        self.activity = target
