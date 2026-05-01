"""
Actions for Aureum automation.

Each action is registered via @ActionRegistry.register decorator.
Actions receive params (from JSON) and context (ActionContext).
"""

import random
import time
from typing import Optional
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException,StaleElementReferenceException

from action.action_context import ActionContext
from action.action_registry import ActionRegistry
from infra.navigator import Navigator


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
    popup = None

    selectors = [
        ".common-pop-error.pop-show",
        ".pop-usual.pop-result-assist-raid.pop-show",
        ".pop-usual.pop-rematch-fail.pop-show",
    ]
    for sel in selectors:
        try:
            popup = nav.driver.find_element(By.CSS_SELECTOR, sel)
            break
        except NoSuchElementException:
            return
            #pass

    # Fallback: generic .pop-usual but with text filter
    # if not popup:
    #     try:
    #         popup = nav.driver.find_element(By.CSS_SELECTOR, ".pop-usual.pop-show")
    #     except NoSuchElementException:
    #         return None


    # Get text
    try:
        popup_text = popup.find_element(By.CSS_SELECTOR, "#popup-body").text.strip()
        
    except StaleElementReferenceException:
        # Popup closed before we could read it — ignore
        return None
    except Exception:
        popup_text = popup.text.strip()

    try:
        popup_header_text = popup.find_element(By.CSS_SELECTOR, ".prt-popup-header").text.strip()
    except:
        popup_header_text = ""

    # Ignore victory/reward popups
    victory_keywords = ["exp", "prestige", "bonus", "items were used", "battle log","event items","exp gained"]
    if (any(k in popup_text.lower() for k in victory_keywords) or any(k in popup_header_text.lower() for k in victory_keywords)):
        return None

    print(f"[!] Popup detected")
    popup_type = _detect_popup_type(popup_text)

    try:
        ok_btn = popup.find_element(By.CSS_SELECTOR, ".btn-usual-ok")
        nav.click_element(ok_btn)
        nav.wait(1.5)
    except Exception:
        print("[!] Could not find OK button to close popup")

    return popup_type


# =============================================================================
# Raid Actions
# =============================================================================


@ActionRegistry.register("select_raid")
def action_select_raid(params, context: ActionContext):
    """
    Select a raid from the list based on HP threshold filter.
    """
    task_config = context.task_config
    nav = context.navigator

    # Navigate to raid list if not already there
    if "https://game.granbluefantasy.jp/#quest/assist" not in nav.get_current_url():
        nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")
        nav.wait_for_element(By.CSS_SELECTOR, "#prt-search-list", timeout=10)

    # Human-like browsing scroll
    _perform_browse_scrolling(nav)

    # Find all visible raid rooms
    raid_rooms = nav.driver.find_elements(
        By.CSS_SELECTOR, "div#prt-search-list div.btn-multi-raid.lis-raid.search"
    )

    if not raid_rooms:
        print("[!] No raids found in list")
        return ActionContext.RESULT_FAILED

    eligible_raids = []

    for raid in raid_rooms:
        try:
            raid_info = {
                "raid_id": raid.get_attribute("data-raid-id"),
                "quest_id": raid.get_attribute("data-quest-id"),
                "name": raid.get_attribute("data-chapter-name") or "",
                "hp_percent": 0.0,
                "players_current": 0,
                "players_max": 0,
                "element": raid,
            }
            # Fallback name
            if not raid_info["name"]:
                try:
                    raid_info["name"] = raid.find_element(
                        By.CSS_SELECTOR, ".txt-raid-name"
                    ).text.strip()
                except:
                    pass

            # HP
            hp_style = raid.find_element(
                By.CSS_SELECTOR, ".prt-raid-gauge-inner"
            ).get_attribute("style")
            raid_info["hp_percent"] = float(hp_style.split("width:")[1].split("%")[0])

            # Player count
            try:
                flees_text = raid.find_element(
                    By.CSS_SELECTOR, ".prt-flees-in"
                ).text.strip()
                current_str, max_str = flees_text.split("/")
                raid_info["players_current"] = int(current_str)
                raid_info["players_max"] = int(max_str)
            except (NoSuchElementException, ValueError, IndexError):
                raid_info["players_current"] = 0
                raid_info["players_max"] = 30

            # HP range
            if not (
                task_config.min_hp_threshold
                <= raid_info["hp_percent"]
                <= task_config.max_hp_threshold
            ):
                continue
            # Player count range
            if not (
                task_config.min_people
                <= raid_info["players_current"]
                <= task_config.max_people
            ):
                continue

            eligible_raids.append(raid_info)

        except (NoSuchElementException, IndexError, ValueError) as e:
            continue

    if not eligible_raids:
        print("[i] No raids met HP threshold. Skipping.")
        return ActionContext.RESULT_FAILED

    # Select random eligible raid
    target = random.choice(eligible_raids)
    print(
        f"[i] Selected raid with {target['hp_percent']}% HP and {target['players_current']} player"
    )

    # Publish raid metadata to task progress
    context.task_progress.current_raid_name = target.get("name", "Unknown Raid")
    context.task_progress.current_raid_id = target.get("raid_id", "")
    context.task_progress.boss_hp_at_entry = target.get("hp_percent", 0.0)

    nav.click_element(target["element"])
    return ActionContext.RESULT_SUCCESS


@ActionRegistry.register("select_summon")
def action_select_summon(params, context: ActionContext):
    """
    Select summon from supporter selection screen.
    Priority order:
    1. Check for auto-summon preset (GBF internal system)
    2. Try each summon in config.summon_priority
    3. Fallback: select first summon in type0 tab
    """
    nav = context.navigator
    summon_list = context.task_config.summon_priority

    # Step 1: Check auto-summon preset
    try:
        WebDriverWait(nav.driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-usual-ok"))
        )
        print("[i] Auto Summon Setting Found - using preset")
        return ActionContext.RESULT_SUCCESS
    except (TimeoutException,StaleElementReferenceException):
        print("[i] Auto Summon not available - searching preferred summons...")

    # Step 2: Try each preferred summon in priority order
    for summon in summon_list:
        name = summon.get("name")
        level = summon.get("level")
        if not name:
            continue
        print(
            f"[i] Searching for summon: {name}"
            + (f" ({level})" if level else " (any level)")
        )
        try:
            if level:
                xpath = f"""
                //div[contains(@class, 'supporter-summon') and
                    .//span[@class='txt-summon-level' and normalize-space(text())='{level}'] and
                    .//span[@class='js-summon-name' and normalize-space(text())='{name}']]
                """
            else:
                xpath = f"""
                //div[contains(@class, 'supporter-summon') and
                    .//span[@class='js-summon-name' and normalize-space(text())='{name}']]
                """
            support_elems = nav.driver.find_elements(By.XPATH, xpath)
            if support_elems:
                tab_btn = _find_support_tab_from_elem(nav, support_elems[0])
                if tab_btn:
                    nav.click_element(tab_btn)
                    nav.wait(0.3, 0.5)
                nav.click_element(support_elems[0])
                print(f"[✓] Selected preferred summon: {name}")
                return ActionContext.RESULT_SUCCESS
        except Exception as e:
            print(f"[!] Error selecting {name}: {e}")
            continue

    # Step 3: Fallback - select first summon in type0 tab
    print("[!] No preferred summons found — using first available summon.")
    try:
        fallback_tab = nav.driver.find_element(
            By.CSS_SELECTOR, ".icon-supporter-type-7"
        )
        nav.click_element(fallback_tab)
        nav.wait(0.3, 0.5)
        first_summon = WebDriverWait(nav.driver, 2).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".prt-supporter-attribute.type0 .btn-supporter")
            )
        )
        nav.click_element(first_summon)
        print("[→] Selected first available summon")
        return ActionContext.RESULT_SUCCESS
    except Exception as e:
        print(f"[!!] Fallback summon selection failed: {e}")
        return ActionContext.RESULT_FAILED


@ActionRegistry.register("join_battle")
def action_join_battle(params, context: ActionContext):
    """Click the quest start button to join battle."""
    nav = context.navigator
    try:
        quest_start_btn = nav.wait_for_clickable(
            By.CSS_SELECTOR, ".btn-usual-ok.se-quest-start", timeout=10
        )
        nav.click_element(quest_start_btn)
        print("[✓] Joined battle")
        return ActionContext.RESULT_SUCCESS
    except (TimeoutException,StaleElementReferenceException):
        print("[!] Quest start button not found")
    return ActionContext.RESULT_FAILED


@ActionRegistry.register("do_battle")
def action_do_battle(params, context: ActionContext):
    nav = context.navigator
    task_config = context.task_config
    fullauto_clicked = 0

    # Pre-battle full auto (one-time, before loop)
    if task_config.pre_fa and fullauto_clicked == 0:
        try:
            pre_fa_elm = WebDriverWait(nav.driver, 2).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".prt-auto-setting")
                )
            )
            if pre_fa_elm:
                nav.click_onthespot()
                fullauto_clicked = 1
        except TimeoutException:
            pass

    # Initial battle UI wait
    try:
        nav.wait_for_element(
            By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=10
        )
    except TimeoutException:
        return ActionContext.RESULT_FAILED

    if task_config.trigger_skip:
        nav.driver.refresh()
        try:
            nav.wait_for_element(
                By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=15
            )
        except TimeoutException:
            return ActionContext.RESULT_FAILED

    current_turn = 1
    battle_ended = False
    click_target = None

    start_time = time.time()
    while time.time() - start_time < 300:
        context.task_progress.current_turn = current_turn

        if (
            "#result_multi/" in nav.get_current_url()
            or "#result/" in nav.get_current_url()
        ):
            print("[→] Battle ended - detected result URL")
            battle_ended = True

        if battle_ended:
            if click_target:
                nav.click_element(click_target)
            context.battle_finished = True
            return ActionContext.RESULT_SUCCESS

        # Turn limit reached?
        if not task_config.until_finish and current_turn > task_config.turn:
            print(f"[→] Turn limit reached ({task_config.turn}).")
            return ActionContext.RESULT_SUCCESS

        # Click full auto if not yet clicked this turn
        if fullauto_clicked == 0:
            try:
                fullauto_btn = nav.wait_for_clickable(
                    By.CSS_SELECTOR, ".btn-auto", timeout=5
                )
                nav.click_element(fullauto_btn)
                nav._move_away(fullauto_btn)
                print("[⚙] Full Auto clicked")
                fullauto_clicked = 1
                nav.wait(0.2, 0.4)
            except TimeoutException:
                print("[!] Full Auto not found, retrying...")
                nav.wait(0.2, 0.3)
                continue

        # Check attack button ON THE SAME PAGE (before refresh)
        try:
            atk_btn = nav.wait_for_element(
                By.CSS_SELECTOR, ".btn-attack-start", timeout=2
            )
            if "display-off" in atk_btn.get_attribute("class"):
                print(f"[i] Turn {current_turn} completed")
                current_turn += 1
                fullauto_clicked = 0
                nav.wait(0.3, 0.5)

                if (
                    not task_config.until_finish
                    and current_turn > task_config.turn
                ):
                    return ActionContext.RESULT_SUCCESS

                nav.driver.refresh()
                if task_config.pre_fa and fullauto_clicked == 0:
                    try:
                        pre_fa_elm = WebDriverWait(nav.driver, 2).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, ".prt-auto-setting")
                            )
                        )
                        if pre_fa_elm:
                            nav.click_onthespot()
                            fullauto_clicked = 1
                    except TimeoutException:
                        pass
                if (
                    "#result_multi/" in nav.get_current_url()
                    or "#result/" in nav.get_current_url()
                ):
                    print("[→] Battle ended - detected result URL")
                    battle_ended = True

                if battle_ended:
                    context.battle_finished = True
                    return ActionContext.RESULT_SUCCESS
                try:
                    nav.wait_for_element(
                        By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=5
                    )
                    print("[✓] Battle UI restored after turn refresh")
                except TimeoutException:
                    print("[×] Battle UI did not return after turn refresh")
                continue
        except TimeoutException:
            pass

        # refresh=true: refresh to skip skill animations
        if task_config.refresh:
            time.sleep(random.uniform(0.1,0.3))
            print("[i] Refreshing to skip skill animations...")
            fullauto_clicked = 0
            nav.driver.refresh()
            if task_config.pre_fa and fullauto_clicked == 0:
                try:
                    pre_fa_elm = WebDriverWait(nav.driver, 2).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, ".prt-auto-setting")
                        )
                    )
                    if pre_fa_elm:
                        nav.click_onthespot()
                        fullauto_clicked = 1
                except TimeoutException:
                    pass
            if (
                "#result_multi/" in nav.get_current_url()
                or "#result/" in nav.get_current_url()
            ):
                print("[→] Battle ended - detected result URL")
                battle_ended = True

            if battle_ended:
                context.battle_finished = True
                return ActionContext.RESULT_SUCCESS
            try:
                nav.wait_for_element(
                    By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=5
                )
                print("[✓] Battle UI restored after animation refresh")
            except TimeoutException:
                print("[×] Battle UI did not return after animation refresh")
            continue

        # refresh=false: let animations play out
        else:
            nav.wait(0.2, 0.3)
            # check A
            if not battle_ended:
                try:
                    result_cnt = nav.driver.find_element(By.CSS_SELECTOR, ".prt-result-cnt")
                    if result_cnt.is_displayed():
                        print("[→] Battle ended - detected result container")
                        battle_ended = True
                except NoSuchElementException:
                    pass

            # check B
            if not battle_ended:
                try:
                    click_target = WebDriverWait(nav.driver, 1).until(
                        EC.element_to_be_clickable(
                            (
                                By.XPATH,
                                "//div[contains(@class, 'pop-exp')]//div[contains(@class, 'btn-usual-ok')]",
                            )
                        )
                    )
                    print("[→] Battle ended - detected victory popup")
                    battle_ended = True
                except TimeoutException:
                    pass

            # check C
            if not battle_ended:
                try:
                    click_target = WebDriverWait(nav.driver, 1).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, ".pop-usual.pop-rematch-fail .btn-usual-ok")
                        )
                    )
                    popup = nav.driver.find_element(
                        By.CSS_SELECTOR, ".pop-usual.pop-rematch-fail"
                    )
                    if "battle has ended" in popup.text.lower():
                        print("[→] Battle ended - detected popup")
                        battle_ended = True
                except TimeoutException:
                    pass

        nav.wait(0.2, 0.3)
        continue

    print("[!] Battle timeout reached")
    return ActionContext.RESULT_FAILED


@ActionRegistry.register("refresh_raid_list")
def action_refresh_raid_list(params, context: ActionContext):
    """Click the raid list refresh button."""
    nav = context.navigator
    print("refreshing raid list")

    if "https://game.granbluefantasy.jp/#quest/assist" not in nav.get_current_url():
        nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")
        nav.wait_for_element(By.CSS_SELECTOR, "#prt-search-list", timeout=10)

    try:
        refresh_btn = nav.wait_for_element(
            By.CSS_SELECTOR, ".btn-search-refresh", timeout=2
        )
        nav.click_element(refresh_btn)
        print("[i] Raid list refreshed")
        return ActionContext.RESULT_SUCCESS
    except TimeoutException:
        print("[!] Refresh button not found")
        return ActionContext.RESULT_FAILED


# ---------------------------------------------------------------------------
# Raid Preset Selection
# ---------------------------------------------------------------------------

_DIFFICULTY_TAB_MAP = {
    "standard": "type1",
    "impossible": "type2",
    "unlimited": "type4",
}


def _extract_raid_id_from_image_url(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"/lobby/(\d+)\.png", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d+)\.png", url)
    if m:
        return m.group(1)
    return None


@ActionRegistry.register("ensure_raid_preset")
def action_ensure_raid_preset(params, context: ActionContext):
    """
    Ensure the desired raid is active in one of the 4 preset slots on #quest/assist.

    Flow:
      1. Read the 4 preset slots.
      2. If desired raid is already active -> success.
      3. If desired raid is present but inactive -> click it.
      4. If not present -> open Settings modal, clear a random slot,
         navigate difficulty tab -> stage -> raid image -> OK, close modal.
      5. Verify desired raid is now active.
    """
    nav = context.navigator
    raid_id = context.raid_id
    stage_id = context.task_config.stage_id
    difficulty = context.task_config.difficulty

    # Fallback: query DB if config fields are missing
    if not raid_id or not stage_id or not difficulty:
        from infra.database import get_raid_by_id
        db_raid = get_raid_by_id(raid_id) if raid_id else None
        if db_raid:
            stage_id = stage_id or db_raid.get("stage_id")
            difficulty = difficulty or db_raid.get("difficulty")

    if not raid_id:
        print("[!] ensure_raid_preset: no raid_id available")
        return ActionContext.RESULT_FAILED

    print(f"[i] Ensuring raid preset {raid_id} is active (difficulty={difficulty}, stage={stage_id})")

    # --- Navigate to assist page ---
    if "#quest/assist" not in nav.get_current_url():
        nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")
    try:
        nav.wait_for_element(By.CSS_SELECTOR, ".btn-search-switch", timeout=15)
    except TimeoutException:
        print("[!] Raid list page did not load")
        return ActionContext.RESULT_FAILED
    nav.wait(1.5, 2.5)

    # --- Helper: read preset slots ---
    def _read_slots():
        slots = []
        for i in range(1, 5):
            try:
                display = nav.driver.find_element(By.CSS_SELECTOR, f".prt-search-switch-display.slot{i}")
                try:
                    img = display.find_element(By.CSS_SELECTOR, ".img-quest")
                    img_url = img.get_attribute("src") or ""
                except NoSuchElementException:
                    img_url = ""
                cls = display.get_attribute("class") or ""
                slots.append({
                    "index": i,
                    "display": display,
                    "raid_id": _extract_raid_id_from_image_url(img_url),
                    "is_active": "active" in cls and "on" in cls,
                })
            except NoSuchElementException:
                slots.append({"index": i, "display": None, "raid_id": None, "is_active": False})
        return slots

    slots = _read_slots()
    for s in slots:
        status = "ACTIVE" if s["is_active"] else ""
        print(f"    Slot {s['index']}: raid_id={s['raid_id']} {status}")

    # Already active?
    for s in slots:
        if s["raid_id"] == raid_id and s["is_active"]:
            print(f"[+] Raid {raid_id} is already active")
            return ActionContext.RESULT_SUCCESS

    # Present but inactive -> click it
    for s in slots:
        if s["raid_id"] == raid_id and s["display"] is not None:
            print(f"[+] Raid {raid_id} found in slot {s['index']} (inactive). Clicking...")
            try:
                btn = s["display"].find_element(
                    By.XPATH, "./ancestor::div[contains(@class, 'prt-search-switch-wrapper')]//div[contains(@class, 'btn-search-switch')]"
                )
                if "active" in (btn.get_attribute("class") or ""):
                    return ActionContext.RESULT_SUCCESS
                nav.click_element(btn)
                nav.wait(1.5, 2.5)
                # Verify
                slots_after = _read_slots()
                for sa in slots_after:
                    if sa["raid_id"] == raid_id and sa["is_active"]:
                        print(f"[+] Raid {raid_id} is now active")
                        return ActionContext.RESULT_SUCCESS
                print("[!] Clicked preset but raid did not become active")
                return ActionContext.RESULT_FAILED
            except Exception as e:
                print(f"[!] Failed to click preset slot: {e}")
                return ActionContext.RESULT_FAILED

    # --- Not in any preset -> open Settings modal ---
    print(f"[!] Raid {raid_id} not in presets. Opening Settings...")
    try:
        setting_btn = nav.driver.find_element(By.CSS_SELECTOR, ".btn-search-setting")
        nav.click_element(setting_btn)
        nav.wait(1.0, 1.5)
        nav.wait_for_element(By.CSS_SELECTOR, ".pop-search-setting", timeout=10)
        print("[+] Settings modal opened")
    except Exception as e:
        print(f"[!] Failed to open settings modal: {e}")
        return ActionContext.RESULT_FAILED

    # --- Remove a random preset ---
    removed = False
    for attempt in range(4):
        target_slot = random.randint(1, 4)
        try:
            wrapper = nav.driver.find_element(By.CSS_SELECTOR, f".prt-search-slot-wrapper.slot{target_slot}")
            # Check if slot is already empty
            try:
                wrapper.find_element(By.CSS_SELECTOR, ".txt-empty-slot")
                print(f"[+] Slot {target_slot} is already empty")
                slot_btn = wrapper.find_element(By.CSS_SELECTOR, ".btn-select-search-slot")
                nav.click_element(slot_btn)
                removed = True
                break
            except NoSuchElementException:
                pass
            # Release existing preset
            release_btn = wrapper.find_element(By.CSS_SELECTOR, ".btn-release")
            nav.click_element(release_btn)
            print(f"[+] Released preset in slot {target_slot}")
            nav.wait(1.0, 1.5)
            removed = True
            break
        except Exception as e:
            print(f"[!] Could not clear slot {target_slot}: {e}")
            continue

    if not removed:
        print("[!] Failed to clear any preset slot")
        return ActionContext.RESULT_FAILED

    # --- Select appropriate raid in modal ---
    tab_class = _DIFFICULTY_TAB_MAP.get((difficulty or "").lower())
    if not tab_class:
        print(f"[!] Unknown difficulty '{difficulty}' for preset modal")
        return ActionContext.RESULT_FAILED

    try:
        # 1. Click difficulty tab
        tab_btn = nav.wait_for_clickable(By.CSS_SELECTOR, f".btn-stage-type.{tab_class}", timeout=10)
        nav.click_element(tab_btn)
        nav.wait(0.5, 1.0)

        # 2. Click stage
        stage_btn = nav.wait_for_clickable(
            By.CSS_SELECTOR, f'div[data-stage-id="{stage_id}"].btn-search-stage', timeout=10
        )
        nav.click_element(stage_btn)
        nav.wait(0.5, 1.0)

        # 3. Wait for raid popup
        nav.wait_for_element(By.CSS_SELECTOR, ".pop-usual.pop-search-target-quest.pop-show", timeout=10)

        # 4. Select raid by image keyword
        raid_xpath = f"//div[contains(@class, 'btn-select-quest') and .//img[contains(@src, '{raid_id}')]]"
        raid_btn = nav.wait_for_clickable(By.XPATH, raid_xpath, timeout=10)
        nav.click_element(raid_btn)
        nav.wait(0.5, 1.0)

        # 5. Confirm
        ok_btn = nav.wait_for_clickable(By.CSS_SELECTOR, ".prt-popup-footer .btn-usual-ok", timeout=10)
        nav.click_element(ok_btn)
        nav.wait(1.0, 1.5)
        print(f"[+] Selected raid {raid_id} in modal")
    except Exception as e:
        print(f"[!] Failed to select raid in modal: {e}")
        return ActionContext.RESULT_FAILED

    # --- Close modal ---
    try:
        close_btn = nav.wait_for_clickable(By.CSS_SELECTOR, ".pop-search-setting .btn-usual-close", timeout=10)
        nav.click_element(close_btn)
        nav.wait(1.5, 2.5)
        print("[+] Settings modal closed")
    except Exception as e:
        print(f"[!] Failed to close settings modal: {e}")
        # Try Escape as fallback
        from selenium.webdriver.common.keys import Keys
        nav.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        nav.wait(1.0, 1.5)

    # --- Verify ---
    slots = _read_slots()
    for s in slots:
        if s["raid_id"] == raid_id and s["is_active"]:
            print(f"[+] SUCCESS: Raid {raid_id} is now active")
            return ActionContext.RESULT_SUCCESS

    print(f"[!] FAIL: Raid {raid_id} is still not active after configuration")
    return ActionContext.RESULT_FAILED


@ActionRegistry.register("clean_raid_queue")
def action_clean_raid_queue(params, context: ActionContext):
    """Process and clear pending raids from unclaimed list."""
    nav = context.navigator
    nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")

    try:
        pending_btn = nav.wait_for_element(
            By.CSS_SELECTOR, ".btn-unconfirmed-result", timeout=2
        )
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

            raid = raids[random.randint(0, len(raids) - 1)]
            raid_id = raid.get_attribute("data-raid-id")
            print(f"[i] Processing pending raid {raid_id}")
            nav.click_element(raid)

            try:
                ok_btn = nav.wait_for_element(
                    By.CSS_SELECTOR, ".btn-usual-ok", timeout=2
                )
                time.sleep(random.uniform(0.2, 0.3))
                if random.uniform(0, 1) > 0.5:
                    nav.click_element(ok_btn)
                nav.wait(0.5)
            except:
                pass

            nav.driver.get(
                "https://game.granbluefantasy.jp/#quest/assist/unclaimed/0/0"
            )
            nav.wait_for_element(
                By.CSS_SELECTOR,
                "#prt-unclaimed-list .btn-multi-raid.lis-raid",
                timeout=2,
            )

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
    """Navigate to the raid list page."""
    nav = context.navigator
    nav.driver.get("https://game.granbluefantasy.jp/#quest/assist")
    nav.wait_for_element(By.CSS_SELECTOR, "#prt-search-list", timeout=10)
    print("[i] Arrived at raid list")
    return ActionContext.RESULT_SUCCESS


@ActionRegistry.register("go_to_main_menu")
def action_go_to_main_menu(params, context: ActionContext):
    """Navigate to main menu (mypage)."""
    nav = context.navigator
    nav.driver.get("https://game.granbluefantasy.jp/#mypage/")
    nav.wait(1, 2)
    print("[i] Arrived at main menu")
    return ActionContext.RESULT_SUCCESS


@ActionRegistry.register("go_to_url")
def action_go_to_url(params, context: ActionContext):
    """Navigate to an arbitrary URL. Used by quests and events."""
    nav = context.navigator
    url = params.get("url", "")
    if url:
        nav.driver.get(url)
        print(f"[i] Navigated to {url}")
        time.sleep(0.5)
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


def _find_support_tab_from_elem(nav: Navigator, support_elem):
    """
    Given a supporter summon element, find its corresponding tab button.
    Returns the tab element, or None if not found.
    """
    try:
        container = support_elem.find_element(
            By.XPATH, "./ancestor::div[contains(@class, 'prt-supporter-attribute')]"
        )
        class_attr = container.get_attribute("class")
        match = re.search(r"type(\d+)", class_attr)
        if not match:
            print(f"[!] Could not detect type class from: {class_attr}")
            return None

        support_type = int(match.group(1))
        type_map = {0: 7, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}
        tab_index = type_map.get(support_type)
        if tab_index is None:
            print(f"[!] No matching tab for type {support_type}")
            return None

        print(f"[i] Support type{support_type} → tab button type-{tab_index}")
        tab_selector = f".icon-supporter-type-{tab_index}"
        return nav.driver.find_element(By.CSS_SELECTOR, tab_selector)
    except Exception as e:
        print(f"[!] Error finding support tab: {e}")
        return None
