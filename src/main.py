import sys
import os
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options  import Options
from navigator import Navigator
from core_engine import CoreEngine
from config_manager import ConfigManager
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def create_browser():
    """
    Create and configure undetected Chrome browser.
    
    Returns configured driver instance.
    """
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Platform-specific user data directory
    if sys.platform == "win32":
        user_data_dir = r"C:\Selenium\ChromeProfile"
    else:
        # Linux/Mac - change this path as needed
        user_data_dir = os.path.expanduser("~/.config/google-chrome/selenium_profile")
    
    # Ensure user data dir exists
    os.makedirs(user_data_dir, exist_ok=True)
    
    driver = uc.Chrome(
        options=chrome_options,
        user_data_dir=user_data_dir,
        version_main=146  # Chrome version - change if needed
    )
    
    return driver
def main():
    """Main entry point."""
    print("[*] Starting Aureum automation...")
    
    # Get project root (parent of src/)
    project_root = Path(__file__).parent.parent
    
    # Initialize browser
    print("[*] Initializing browser...")
    driver = create_browser()
    
    # Navigate to game
    print("[*] Navigating to game...")
    driver.get("https://game.granbluefantasy.jp/")
    
    # Create navigator
    navigator = Navigator(driver)
    
    # Create config manager and load defaults
    config = ConfigManager()
    config_path = project_root / "config" / "default.json"
    if config_path.exists():
        config.load_default_config(config_path)
        print(f"[*] Loaded config from {config_path}")
    
    # Create core engine
    engine = CoreEngine(navigator)
    
    # Start raid task
    raid_task_path = project_root / "tasks" / "raid.json"
    if raid_task_path.exists():
        print(f"[*] Starting raid task from {raid_task_path}")
        engine.start_task(raid_task_path)
        print(f"[*] Task thread alive: {engine._task_thread.is_alive()}")
    else:
        print(f"[!] Task file not found: {raid_task_path}")
        driver.quit()
        return
    
    try:
        # Keep main thread alive
        while engine._running:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Interrupted by user")
    finally:
        print("[*] Shutting down...")
        engine.stop()
        driver.quit()
        print("[*] Done")
if __name__ == "__main__":
    main()