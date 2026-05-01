class ActionContext:
    """Transient execution envelope. Created fresh per task by TaskManager."""
    RESULT_SUCCESS = "success"
    RESULT_FAILED = "failed"
    RESULT_SKIP = "skip"

    def __init__(self, navigator, global_config, task_config, task_progress, raid_id=None):
        self.navigator = navigator          # shared ref
        self.global_config = global_config  # read-only for actions
        self.task_config = task_config      # read-only for actions
        self.task_progress = task_progress  # actions write progress here
        self.raid_id = raid_id              # FK to raids table for preset matching
        self.battle_finished = False
        self.last_result = None

    def reset_per_raid(self):
        self.battle_finished = False
        self.last_result = None
