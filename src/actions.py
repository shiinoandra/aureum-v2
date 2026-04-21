"""
Actions for Aureum automation.

Each action is registered via @ActionRegistry.register decorator.
Actions receive params (from JSON) and context (ActionContext).
"""

import random
import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from context import ActionContext,ActionRegistry
from navigator import Navigator
from config_manager import ConfigManager


# =============================================================================
# Popup Handling (Internal Helpers)
# =============================================================================

def _detect_popup_type(popup_text: str) -> str:
    """Detect popup type from text content."""
    text_lower = popup_text.lower()

    if any(k in text_lower for k in ["verification", "verify", "captcha"]):
        return "captcha"
    elif "This raid battle is full" in popup_text:
        return "raid_full"
    elif "not enough AP" in text_lower:
        return "not_enough_ap"
    elif "only provide backup in up to three raid battles" in popup_text:
        return "three_raid"
    elif "Check your pending battles" in popup_text:
        return "toomuch_pending"
    elif "has already ended" in popup_text:
        return "ended"
    else:
        return "unknown_popup"


def _check_and_handle_popup(nav: Navigator) -> Optional[str]:
    """
    Check for popup and handle it if present.
    Returns popup type if popup was shown, None otherwise.
    """
    try:
        popup = nav.driver.find_element(By.CSS_SELECTOR, ".common-pop-error.pop-show")
        popup_text = popup.find_element(By.CSS_SELECTOR, "#popup-body").text.strip()
        print(f"[!] Popup detected: '{popup_text}'")

        popup_type = _detect_popup_type(popup_text)

        try:
            ok_btn = popup.find_element(By.CSS_SELECTOR, ".btn-usual-ok")
            nav.click_element(ok_btn)
            nav.wait(1.5)
        except Exception:
            print("[!] Could not find OK button to close popup")

        return popup_type
    except:
        return None


# =============================================================================
# Raid Actions
# =============================================================================

@ActionRegistry.register("select_raid")
def action_select_raid(params, context: ActionContext):
    """
    Select a raid from the list based on HP threshold filter.

    Params:
        - filter: "prefer_Lv100" (filters raids with HP >= 60%)
    """
    nav = context.navigator

    # Navigate to raid list if not already there
    if "https://game.granbluefantasy.jp/#quest/assist" not in nav.get_current_url():
        nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")
        nav.wait_for_element(By.CSS_SELECTOR, "#prt-search-list", timeout=10)

    # Check for popups
    # Human-like browsing scroll
    _perform_browse_scrolling(nav)

    # Find all visible raid rooms
    raid_rooms = nav.driver.find_elements(
        By.CSS_SELECTOR, "div#prt-search-list div.btn-multi-raid.lis-raid.search"
    )

    if not raid_rooms:
        print("[!] No raids found in list")
        return ActionContext.RESULT_FAILED

    # Filter by HP threshold
    HP_THRESHOLD = 60
    eligible_raids = []

    for raid in raid_rooms:
        try:
            hp_style = raid.find_element(By.CSS_SELECTOR, ".prt-raid-gauge-inner").get_attribute("style")
            hp_percent = float(hp_style.split("width:")[1].split("%")[0])

            if hp_percent >= HP_THRESHOLD:
                eligible_raids.append({"hp": hp_percent, "element": raid})
        except (NoSuchElementException, IndexError, ValueError):
            continue

    if not eligible_raids:
        print("[i] No raids met HP threshold. Skipping.")
        return ActionContext.RESULT_FAILED

    # Select random eligible raid
    target = random.choice(eligible_raids)
    print(f"[i] Selected raid with {target['hp']}% HP")
    nav.click_element(target["element"])
    return ActionContext.RESULT_SUCCESS



@ActionRegistry.register("select_summon")
def action_select_summon(params, context: ActionContext):
    """
    Select summon from supporter selection screen.

    Params:
        - filter: "element_fire", "element_earth", etc. (optional, for future use)
    """
    nav = context.navigator

    try:
        WebDriverWait(nav.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-usual-ok"))
        )
        print("[i] Auto Summon Setting Found - using preset")
        return ActionContext.RESULT_SUCCESS
    except TimeoutException:
        pass
        
    return ActionContext.RESULT_FAILED


    # TODO: Implement element-based summon selection if needed
    # For now, assume auto-summon preset is configured in-game


@ActionRegistry.register("join_battle")
def action_join_battle(params, context: ActionContext):
    """
    Click the quest start button to join battle.
    """
    nav = context.navigator

    try:
        quest_start_btn = nav.wait_for_clickable(
            By.CSS_SELECTOR, ".btn-usual-ok.se-quest-start", timeout=10
        )
        nav.click_element(quest_start_btn)
        print("[✓] Joined battle")
        return ActionContext.RESULT_SUCCESS
    except TimeoutException:
        print("[!] Quest start button not found")
    return ActionContext.RESULT_FAILED

@ActionRegistry.register("do_battle")
def action_do_battle(params, context: ActionContext):
    nav = context.navigator
    config = context.config
    battle_config = config.get_battle_config()
    
    # Initial battle UI wait
    try:
        nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=7)
    except TimeoutException:
        return ActionContext.RESULT_FAILED
    
    if battle_config.trigger_skip:
        nav.driver.refresh()
        try:
            nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=10)
        except TimeoutException:
            return ActionContext.RESULT_FAILED
    
    current_turn = 1
    fullauto_clicked = 0
    
    start_time = time.time()
    while time.time() - start_time < 300:
        battle_ended = False
        click_target = None

        # Method A: URL navigated to result page
        current_url = nav.get_current_url()
        print("checking method A")
        if "#result_multi" in current_url or "#result/" in current_url:
            print("inside method A if")
            print("[→] Battle ended - detected result URL")
            battle_ended = True
            try:
                click_target = nav.driver.find_element(By.CSS_SELECTOR, ".prt-result-cnt .btn-usual-ok")
            except NoSuchElementException:
                pass
        
        print("checking method B")
        if not battle_ended:
            print("inside method B if")
            try:
                result_cnt = nav.driver.find_element(By.CSS_SELECTOR, ".prt-result-cnt")
                if result_cnt.is_displayed():
                    print("[→] Battle ended - detected result container")
                    battle_ended = True
                    try:
                        click_target = result_cnt.find_element(By.CSS_SELECTOR, ".btn-usual-ok")
                    except NoSuchElementException:
                        pass
            except NoSuchElementException:
                pass
        
        # Method C: Victory popup (fallback)

        print("checking method C")
        if not battle_ended:
            print("inside method C if")
            try:
                click_target = WebDriverWait(nav.driver, 1).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//div[contains(@class, 'pop-exp')]//div[contains(@class, 'btn-usual-ok')]"
                    ))
                )
                print("[→] Battle ended - detected victory popup")
                battle_ended = True
            except TimeoutException:
                pass

        # Method D: "Battle has ended" popup (edge case before full auto click)
        print("checking method D")
        if not battle_ended:
            print("inside method D if")
            try:
                ended_popup = nav.driver.find_element(By.CSS_SELECTOR, "pop.rematch")
                print("[→] Battle ended - detected 'battle has ended' popup")
                battle_ended = True
                try:
                    click_target = ended_popup.find_element(By.CSS_SELECTOR, ".btn-usual-ok")
                    nav.click_element(click_target)
                except NoSuchElementException:
                    pass
            except NoSuchElementException:
                pass
        
        if battle_ended:
            if click_target:
                nav.click_element(click_target)
            context.raids_completed += 1
            context.battle_finished = True
            print(f"[→] Battle finished. Raids completed: {context.raids_completed}")
            return ActionContext.RESULT_SUCCESS
        
        # === 2. Turn limit reached? ===
        if not battle_config.until_finish and current_turn > battle_config.turn:
            context.raids_completed += 1
            print(f"[→] Turn limit reached ({battle_config.turn}). Raids completed: {context.raids_completed}")
            return ActionContext.RESULT_SUCCESS
        
        # === 3. Was attack auto-triggered while we were refreshing? ===
        try:
            atk_btn = nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start", timeout=5)
            if "display-off" in atk_btn.get_attribute("class"):
                print(f"[i] Turn {current_turn} completed")
                current_turn += 1
                fullauto_clicked = 0
                nav.wait(0.3, 0.5)
                
                # Refresh to skip attack animation / reset UI for next turn
                nav.driver.refresh()
                continue
        except TimeoutException:
            nav.wait(0.3, 0.5)
            pass
        
        # === 4. Click full auto if not yet clicked ===
        if fullauto_clicked == 0:
            try:
                fullauto_btn = nav.wait_for_clickable(By.CSS_SELECTOR, ".btn-auto", timeout=5)
                nav.click_element(fullauto_btn)
                nav._move_away(fullauto_btn)
                print("[⚙] Full Auto clicked")
                fullauto_clicked = 1
                nav.wait(0.2, 0.4)
            except TimeoutException:
                # Might be battle ended or page loading. Let loop check popup again.
                print("[!] Full Auto not found, retrying...")
                nav.wait(0.5, 1.0)
                continue
        
        # === 5. refresh=true: refresh to skip skill animations ===
        if battle_config.refresh:
            print("[i] Refreshing to skip skill animations...")
            fullauto_clicked = 0  # Page will reload, need to click again
            nav.driver.refresh()
            continue
        
        # === 6. refresh=false: let animations play out ===
        else:
            nav.wait(0.5, 1.0)
            continue



@ActionRegistry.register("refresh_raid_list")
def action_refresh_raid_list(params, context: ActionContext):
    """
    Click the raid list refresh button.
    """
    nav = context.navigator
    print("refreshing raid list")

    if "https://game.granbluefantasy.jp/#quest/assist" not in nav.get_current_url():
        nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")
        nav.wait_for_element(By.CSS_SELECTOR, "#prt-search-list", timeout=10)

    try:
        refresh_btn = nav.wait_for_element(By.CSS_SELECTOR, ".btn-search-refresh", timeout=2)
        nav.click_element(refresh_btn)
        print("[i] Raid list refreshed")
        return ActionContext.RESULT_SUCCESS
    except TimeoutException:
        print("[!] Refresh button not found")
        return ActionContext.RESULT_FAILED


@ActionRegistry.register("clean_raid_queue")
def action_clean_raid_queue(params, context: ActionContext):
    """
    Process and clear pending raids from unclaimed list.
    """
    nav = context.navigator

    nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")

    try:
        pending_btn = nav.wait_for_element(By.CSS_SELECTOR, ".btn-unconfirmed-result", timeout=2)
        nav.click_element(pending_btn)
        nav.wait_for_element(By.ID, "prt-unclaimed-list", timeout=5)

        while True:
            nav.wait(1.5)
            raids = nav.driver.find_elements(
                By.CSS_SELECTOR, "#prt-unclaimed-list .btn-multi-raid.lis-raid"
            )

            if not raids:
                print("[✓] No more pending raids")
                break

            # Select first raid in list
            raid = raids[random.randint(0,len(raids)-1)]
            raid_id = raid.get_attribute("data-raid-id")
            print(f"[i] Processing pending raid {raid_id}")
            nav.click_element(raid)

            # Claim its rewards
            try:
                ok_btn = nav.wait_for_element(By.CSS_SELECTOR, ".btn-usual-ok", timeout=2)
                time.sleep(random.uniform(0.2,0.3))
                if(random.uniform(0,1)>0.5):
                    nav.click_element(ok_btn)
                nav.wait(0.5)
            except:
                pass

            # Go back to unclaimed list
            nav.driver.back()
            nav.wait_for_element(By.CSS_SELECTOR, "#prt-unclaimed-list .btn-multi-raid.lis-raid", timeout=2)

        print("[✓] Raid queue cleaned")
        nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")
        return ActionContext.RESULT_SUCCESS
        

    except TimeoutException:
        print("[i] No pending battles button found")
        nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")
        return ActionContext.RESULT_SUCCESS

    except Exception as e:
        print(f"[!!] Error cleaning raid queue: {e}")
        return ActionContext.RESULT_FAILED



@ActionRegistry.register("go_to_raid_list")
def action_go_to_raid_list(params, context: ActionContext):
    """
    Navigate to the raid list page.
    """
    nav = context.navigator
    nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")
    nav.wait_for_element(By.CSS_SELECTOR, "#prt-search-list", timeout=10)
    print("[i] Arrived at raid list")
    return ActionContext.RESULT_SUCCESS


@ActionRegistry.register("go_to_main_menu")
def action_go_to_main_menu(params, context: ActionContext):
    """
    Navigate to main menu (mypage).
    """
    nav = context.navigator
    nav.driver.get("https://game.granbluefantasy.jp/#mypage/")
    nav.wait(1, 2)
    print("[i] Arrived at main menu")
    return ActionContext.RESULT_SUCCESS


# =============================================================================
# Internal Helpers
# =============================================================================

def _perform_browse_scrolling(nav: Navigator):
    """Human-like browsing scroll behavior."""
    from selenium.webdriver.common.action_chains import ActionChains

    if random.random() < 0.6:
        actions = ActionChains(nav.driver)
        num_scrolls = random.randint(2, 5)

        for _ in range(num_scrolls):
            delta = random.randint(100, 300)
            if random.random() < 0.4:
                delta *= -1
            actions.scroll_by_amount(0, delta).perform()
            time.sleep(random.uniform(0.4, 1.2))

        actions.scroll_by_amount(0, -random.randint(300, 800)).perform()
        time.sleep(random.uniform(0.4, 1.0))
    return ActionContext.RESULT_SUCCESS
