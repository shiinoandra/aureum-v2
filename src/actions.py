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
            pass
    
    # Fallback: generic .pop-usual but with text filter
    if not popup:
        try:
            popup = nav.driver.find_element(By.CSS_SELECTOR, ".pop-usual.pop-show")
        except NoSuchElementException:
            return None
    
    # Get text
    try:
        popup_text = popup.find_element(By.CSS_SELECTOR, "#popup-body").text.strip()
    except:
        popup_text = popup.text.strip()
    
    # Ignore victory/reward popups
    victory_keywords = ["exp", "loot collected", "rupies collected", 
                        "items were used", "battle log"]
    if any(k in popup_text.lower() for k in victory_keywords):
        return None
    
    print(f"[!] Popup detected: '{popup_text}'")
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
    HP_THRESHOLD = 20
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
    Priority order:
    1. Check for auto-summon preset (GBF internal system)
    2. Try each summon in config.summon_priority (first → last)
       - Supports optional 'level' (exact match if provided, any level if omitted/null)
    3. Fallback: select first summon in type0 tab
    """
    nav = context.navigator
    config = context.config.get_battle_config()
    summon_list = config.summon_priority
    # Step 1: Check auto-summon preset
    try:
        WebDriverWait(nav.driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-usual-ok"))
        )
        print("[i] Auto Summon Setting Found - using preset")
        return ActionContext.RESULT_SUCCESS
    except TimeoutException:
        print("[i] Auto Summon not available - searching preferred summons...")
    # Step 2: Try each preferred summon in priority order
    for summon in summon_list:
        name = summon.get("name")
        level = summon.get("level")
        if not name:
            continue
        print(f"[i] Searching for summon: {name}" + (f" ({level})" if level else " (any level)"))
        try:
            # Build XPath based on whether level is specified
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
        fallback_tab = nav.driver.find_element(By.CSS_SELECTOR, ".icon-supporter-type-7")
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

# @ActionRegistry.register("do_battle")
# def action_do_battle(params, context: ActionContext):
#     nav = context.navigator
#     config = context.config
#     battle_config = config.get_battle_config()
    
#     if battle_config.pre_fa:
#         nav.click_onthespot()
#         fullauto_clicked=1
    
#     # Initial battle UI wait
#     try:
#         nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=7)
#     except TimeoutException:
#         return ActionContext.RESULT_FAILED
    
#     if battle_config.trigger_skip:
#         nav.driver.refresh()
#         try:
#             nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=10)
#         except TimeoutException:
#             return ActionContext.RESULT_FAILED
    
#     current_turn = 1
#     fullauto_clicked = 0
    
#     start_time = time.time()
#     while time.time() - start_time < 300:
#         battle_ended = False
#         click_target = None

#         if battle_config.pre_fa:
#             nav.click_onthespot()
#             fullauto_clicked=1
        

#         # Method A: URL navigated to result page
#         current_url = nav.get_current_url()
#         if "#result_multi" in current_url or "#result/" in current_url:
#             print("[→] Battle ended - detected result URL")
#             battle_ended = True
#             try:
#                 click_target = nav.driver.find_element(By.CSS_SELECTOR, ".prt-result-cnt .btn-usual-ok")
#             except NoSuchElementException:
#                 pass
        
#         if not battle_ended:
#             try:
#                 result_cnt = nav.driver.find_element(By.CSS_SELECTOR, ".prt-result-cnt")
#                 if result_cnt.is_displayed():
#                     print("[→] Battle ended - detected result container")
#                     battle_ended = True
#                     try:
#                         click_target = result_cnt.find_element(By.CSS_SELECTOR, ".btn-usual-ok")
#                     except NoSuchElementException:
#                         pass
#             except NoSuchElementException:
#                 pass
        
#         # Method C: Victory popup (fallback)

#         if not battle_ended:
#             try:
#                 click_target = WebDriverWait(nav.driver, 1).until(
#                     EC.element_to_be_clickable((
#                         By.XPATH,
#                         "//div[contains(@class, 'pop-exp')]//div[contains(@class, 'btn-usual-ok')]"
#                     ))
#                 )
#                 print("[→] Battle ended - detected victory popup")
#                 battle_ended = True
#             except TimeoutException:
#                 pass

#         # Method D: "Battle has ended" popup (edge case before full auto click)
#         if not battle_ended:
#             try:
#                 click_target = WebDriverWait(nav.driver, 1.5).until(
#                     EC.element_to_be_clickable((
#                         By.CSS_SELECTOR,
#                         ".pop-usual.pop-rematch-fail .btn-usual-ok"
#                     ))
#                 )

#                 popup = nav.driver.find_element(
#                     By.CSS_SELECTOR,
#                     ".pop-usual.pop-rematch-fail"
#                 )

#                 if "battle has ended" in popup.text.lower():
#                     print("[→] Battle ended - detected popup")
#                     battle_ended = True

#                     click_target.click()  # don't forget to actually click

#             except TimeoutException:
#                 pass
                
#         if battle_ended:
#             if click_target:
#                 nav.click_element(click_target)
#             context.raids_completed += 1
#             context.battle_finished = True
#             print(f"[→] Battle finished. Raids completed: {context.raids_completed}")
#             return ActionContext.RESULT_SUCCESS
        
#         # === 2. Turn limit reached? ===
#         if not battle_config.until_finish and current_turn > battle_config.turn:
#             context.raids_completed += 1
#             print(f"[→] Turn limit reached ({battle_config.turn}). Raids completed: {context.raids_completed}")
#             return ActionContext.RESULT_SUCCESS
        
#         # === 3. Was attack auto-triggered while we were refreshing? ===
#         try:
#             atk_btn = nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start", timeout=5)
#             if "display-off" in atk_btn.get_attribute("class"):
#                 print(f"[i] Turn {current_turn} completed")
#                 current_turn += 1
#                 fullauto_clicked = 0
#                 nav.wait(0.3, 0.5)
                
#                 # Refresh to skip attack animation / reset UI for next turn
#                 nav.driver.refresh()
#                 continue
#         except TimeoutException:
#             nav.wait(0.3, 0.5)
#             pass
        
#         # === 4. Click full auto if not yet clicked ===
#         if fullauto_clicked == 0:
#             try:
#                 fullauto_btn = nav.wait_for_clickable(By.CSS_SELECTOR, ".btn-auto", timeout=5)
#                 nav.click_element(fullauto_btn)
#                 nav._move_away(fullauto_btn)
#                 print("[⚙] Full Auto clicked")
#                 fullauto_clicked = 1
#                 nav.wait(0.2, 0.4)
#             except TimeoutException:
#                 # Might be battle ended or page loading. Let loop check popup again.
#                 print("[!] Full Auto not found, retrying...")
#                 nav.wait(0.5, 1.0)
#                 continue
        
#         # === 5. refresh=true: refresh to skip skill animations ===
#         if battle_config.refresh:
#             print("[i] Refreshing to skip skill animations...")
#             fullauto_clicked = 0  # Page will reload, need to click again
#             nav.driver.refresh()
#             continue
        
#         # === 6. refresh=false: let animations play out ===
#         else:
#             nav.wait(0.5, 1.0)
#             continue


@ActionRegistry.register("do_battle")
def action_do_battle(params, context: ActionContext):
    nav = context.navigator
    config = context.config
    battle_config = config.get_battle_config()
    
    # Pre-battle full auto (one-time, before loop)
    if battle_config.pre_fa:
        nav.click_onthespot()
    
    # Initial battle UI wait
    try:
        nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=10)
    except TimeoutException:
        return ActionContext.RESULT_FAILED
    
    if battle_config.trigger_skip:
        nav.driver.refresh()
        try:
            nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=15)
        except TimeoutException:
            return ActionContext.RESULT_FAILED
    
    current_turn = 1
    fullauto_clicked = 0
    battle_ended = False
    click_target = None

    start_time = time.time()
    while time.time() - start_time < 300:
        
        if "#result_multi" in nav.get_current_url() or "#result/" in nav.get_current_url():
            print("[→] Battle ended - detected result URL")
            battle_ended = True

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
        
        # === 3. Click full auto if not yet clicked this turn ===
        if fullauto_clicked == 0:
            try:
                fullauto_btn = nav.wait_for_clickable(By.CSS_SELECTOR, ".btn-auto", timeout=5)
                nav.click_element(fullauto_btn)
                nav._move_away(fullauto_btn)
                print("[⚙] Full Auto clicked")
                fullauto_clicked = 1
                nav.wait(0.2, 0.4)
            except TimeoutException:
                print("[!] Full Auto not found, retrying...")
                nav.wait(0.2, 0.3)
                continue
            
            # === 4. CRITICAL: Check attack button ON THE SAME PAGE (before refresh) ===
            try:
                atk_btn = nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start", timeout=2)
                if "display-off" in atk_btn.get_attribute("class"):
                    print(f"[i] Turn {current_turn} completed")
                    current_turn += 1
                    fullauto_clicked = 0
                    nav.wait(0.3, 0.5)
                    
                    if not battle_config.until_finish and current_turn > battle_config.turn:
                        context.raids_completed += 1
                        print(f"[→] Battle finished. Raids completed: {context.raids_completed}")
                        return ActionContext.RESULT_SUCCESS
                    
                    # Refresh to skip attack animation / reset UI for next turn
                    nav.driver.refresh()
                    try:
                        nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=10)
                        print("[✓] Battle UI restored after turn refresh")
                    except TimeoutException:
                        print("[×] Battle UI did not return after turn refresh")
                        return ActionContext.RESULT_FAILED

                    continue
            except TimeoutException:
                # Attack button not found - might be battle ended or loading
                pass
            
            # === 5. refresh=true: refresh to skip skill animations ===
            if battle_config.refresh:
                print("[i] Refreshing to skip skill animations...")
                fullauto_clicked = 0  # Page reloads, need to click again
                nav.driver.refresh()
                try:
                    nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=5)
                    print("[✓] Battle UI restored after animation refresh")
                except TimeoutException:
                    print("[×] Battle UI did not return after animation refresh")
                    return ActionContext.RESULT_FAILED
                continue
            
            # === 6. refresh=false: let animations play out ===
            else:
                nav.wait(0.2, 0.3)
                continue
        
        # === 7. refresh=false path: fullauto_clicked=1, wait for attack to process ===
        else:
            try:
                atk_btn = nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start", timeout=5)
                if "display-off" in atk_btn.get_attribute("class"):
                    print(f"[i] Turn {current_turn} completed")
                    current_turn += 1
                    fullauto_clicked = 0
                    nav.wait(0.3, 0.5)
                    
                    if not battle_config.until_finish and current_turn > battle_config.turn:
                        context.raids_completed += 1
                        print(f"[→] Battle finished. Raids completed: {context.raids_completed}")
                        return ActionContext.RESULT_SUCCESS

                    nav.driver.refresh()
                    try:
                        nav.wait_for_element(By.CSS_SELECTOR, ".btn-attack-start.display-on", timeout=5)
                        print("[✓] Battle UI restored after turn refresh")
                    except TimeoutException:
                        print("[×] Battle UI did not return after turn refresh")
                        return ActionContext.RESULT_SUCCESS

                    continue
            except TimeoutException:
                nav.wait(0.3, 0.5)
                pass    
        
        #check A
        if not battle_ended:
            try:
                result_cnt = nav.driver.find_element(By.CSS_SELECTOR, ".prt-result-cnt")
                if result_cnt.is_displayed():
                    print("[→] Battle ended - detected result container")
                    battle_ended = True
            except NoSuchElementException:
                pass
        
        #check B
        if not battle_ended:
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
        
        #check C
        if not battle_ended:
            try:
                click_target = WebDriverWait(nav.driver, 1).until(
                    EC.element_to_be_clickable((
                        By.CSS_SELECTOR,
                        ".pop-usual.pop-rematch-fail .btn-usual-ok"
                    ))
                )
                popup = nav.driver.find_element(By.CSS_SELECTOR, ".pop-usual.pop-rematch-fail")
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
            nav.driver.get("https://game.granbluefantasy.jp/#quest/assist/unclaimed/0/0")
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