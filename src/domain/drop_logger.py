from pathlib import Path


class DropLogger:
    """Stub for DOM-based drop logging.

    Will be implemented based on hihihori3.py's log_raid_results() which parses:
    - .prt-item-list
    - .lis-treasure.btn-treasure-item
    - .img-treasure-item (for image URL + item ID)
    - .prt-article-count (for quantity)

    Usage: called by TaskManager after a successful raid cycle when the browser
    is on a result screen (#result_multi/*).
    """

    def __init__(self):
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

    def capture(self, driver, raid_id: str, raid_name: str):
        """Stub. Will parse result DOM and write to HTML log."""
        print(f"[STUB] DropLogger.capture called for raid {raid_id} ({raid_name})")
        pass
