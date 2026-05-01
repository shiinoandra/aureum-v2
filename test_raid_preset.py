#!/usr/bin/env python3
"""
Standalone test script for raid preset selection on GBF #quest/assist page.

Usage:
    python test_raid_preset.py <raid_id>
    e.g. python test_raid_preset.py 301061

Prerequisites:
    - Chrome with your GBF login session (same profile as Aureum)
    - undetected-chromedriver installed

What it does:
    1. Opens #quest/assist
    2. Reads the 4 preset slot thumbnails
    3. If desired raid_id is already a preset -> clicks it to activate
    4. If not -> opens Settings modal, removes a random preset, adds desired one
    5. Verifies the desired preset is active
"""

import sys
import os
import re
import time
import random

_project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, 'src'))

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException


def create_browser():
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    if sys.platform == "linux":
        chrome_options.add_argument("--ozone-platform=x11")
    user_data_dir = os.path.expanduser("~/.config/google-chrome/selenium_profile")
    os.makedirs(user_data_dir, exist_ok=True)
    driver = uc.Chrome(
        options=chrome_options,
        user_data_dir=user_data_dir,
        version_main=145,
    )
    return driver


def extract_raid_id_from_image_url(url: str) -> str | None:
    """Parse raid ID from image URL like .../lobby/301061.png"""
    if not url:
        return None
    m = re.search(r"/lobby/(\d+)\.png", url)
    if m:
        return m.group(1)
    # Fallback: any trailing number before extension
    m = re.search(r"/(\d+)\.png", url)
    if m:
        return m.group(1)
    return None


def get_preset_slots(driver):
    """Return list of dicts for the 4 preset slots."""
    slots = []
    for i in range(1, 5):
        try:
            # The slot wrapper contains both the image and the click target
            slot = driver.find_element(By.CSS_SELECTOR, f".prt-search-switch-display.slot{i}")
            # Try to find the thumbnail image inside
            try:
                img = slot.find_element(By.CSS_SELECTOR, ".img-quest")
            
                img_url = img.get_attribute("src") or ""
            except NoSuchElementException:
                img_url = ""

            # Check if this slot is currently active
            active = "active" in (slot.get_attribute("class") or "")
            on = "on" in (slot.get_attribute("class") or "")

            slots.append({
                "index": i,
                "element": slot,
                "img_url": img_url,
                "raid_id": extract_raid_id_from_image_url(img_url),
                "is_active": active and on,
            })
        except NoSuchElementException:
            slots.append({
                "index": i,
                "element": None,
                "img_url": "",
                "raid_id": None,
                "is_active": False,
            })
    return slots


def click_preset_slot(driver, slot_element):
    """Click a preset slot to activate it."""
    # Scroll into view
    max_retries = 5
    xpath = "./ancestor::div[contains(@class, 'prt-search-switch-wrapper')]//div[contains(@class, 'btn-search-switch')]"
    for attempt in range(max_retries):
        button = slot_element.find_element(By.XPATH, xpath)
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        # check first (maybe it's already active)
        if "active" in button.get_attribute("class"):
            return True
        button.click()

        try:
            WebDriverWait(driver, 3).until(
                lambda d: "active" in d.find_element(By.XPATH, xpath).get_attribute("class")
            )
            return True  # success after click

        except Exception:
            print(f"Retry {attempt+1} failed...")
            continue



    print("[+] Clicked preset slot")
    # Wait for the page to refresh raid list
    time.sleep(1.5)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#prt-search-list"))
        )
        print("[+] Raid list loaded after preset switch")
    except TimeoutException:
        print("[!] Warning: raid list didn't appear quickly after preset switch")


def open_settings_modal(driver):
    """Click the Settings button to open the preset configuration modal."""
    print("[+] Opening Settings modal...")
    # The button may have class 'btn-search-setting on' or similar
    setting_btn = driver.find_element(By.CSS_SELECTOR, ".btn-search-setting")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", setting_btn)
    time.sleep(0.3)
    setting_btn.click()
    # Wait for modal to appear
    time.sleep(1.0)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".pop-search-setting"))
        )
        print("[+] Settings modal opened")
        return True
    except TimeoutException:
        print("[!] Settings modal did not open")
        return False


def remove_random_preset_in_modal(driver):
    """Inside the settings modal, remove one preset at random."""
    print("[+] Looking for preset remove buttons (X) in modal...")
    # The X buttons may be inside the modal near each preset image
    # Common pattern: .btn-quest-delete or an icon inside the preset slot
    deleted_slot = random.randint(1,4)
    try:
        wrapper = driver.find_element(By.CSS_SELECTOR, f".prt-search-slot-wrapper.slot{str(deleted_slot)}")
        
        try:
            is_currently_empty = wrapper.find_element(By.CSS_SELECTOR, ".txt-empty-slot")
            if is_currently_empty:
                print('the selected slot are empty,  using that slot')
                slot_btn = wrapper.find_element(By.CSS_SELECTOR,".btn-select-search-slot")
                slot_btn.click()
                return True
        except:
            print("the slot is not empty, attempting to delete the preset")
            try:
                release_btn = wrapper.find_element(By.CSS_SELECTOR, ".btn-release")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", release_btn)
                time.sleep(0.3)
                release_btn.click()
                print("[+] Clicked remove button )")
                time.sleep(1.0)
                return True
            except:
                print("failed to click remove button")
                return False    
    except Exception as e:
        print(f"[!] Failed to remove preset: {e}")
        return False


def add_raid_to_preset_in_modal(driver, raid_id: str, difficulty:str,stage_id:str):
    """Inside the settings modal, add the desired raid to an empty preset slot."""
    print(f"[+] Attempting to add raid {raid_id} to a preset slot...")

def click_when_ready(driver, by, selector, timeout=10):

    try:
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, selector))
        )
        element.click()
        print(f"clicked{selector}")
        return True
    except:
        print(f"failed to click{selector}")
        return False


def select_appropriate_raid(driver, raid_id:str,difficulty:str, stage_id:str):
    btn_class_map = {
    "standard": "type1",
    "impossible": "type2",
    "unlimited": "type4"
}

    global navigator
    try:
        # 1. Click difficulty tab
        difficulty_selector = f".btn-stage-type.{btn_class_map.get(difficulty)}"
        click_when_ready(driver, By.CSS_SELECTOR, difficulty_selector)


        # 2. Click stage

        btn_stage = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, f'div[data-stage-id="{stage_id}"].btn-search-stage'))
        )
        navigator.click_element(btn_stage)



        # 3. Wait for raid popup to appear (presence, not clickable)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".pop-usual.pop-search-target-quest.pop-show")
            )
        )

        # 4. Select raid by image keyword
        raid_xpath = f"//div[contains(@class, 'btn-select-quest') and .//img[contains(@src, '{raid_id}')]]"
        click_when_ready(driver, By.XPATH, raid_xpath)

        # 5. Confirm
        click_when_ready(driver, By.CSS_SELECTOR, ".prt-popup-footer .btn-usual-ok")

        return True

    except Exception as e:
        print(f"Error selecting raid: {e}")
        return False





    except NoSuchElementException:
        print("cant match difficulty with the tab button")
        return False


    print("[!] Could not find a way to add the raid. Modal may require manual interaction.")
    return False




def close_settings_modal(driver):
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".pop-search-setting"))
        )
        print("[+] Settings modal opened")
        btn_close = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, f'.pop-search-setting .btn-usual-close'))
        )
        print("[+] Closing settings modal...")
        navigator.click_element(btn_close)
        return True
    except:
        # Fallback: click outside modal or Escape key
        print("[!] No close button found; trying Escape key")
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(1.0)
        return True


def ensure_correct_raid_preset(driver, desired_raid_id: str,difficulty:str,stage_id:str) -> bool:
    """
    Main logic:
      1. Check if desired_raid_id is already in one of 4 presets.
      2. If yes and active -> done.
      3. If yes but not active -> click it.
      4. If no -> open Settings, remove random preset, add desired one.
    """
    print(f"\n=== Ensuring raid preset {desired_raid_id} is active ===\n")

    # Navigate to assist page
    if "#quest/assist" not in driver.current_url:
        print("[+] Navigating to #quest/assist")
        driver.get("https://game.granbluefantasy.jp/#quest/assist")
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-search-switch"))
            )
            print("[+] Raid list page loaded")
        except TimeoutException:
            print("[!] Raid list page did not load in time")
            return False
        time.sleep(2.0)  # Give SPA time to settle

    # Read preset slots
    slots = get_preset_slots(driver)
    print("[+] Current presets:")
    for s in slots:
        status = "ACTIVE" if s["is_active"] else ""
        print(f"    Slot {s['index']}: raid_id={s['raid_id']} {status}")

    # Check if desired raid is already active
    for s in slots:
        if s["raid_id"] == desired_raid_id and s["is_active"]:
            print(f"[+] Desired raid {desired_raid_id} is already active. Nothing to do.")
            return True

    # Check if desired raid exists but is inactive
    for s in slots:
        if s["raid_id"] == desired_raid_id and s["element"] is not None:
            print(f"[+] Desired raid {desired_raid_id} found in slot {s['index']} (inactive). Clicking...")
            if(click_preset_slot(driver, s["element"])):
                return True
            else:
                return False

    # Desired raid not in any preset -> open settings and configure
    print(f"[!] Raid {desired_raid_id} not in any preset. Opening Settings to configure...")
    if not open_settings_modal(driver):
        return False

    # Remove a random preset
    if not remove_random_preset_in_modal(driver):
        print("[!] Could not remove a preset. Dumping modal for manual inspection.")
        return False

    # Add desired raid
    if not select_appropriate_raid(driver, desired_raid_id,difficulty,stage_id):
        print("[!] Could not add desired raid. Dumping modal for manual inspection.")
        return False

    # Close modal
    close_settings_modal(driver)

    # Re-check presets
    time.sleep(2.0)
    slots = get_preset_slots(driver)
    print("[+] Presets after configuration:")
    for s in slots:
        status = "ACTIVE" if s["is_active"] else ""
        print(f"    Slot {s['index']}: raid_id={s['raid_id']} {status}")

    for s in slots:
        if s["raid_id"] == desired_raid_id and s["is_active"]:
            print(f"[+] SUCCESS: Raid {desired_raid_id} is now active.")
            return True

    print(f"[!] FAIL: Raid {desired_raid_id} is still not active after configuration.")
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_raid_preset.py <raid_id>")
        print("Example: python test_raid_preset.py 301061")
        sys.exit(1)

    desired_raid_id = sys.argv[1].strip()
    difficulty=sys.argv[2].strip()
    stage_id = sys.argv[3].strip()
    print(f"[*] Test script starting. Target raid_id: {desired_raid_id} difficulty: {difficulty} stage_id: {stage_id}")

    driver = create_browser()
    from infra.navigator import Navigator
    global navigator 
    navigator = Navigator(driver)
    try:
        ok = ensure_correct_raid_preset(driver, desired_raid_id,difficulty,stage_id)
        if ok:
            print("\n=== TEST PASSED ===")
        else:
            print("\n=== TEST FAILED ===")
        # Keep browser open for inspection
        input("Press Enter to close the browser...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
