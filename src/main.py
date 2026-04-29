import sys
import os
import undetected_chromedriver as uc
from pathlib import Path
import json
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from infra.navigator import Navigator
from runtime.runtime_manager import RuntimeManager
from task.task import Task, TaskConfig


def create_browser():
    """Create and configure undetected Chrome browser."""
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    if sys.platform == "win32":
        user_data_dir = r"C:\Selenium\ChromeProfile"
    else:
        user_data_dir = os.path.expanduser("~/.config/google-chrome/selenium_profile")
        if sys.platform == "linux":
            chrome_options.add_argument("--ozone-platform=x11")

    os.makedirs(user_data_dir, exist_ok=True)

    driver = uc.Chrome(
        options=chrome_options,
        user_data_dir=user_data_dir,
        version_main=145
    )

    return driver


def main():
    """Main entry point."""
    print("[*] Starting Aureum automation...")

    project_root = Path(__file__).parent.parent

    # Initialize browser
    print("[*] Initializing browser...")
    driver = create_browser()

    # Navigate to game
    print("[*] Navigating to game...")
    driver.get("https://game.granbluefantasy.jp/")

    # Create navigator
    navigator = Navigator(driver)

    # Create runtime manager
    runtime = RuntimeManager(navigator)

    # Load default task config from raid.json
    raid_task_path = project_root / "tasks" / "raid.json"
    default_task_config = TaskConfig()
    if raid_task_path.exists():
        with open(raid_task_path) as f:
            task_def = json.load(f)
        default_task_config = TaskConfig.from_dict(task_def.get("task_config", {}))
        print(f"[*] Loaded default task config from {raid_task_path}")

    # Build and enqueue raid task
    if raid_task_path.exists():
        with open(raid_task_path) as f:
            task_def = json.load(f)

        task = Task(
            task_id=str(uuid.uuid4())[:8],
            task_type="raid",
            task_config=default_task_config,
            actions=task_def.get("actions", []),
            exit_condition=task_def.get("exit_condition", {"type": "raid_count", "value": 10}),
        )
        runtime.enqueue_task(task)
        runtime.start()
        print(f"[*] Started raid task")
    else:
        print(f"[!] Task file not found: {raid_task_path}")
        driver.quit()
        return

    try:
        # Keep main thread alive
        while runtime.is_running:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Interrupted by user")
    finally:
        print("[*] Shutting down...")
        runtime.stop()
        driver.quit()
        print("[*] Done")


if __name__ == "__main__":
    main()
