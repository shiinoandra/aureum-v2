import math
import re
from os.path import abspath
from os import path
import pyautogui
import random
import time
from bezier import Curve  
import numpy as np

import csv
from datetime import datetime
import os

import undetected_chromedriver as uc  # Alternative to regular Chrome driver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains


class NavigationHelper:
    def __init__(self,driver):
        self.driver=driver
    @staticmethod
    def bezier_curve(start, end, steps=25):
        """
        Calculates the points for a Bezier curve and returns them as a list of tuples.
        """
        # Use the same logic as before to generate control points
        dx, dy = end[0] - start[0], end[1] - start[1]
        control1 = (
            start[0] + dx * random.uniform(0.2, 0.4) + random.uniform(-dx*0.1, dx*0.1),
            start[1] + dy * random.uniform(0.2, 0.4) + random.uniform(-dy*0.1, dy*0.1)
        )
        control2 = (
            start[0] + dx * random.uniform(0.6, 0.8) + random.uniform(-dx*0.1, dx*0.1),
            start[1] + dy * random.uniform(0.6, 0.8) + random.uniform(-dy*0.1, dy*0.1)
        )
        
        nodes = np.asfortranarray([
            [start[0], control1[0], control2[0], end[0]],
            [start[1], control1[1], control2[1], end[1]],
        ])
        
        curve = Curve(nodes, degree=3)
        
        # Evaluate the curve at 'steps' number of points
        points_on_curve = curve.evaluate_multi(np.linspace(0, 1, steps))
        
        # Return as a list of (x, y) tuples
        return list(zip(points_on_curve[0], points_on_curve[1]))

    def click_element(self, element):
        win_position = self.driver.get_window_rect()
        offset_x = win_position['x']
        offset_y = win_position['y'] + self.driver.execute_script("return window.outerHeight - window.innerHeight;")
        try:
            # First, just ensure the element is in the viewport. 'nearest' is less robotic.
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'nearest', inline: 'nearest'});", element
            )
            # time.sleep(random.uniform(0.1, 0.2)) # Pause as if to locate the element

            # Add a small, random "adjustment" scroll. Humans rarely stop perfectly.
            scroll_offset = random.randint(-20, 20)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_offset});")
            # time.sleep(random.uniform(0.1, 0.2)) # A final pause before moving the mouse

        except Exception as e:
            print(f"[!] scrollIntoView failed: {e}")

        rect = self.get_element_rect(element)

        center_x = rect["x"] + rect["width"] / 2 + offset_x
        center_y = rect["y"] + rect["height"] / 2 + offset_y

        sigma_x = rect["width"] * 0.1
        sigma_y = rect["height"] * 0.1

        x = random.gauss(center_x, sigma_x)
        y = random.gauss(center_y, sigma_y)

        # Get start and end positions
        start_pos = pyautogui.position()
        end_pos = (x, y)

         # 1. Define total duration and number of steps for the movement
        total_duration = random.uniform(0.1, 0.3)
        num_steps = 8

        # 2. Get the list of all points along the curve
        points =  NavigationHelper.bezier_curve(start_pos, end_pos, steps=num_steps)

        # 3. Calculate the duration for each individual step
        duration_per_step = total_duration / num_steps

        # 4. Loop through the points and move with a calculated duration (NO time.sleep)
        for i, point in enumerate(points):
            # Calculate progress (from 0.0 to 1.0)
            progress = i / num_steps
            # Apply the sine easing function
            ease_value = (math.sin(math.pi * progress - math.pi / 2) + 1) / 2
            
            # The middle of the movement should be fastest, ends should be slowest.
            # We distribute the total duration according to the ease curve.
            # This is a bit abstract, a simpler way is to just vary the duration.
            
            # A simpler but still effective approach:
            # Make the start and end of the movement slower.
            if progress < 0.2 or progress > 0.8:
                step_duration = duration_per_step * 1.5 # 50% slower
            else:
                step_duration = duration_per_step * 0.75 # 25% faster
        
            pyautogui.moveTo(point[0], point[1], duration=step_duration)

        # Add tiny "correction" movements at the end for more realism
        for _ in range(random.randint(1, 3)):
            pyautogui.move(
                random.randint(-2, 2),
                random.randint(-2, 2),
                duration=random.uniform(0.01, 0.03)
            )

        # Click with a variable hold time
        hold_time = random.uniform(0.05, 0.1)
        pyautogui.mouseDown()
        time.sleep(hold_time)
        pyautogui.mouseUp()
    
    def out_of_element(self,element):
        win_position = self.driver.get_window_rect()
        offset_x = win_position['x']
        offset_y = win_position['y'] + self.driver.execute_script("return window.outerHeight - window.innerHeight;")
        try:
            # First, just ensure the element is in the viewport. 'nearest' is less robotic.
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'nearest', inline: 'nearest'});", element
            )
            # time.sleep(random.uniform(0.1, 0.2)) # Pause as if to locate the element

            # Add a small, random "adjustment" scroll. Humans rarely stop perfectly.
            scroll_offset = random.randint(-20, 20)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_offset});")
            # time.sleep(random.uniform(0.1, 0.2)) # A final pause before moving the mouse

        except Exception as e:
            print(f"[!] scrollIntoView failed: {e}")

        rect = self.get_element_rect(element)
        center_x = rect["x"] + rect["width"] / 2 + offset_x
        center_y = rect["y"] + rect["height"] / 2 + offset_y
        random_x_offset = center_x + random.randint(-100, 100)
        random_y_offset = center_y + random.randint(-100, 100)

        # 6. Perform the move
        pyautogui.moveTo(random_x_offset, random_y_offset, duration=1)


    
    # def perform_browse_scrolling(self):
    #     """
    #     With a random probability, performs a series of up/down scrolls
    #     to simulate a human browsing the list before making a choice.
    #     """
    #     # Only perform this "browsing" simulation sometimes (e.g., 60% of the time)
    #     if random.random() < 0.6:
    #         print("[i] Simulating human-like 'browse' scrolling...")
            
    #         # Decide on a random number of scrolls to perform
    #         num_scrolls = random.randint(2, 5)
            
    #         for i in range(num_scrolls):
    #             # Scroll a random amount (positive is down, negative is up)
    #             scroll_amount = random.randint(250, 600)
    #             if random.random() < 0.5: # 50% chance to scroll up
    #                 scroll_amount *= -1
                    
    #             self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                
    #             # Pause between scrolls, as if reading
    #             time.sleep(random.uniform(0.3, 0.5))
            
    #         # A final scroll back towards the top to reset the view
    #         self.driver.execute_script("window.scrollTo(0, 0);")
    #         time.sleep(random.uniform(0.3, 0.6))

    def perform_browse_scrolling(self):
        if random.random() < 0.6:
            print("[i] Simulating human-like 'browse' scrolling...")

            actions = ActionChains(self.driver)
            num_scrolls = random.randint(2, 5)

            for _ in range(num_scrolls):
                # Smaller, more natural wheel deltas
                delta = random.randint(100, 300)
                if random.random() < 0.4:
                    delta *= -1  # occasional upward scroll

                actions.scroll_by_amount(0, delta).perform()

                # Human pause
                time.sleep(random.uniform(0.4, 1.2))

            # Gentle return toward top instead of jumping
            actions.scroll_by_amount(0, -random.randint(300, 800)).perform()
            time.sleep(random.uniform(0.4, 1.0))

    def get_element_rect(self,element):
        return  self.driver.execute_script("""
                                            const rect = arguments[0].getBoundingClientRect();
                                            return {
                                                x: rect.x,
                                                y: rect.y,
                                                width: rect.width,
                                                height: rect.height
                                            };
                                        """, element)
    
    @staticmethod
    def play_alert_sound(self, sound_file="alert.mp3"):
        """
        Plays a sound file to alert the user.
        """
        try:
            # Check if the sound file exists before trying to play it
            if os.path.exists(sound_file):
                print("[!!!] PLAYING CAPTCHA ALERT SOUND [!!!]")
                playsound(sound_file)
            else:
                print(f"[!] Alert sound file not found at '{sound_file}'")
        except Exception as e:
            print(f"[!] Error playing sound. Make sure 'playsound' is installed correctly.")
            print(f"[!] Details: {e}")


class BattleHelper:
    def __init__(self,driver,nav:NavigationHelper):
        self.driver=driver
        self.nav=nav

    def find_support_tab_from_elem(self, support_elem):
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
            tab_selector = f".icon-supporter-type-{tab_index}" # Note: Class name might be different
            return self.driver.find_element(By.CSS_SELECTOR, tab_selector)
        except Exception as e:
            print(f"Error finding support tab: {e}")
            return None

    def select_summmon(self):
        try:
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,".btn-usual-ok"))
            )
            print("Auto Summon Setting Found")
            return "next"
        
        except TimeoutException:
            pass
            # try:
            #     support_level = "Lvl 100"
            #     support_name = "Huanglong"

            #     xpath = f"""
            #     //div[contains(@class, 'supporter-summon') and
            #         .//span[@class='txt-summon-level' and normalize-space(text())='{support_level}'] and
            #         .//span[@class='js-summon-name' and normalize-space(text())='{support_name}']]
            #     """
            #     support_elems = driver.find_elements(By.XPATH, xpath) 
            #     if support_elems: 
            #         attribute_tab_btn = self.find_support_tab_from_elem(support_elems[0])
            #         self.nav.click_element(attribute_tab_btn)
            #         self.nav.click_element(support_elems[0])
            #     else:
            #         print("[!] Desired summon not found — using first summon in type0.")
            #         # Step 1: Click type0’s tab (mapped to icon-supporter-type-7)
            #         try:
            #             fallback_tab_btn = self.driver.find_element(By.CSS_SELECTOR, ".icon-supporter-type-7")
            #             self.nav.click_element(fallback_tab_btn)
            #         except:
            #             return("error")

            #         # Step 2: Find the first summon in type0 list
            #         first_summon = WebDriverWait(self.driver, 0.5).until(
            #             EC.presence_of_element_located(
            #                 (By.CSS_SELECTOR, ".prt-supporter-attribute.type0 .btn-supporter")
            #             )
            #         )

            #         print("[→] Selecting first available summon...")
            #         self.click_element(first_summon)
            #     return "next"
             
            # except Exception as e:
            #     print(f"Error during fallback summon selection: {e}")
            #     return "error"
    
    def join_battle(self):
        try:
            quest_start_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-usual-ok.se-quest-start"))
            )
            self.nav.click_element(quest_start_btn)
            
            return "next"
        except TimeoutException:
            print("[!] Could not find quest start button.")
            return "next"

    def wait_for_battle_ui(self, timeout=30):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".btn-attack-start"))
        )
 
    def do_battle(self,entry_trigger_skip=False,refresh=True,until_finish=False,turn=1):

        try:
           # Wait until the attack button is visible and ready
            atk_btn_visible = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, ".btn-attack-start.display-on")
                )
            )
            

            print("[✓] Attack button visible")
            if(entry_trigger_skip):
                self.driver.refresh()
            current_turn =1
            fullauto_clicked=0

            start_time = time.time()
            while time.time() - start_time < 300000:
                try:
                    finished_message = WebDriverWait(self.driver, 1).until(
                        EC.element_to_be_clickable(( By.XPATH,"//div[contains(@class, 'pop-exp')]//div[contains(@class, 'btn-usual-ok')]"))
                    )
                    print("[→] Battle is finished - processing next battle")
                    if(finished_message):
                        # result_ok_btn = WebDriverWait(self.driver, 2).until(
                        #     EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-usual-ok"))
                        # )
                        # click_chance = random.randint(1,6)
                        # if click_chance >3 :
                        self.nav.click_element(finished_message)
                        return next


                except TimeoutException:
                    print("[⚙] Battle is not finished continuing2...")
                    # Refresh to process the next step
                    # If button still active, click full auto

                if(fullauto_clicked==0):
                    try:
                        fullauto_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-auto"))
                        )
                        self.nav.click_element(fullauto_btn)
                        fullauto_clicked=1
                        think_time = random.uniform(0.2,0.4) # 5 to 12 seconds
                        self.nav.out_of_element(fullauto_btn)
                        time.sleep(think_time)
                        
                        print("[⚙] Full Auto clicked")
                        try:
                            atk_btn = WebDriverWait(self.driver, 1).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-attack-start"))
                            )

                            class_attr = atk_btn.get_attribute("class")

                            if "display-off" in class_attr:
                                print("current turn:"+str(current_turn))
                                if(until_finish or current_turn<turn):
                                    time.sleep(random.uniform(0.3,0.5))
                                    self.nav.out_of_element(fullauto_btn)
                                    fullauto_clicked=0
                                    current_turn+=1
                                    self.driver.refresh()
                                else:
                                    return "next"
                                print("[✓] Attack processed — leaving battle")

                        except TimeoutException:
                            # Attack button not found
                            if fullauto_clicked == 1:
                                print("[✓] Attack button disappeared after auto — exiting battle")
                            else:
                                # Probably just refreshed, wait instead of exiting
                                print("[⏳] Attack button not visible yet — waiting")
                                time.sleep(0.5)
                                continue
                        if (refresh):
                            fullauto_clicked=0
                            self.driver.refresh()
                            try:
                                finished_message = WebDriverWait(self.driver, 1).until(
                                    EC.presence_of_element_located(( By.XPATH,     "//div[@class='prt-popup-header' and (normalize-space()='EXP Gained' or contains(normalize-space(), 'battle has ended'))]"))
                                )
                                print("[→] Battle is finished - processing next battle")
                                if(finished_message):
                                    result_ok_btn = WebDriverWait(self.driver, 2).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-usual-ok"))
                                    )
                                    # click_chance = random.randint(1,6)
                                    # if click_chance >3 :
                                    self.nav.click_element(result_ok_btn)
                                    return next
                            except:
                                continue
                            try:
                                self.wait_for_battle_ui(timeout=15)
                                print("[✓] Battle UI restored after refresh")
                            except TimeoutException:
                                print("[×] Battle UI did not return after refresh")
                                return "error"
                        else:
                            try:
                                finished_message = WebDriverWait(self.driver, 1).until(
                                    EC.presence_of_element_located(( By.XPATH,     "//div[@class='prt-popup-header' and (normalize-space()='EXP Gained' or contains(normalize-space(), 'battle has ended'))]"))
                                )
                                print("[→] Battle is finished - processing next battle")
                                if(finished_message):
                                    result_ok_btn = WebDriverWait(self.driver, 2).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-usual-ok"))
                                    )
                                    # click_chance = random.randint(1,6)
                                    # if click_chance >3 :
                                    self.nav.click_element(result_ok_btn)
                                    return next
                            except:
                                continue


                    except TimeoutException:
                        print("[!] Full Auto not found, skipping...")
                        return "next"
                    # Refresh to process the next step

 


                try:
                    atk_btn = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-attack-start"))
                    )

                    class_attr = atk_btn.get_attribute("class")

                except TimeoutException:
                    # Attack button not found
                    if fullauto_clicked == 1:
                        print("[✓] Attack button disappeared after auto — exiting battle")
                        return "next"
                    else:
                        # Probably just refreshed, wait instead of exiting
                        print("[⏳] Attack button not visible yet — waiting")
                        time.sleep(0.5)
                        continue
                    
                except (NoSuchElementException, StaleElementReferenceException):
                    print("[!] Attack button not found — retrying...")
                    return "next"
                
                

        except TimeoutException:
            print("[×] Timeout waiting for attack button — probably not in battle")
            return "error"

        
class StoryEventHelper:

    def __init__(self,driver,eventUrl,nav:NavigationHelper,battle:BattleHelper):
        self.driver=driver
        self.eventUrl=eventUrl
        self.nav=nav
        self.battle = battle
        self.meatUrl=""
        self.hellUrl=""

    def getStoryBattleUrl(self):
            self.driver.get(self.eventUrl)
            
            startBtn = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-event-raid"))
            )
            self.nav.click_element(startBtn)
            time.sleep(0.1)

            battleBtns = WebDriverWait(self.driver, 5).until(
            EC.presence_of_all_elements_located((
                By.XPATH,
                "//div[contains(@class,'prt-questselect-header')]"
                "/following::div[contains(@class,'prt-btn-list')]"
                "//div[contains(@class,'prt-quest-frame')]"
            ))
            )
            quest_ids = []
            for btn in battleBtns:
                # Inside each frame, locate the button element (btn-quest-start or prt-not-enough-article)
                inner_btn = btn.find_element(By.XPATH, ".//div[contains(@class,'btn-quest-start') or contains(@class,'prt-not-enough-article')]")
                quest_ids.append(inner_btn.get_attribute("data-quest-id"))

            self.meatUrl="https://game.granbluefantasy.jp/#quest/supporter/"+quest_ids[0]+"/1"
            self.hellUrl="https://game.granbluefantasy.jp/#quest/supporter/"+quest_ids[2]+"/1/0/10645"
    
    def doMeatBattle(self,amount):
        for i in range(amount):
            emergency_exit=False
            if self.meatUrl not in driver.current_url:
                driver.get(self.meatUrl)
                if self.battle.select_summmon() == "next":
                    think_time = random.uniform(0.1,0.3) # 5 to 12 seconds
                    time.sleep(think_time)
                    if self.battle.join_battle() == "next":
                        time.sleep(think_time)
                        self.battle.do_battle(until_finish=False) # Final step, loop continues regardless of outcome
                        time.sleep(think_time)
                        print(f"[i] Battle Cycle complete.")
                        time.sleep(think_time)
            # else:
            #     print(f"Unhandled status: . Stopping.")
            #     break

    def doHellBattle(self,amount):
        for i in range(amount):
            emergency_exit=False
            if self.hellUrl not in driver.current_url:
                driver.get(self.hellUrl)
                time.sleep(random.uniform(1,1.5))
                if self.battle.select_summmon() == "next":
                    time.sleep(random.uniform(1,1.5))
                    if self.battle.join_battle() == "next":
                        time.sleep(random.uniform(1,2))
                        self.battle.do_battle(until_finish=True,refresh=False,turn=10) # Final step, loop continues regardless of outcome
                        think_time = random.uniform(0.2,0.3) # 5 to 12 seconds
                        print(f"[i] Battle Cycle complete.")
                        

                        time.sleep(think_time)

            # else:
            #     print(f"Unhandled status: . Stopping.")
            #     break      

class jutenEventHelper:
    def __init__(self,driver,nav:NavigationHelper,battle:BattleHelper):
        self.driver=driver
        self.nav=nav
        self.battle = battle
        self.vhUrl=""
        self.exUrl=""
        self.hlUrl=""
        self.baseUrl="https://game.granbluefantasy.jp/#quest/supporter/"
        self.quest_map = {}

    def getQuestBattleUrl(self):
            self.driver.get("https://game.granbluefantasy.jp/#event/terra")
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".prt-quest-btn"))
            )
            # self.nav.click_element(startBtn)
            time.sleep(0.1)


            quest_buttons = driver.find_elements(
                By.CSS_SELECTOR,
                ".prt-quest-btn .btn-quest-start"
            )

            for btn in quest_buttons:
                quest_id = btn.get_attribute("data-quest-id")

                img = btn.find_element(By.CSS_SELECTOR, "img.img-quest-thumbnail")
                src = img.get_attribute("src")

                if "vhard" in src:
                    self.quest_map["very_hard"] = quest_id
                elif "ex" in src:
                    self.quest_map["extreme"] = quest_id
                elif "high" in src:
                    self.quest_map["impossible"] = quest_id
    
    def doQuestBattle(self,amount,type):
        for i in range(int(amount)):
            emergency_exit=False
            if self.baseUrl+str(self.quest_map[str(type)])+"/3" not in driver.current_url:
                driver.get(self.baseUrl+str(self.quest_map[str(type)])+"/3")
                time.sleep(random.uniform(1,1.5))
                if self.battle.select_summmon() == "next":
                    time.sleep(random.uniform(0.2,0.5))
                    if self.battle.join_battle() == "next":
                        self.battle.do_battle(until_finish=True,refresh=False) # Final step, loop continues regardless of outcome
                        think_time = random.uniform(0.2,0.3) # 5 to 12 seconds
                        print(f"[i] Battle Cycle complete.")
                        time.sleep(think_time)

class gwHelper:
    def __init__(self,driver,nav:NavigationHelper,battle:BattleHelper):
        self.driver=driver
        self.nav=nav
        self.battle = battle
        self.nm90Url="https://game.granbluefantasy.jp/#quest/supporter/743461/1"
        ##self.nm90Url="https://game.granbluefantasy.jp/#quest/supporter/942701/1/0/10116"
        #self.nm90Url="https://game.granbluefantasy.jp/#quest/supporter/942721/1/0/10551"



    def handle_popup(self, timeout=1):
        try:
            popup = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".common-pop-error.pop-show"))
            )
            popup_text = popup.find_element(By.CSS_SELECTOR, "#popup-body").text.strip()
            print(f"[!] Popup detected: '{popup_text}'")

            # List of keywords to check for (all in lowercase)
            captcha_keywords = ["verification", "verify", "captcha"]
            # Check if any of the keywords are in the lowercased popup text
            if any(keyword in popup_text.lower() for keyword in captcha_keywords):
                result = "captcha"
            # --- END OF IMPROVEMENT ---
            elif "This raid battle is full" in popup_text:
                result = "raid_full"
            elif "You don’t have enough AP" in popup_text or "not enough AP" in popup_text.lower():
                result = "not_enough_ap"
            elif "You can only provide backup in up to three raid battles at once." in popup_text:
                result = "three_raid"
            elif "Check your pending battles." in popup_text:
                result = "toomuch_pending"
            elif "This raid battle has already ended" in popup_text:
                result = "ended"
            else:
                result = "unknown_popup"

            try:
                ok_button = popup.find_element(By.CSS_SELECTOR, ".btn-usual-ok")
                self.nav.click_element(ok_button)
                time.sleep(1.5)
            except Exception:
                print("[!] Could not find OK button to close popup.")
            return result
        except TimeoutException:
            return None
    
    def doNMBattle(self,amount):
        emergency_exit=False
        for i in range(int(amount)):
            if self.nm90Url not in driver.current_url:
                self.driver.get(self.nm90Url)
            status = self.handle_popup(timeout=1)
            if status == "captcha":
                print("CAPTCHA detected. Stopping script.")
                NavigationHelper.play_alert_sound() # Play the alert sound
                emergency_exit=True
                break
                            
            if self.battle.select_summmon() == "next":
                time.sleep(random.uniform(0.2,0.5))
                if self.battle.join_battle() == "next":
                    self.battle.do_battle(until_finish=True,refresh=False) # Final step, loop continues regardless of outcome
                    think_time = random.uniform(0.2,0.3) # 5 to 12 seconds
                    print(f"[i] Battle Cycle complete.")
                    try:
                        finished_message = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable(( By.XPATH,"//div[contains(@class, 'pop-exp')]//div[contains(@class, 'btn-usual-ok')]"))
                        )
                        print("[→] Battle is finished - processing next battle")
                        if(finished_message):
                            # click_chance = random.randint(1,6)
                            # if click_chance >3 :
                            #     self.nav.click_element(finished_message)
                            # else:
                            self.driver.back()

                    except TimeoutException:
                        print("[⚙] Battle is not finished continuing...")
                        # Refresh to process the next step
                        # If button still active, click full auto
                    time.sleep(think_time)



class freeQuestHelper:

    def __init__(self,driver,nav:NavigationHelper,battle:BattleHelper):
        self.driver=driver
        self.nav = nav
        self.battle = battle
        self.quest_url = "https://game.granbluefantasy.jp/#quest/supporter/104151/3"

    def doQuestBattle(self,amount):
            for i in range(int(amount)):
                emergency_exit=False
                if self.quest_url not in driver.current_url:
                    driver.get(self.quest_url)
                    time.sleep(random.uniform(1,1.5))
                    if self.battle.select_summmon() == "next":
                        time.sleep(random.uniform(0.2,0.5))
                        if self.battle.join_battle() == "next":
                            self.battle.do_battle(until_finish=True,refresh=False) # Final step, loop continues regardless of outcome
                            think_time = random.uniform(0.2,0.3) # 5 to 12 seconds
                            print(f"[i] Battle Cycle complete.")
                            time.sleep(think_time)

class RaidHelper:
    
    def __init__(self,driver,nav:NavigationHelper,battle:BattleHelper):
        self.driver=driver
        self.nav = nav
        self.battle = battle
        self.log_filename = datetime.today().strftime('%Y-%m-%d')+"_raid_log.html"
        self._initialize_log_file()

    def _initialize_log_file(self):
            """Creates a styled HTML log file with a table header if it doesn't exist."""
            # If the file already exists, we do nothing.
            if os.path.exists(self.log_filename):
                return
                
            print(f"[i] Log file not found. Creating '{self.log_filename}'...")
            # Create the HTML file with a header and some CSS for styling
            with open(self.log_filename, 'w', encoding='utf-8') as f:
                f.write("""<!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <title>GBF Raid Loot Log</title>
                        <style>
                            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f0f2f5; color: #333; }
                            h1 { text-align: center; color: #1d2129; }
                            table { border-collapse: collapse; width: 95%; margin: 20px auto; box-shadow: 0 2px 8px rgba(0,0,0,0.1); background-color: #fff; }
                            th, td { border: 1px solid #ddd; text-align: left; padding: 12px; vertical-align: middle; }
                            thead { background-color: #4267B2; color: white; }
                            tr:nth-child(even) { background-color: #f2f2f2; }
                            tr:hover { background-color: #e9ebee; }
                            .loot-cell { display: flex; flex-wrap: wrap; align-items: center; }
                            .loot-item { display: inline-block; text-align: center; position: relative; margin: 4px; }
                            .loot-item img { width: 48px; height: 48px; border-radius: 4px; }
                            .loot-item .quantity { position: absolute; bottom: -2px; right: -2px; background-color: rgba(0,0,0,0.75); color: white; border-radius: 6px; padding: 2px 5px; font-size: 11px; font-weight: bold; }
                        </style>
                    </head>
                    <body>
                        <h1>GBF Raid Loot Log</h1>
                        <table>
                            <thead>
                                <tr>
                                    <th>Timestamp</th>
                                    <th>Raid ID</th>
                                    <th>Raid Name</th>
                                    <th>Loot Collected</th>
                                </tr>
                            </thead>
                            <tbody>
                            </tbody>
                        </table>
                    </body>
                    </html>""")

    
    def handle_popup(self, timeout=1):
        try:
            popup = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".common-pop-error.pop-show"))
            )
            popup_text = popup.find_element(By.CSS_SELECTOR, "#popup-body").text.strip()
            print(f"[!] Popup detected: '{popup_text}'")

            # List of keywords to check for (all in lowercase)
            captcha_keywords = ["verification", "verify", "captcha"]
            # Check if any of the keywords are in the lowercased popup text
            if any(keyword in popup_text.lower() for keyword in captcha_keywords):
                result = "captcha"
            # --- END OF IMPROVEMENT ---
            elif "This raid battle is full" in popup_text:
                result = "raid_full"
            elif "You don’t have enough AP" in popup_text or "not enough AP" in popup_text.lower():
                result = "not_enough_ap"
            elif "You can only provide backup in up to three raid battles at once." in popup_text:
                result = "three_raid"
            elif "Check your pending battles." in popup_text:
                result = "toomuch_pending"
            elif "This raid battle has already ended" in popup_text:
                result = "ended"
            else:
                result = "unknown_popup"

            try:
                ok_button = popup.find_element(By.CSS_SELECTOR, ".btn-usual-ok")
                self.nav.click_element(ok_button)
                time.sleep(1.5)
            except Exception:
                print("[!] Could not find OK button to close popup.")
            return result
        except TimeoutException:
            return None
        
    def refresh_raid_list(self):
        try:
            refresh_btn = WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".btn-search-refresh")
                    )
                )
            self.nav.click_element(refresh_btn)
        except TimeoutException:
            print("[!] Refresh button not found.")

    def pick_raid(self):
        print("[1] Finding suitable raid...")
        try:
            if "#quest/assist" not in driver.current_url:
                self.driver.get("https://game.granbluefantasy.jp/#quest/assist")
            
            # First, check for popups that might prevent picking a raid
            popup_result = self.handle_popup(timeout=1)
            if popup_result:
                return popup_result

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#prt-search-list"))
            )
            self.nav.perform_browse_scrolling()



            raid_rooms = WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "div#prt-search-list div.btn-multi-raid.lis-raid.search")
                )
            )
            
            eligible_raids = []
            HP_THRESHOLD = 60
            for raid in raid_rooms:
                try:
                    hp_style = raid.find_element(By.CSS_SELECTOR, ".prt-raid-gauge-inner").get_attribute("style")
                    hp_percent = float(hp_style.split("width:")[1].split("%")[0])
                    
                    if hp_percent >= HP_THRESHOLD:
                        # Instead of acting immediately, add the valid raid to our list of choices
                        eligible_raids.append({"hp": hp_percent, "raid_element": raid})
                except (NoSuchElementException, IndexError):
                    continue
            
            if not eligible_raids:
                 print("[i] No raids met the HP threshold. Skipping.")
                 return "skip"

            target_raid = random.choice(eligible_raids)
            print(f"Target raid found with {target_raid['hp']}% HP.")
            self.nav.click_element(target_raid["raid_element"])

            popup_result = self.handle_popup(timeout=2)
            if popup_result:
                return popup_result
            
            print("[✓] Joined raid successfully.")
            return "next"
        except Exception as e:
            print(f"An error occurred in pick_raid: {e}")
            return "error"

    def do_raid(self,amount):
        for i in range(amount):
            emergency_exit=False
            status = self.pick_raid()
            if status == "next":
                if self.battle.select_summmon() == "next":
                    if self.battle.join_battle() == "next":
                        self.battle.do_battle(refresh=True,entry_trigger_skip=False,turn=1) # Final step, loop continues regardless of outcomef
                        think_time = random.uniform(1, 2.5) # 5 to 12 seconds
                        print(f"[i] Raid cycle complete. Simulating 'think time' for {think_time:.2f} seconds...")
                        time.sleep(think_time)
            elif status == "toomuch_pending":
                self.clean_raid_queue()
            elif status == "three_raid":
                print("Three raids joined, waiting before refresh...")
                time.sleep(random.uniform(10, 20))
                check_pend_rand = random.uniform(1,10)
                if (check_pend_rand>3):
                    self.clean_raid_queue()
                self.refresh_raid_list()
            elif status == "captcha":
                print("CAPTCHA detected. Stopping script.")
                NavigationHelper.play_alert_sound() # Play the alert sound
                emergency_exit=True
                break
            elif status in ["skip", "error", "raid_full", "not_enough_ap","ended", "unknown_popup"]:
                print(f"Status is '{status}'. Refreshing and retrying.")
                time.sleep(random.uniform(1, 3))

                self.refresh_raid_list()
            else:
                print(f"Unhandled status: '{status}'. Stopping.")
                break
        

    def clean_raid_queue(self):
        try:
            print("[!] Starting pending raid cleanup process...")
            self.driver.get("https://game.granbluefantasy.jp/#quest/assist")
            
            pending_battle_btn = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-unconfirmed-result"))
            )
            self.nav.click_element(pending_battle_btn)
            
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "prt-unclaimed-list"))
            )
            
            while True:
                time.sleep(1.5) # Allow DOM to settle
                raids = self.driver.find_elements(By.CSS_SELECTOR, "#prt-unclaimed-list .btn-multi-raid.lis-raid")
                
                if not raids:
                    print("[✓] No more pending raids found. Cleanup complete.")
                    break
                
                print(f"[i] Found {len(raids)} pending raid(s). Clearing the first one.")
                selected_index = random.randint(0,len(raids)-1)
                raid_id = raids[selected_index].get_attribute("data-raid-id")
                raid_name = raids[selected_index].find_element(By.CSS_SELECTOR, ".txt-raid-name").text.strip()
                try:
                    self.see_battle_result_by_id(raid_id,raid_name)
                except:
                    continue
                
            print("[i] Returning to the raid search page.")
            self.driver.get("https://game.granbluefantasy.jp/#quest/assist")
            return "next"

        except TimeoutException:
            print("[i] No 'pending battles' button found. Assuming queue is clear.")
            if "#quest/assist" not in self.driver.current_url:
                self.driver.get("https://game.granbluefantasy.jp/#quest/assist")
            return "next"
        except Exception as e:
            print(f"[!!] An unexpected error occurred during raid cleanup: {e}")
            return "error"
    

    def log_raid_results(self, raid_id, raid_name):
            """Scrapes loot and writes it as a new row in the HTML log file."""
            print(f"[i] Logging results for raid {raid_id} to HTML...")
            try:
                loot_container = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".prt-item-list"))
                )
                loot_items = loot_container.find_elements(By.CSS_SELECTOR, ".lis-treasure.btn-treasure-item")
                
                if not loot_items:
                    print("[i] No loot items found to log.")
                    return

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # 1. Build the HTML string for all loot items in this raid
                loot_html_parts = []
                for item in loot_items:
                    try:
                        img_element = item.find_element(By.CSS_SELECTOR, ".img-treasure-item")
                        item_id = img_element.get_attribute("alt")
                        item_image_url = img_element.get_attribute("src")
                        
                        quantity = 1
                        try:
                            count_element = item.find_element(By.CSS_SELECTOR, ".prt-article-count")
                            quantity_text = count_element.text.strip().replace('x', '')
                            if quantity_text:
                                quantity = int(quantity_text)
                        except NoSuchElementException:
                            pass # Quantity remains 1

                        # Create a styled div for each item with a quantity overlay
                        loot_html_parts.append(f"""
                            <div class="loot-item">
                                <img src="{item_image_url}" alt="ID: {item_id}" title="Item ID: {item_id}">
                                <span class="quantity">x{quantity}</span>
                            </div>""")
                    except (NoSuchElementException, StaleElementReferenceException) as e:
                        print(f"[!] Could not process a loot item, skipping it: {e}")

                loot_html_string = "".join(loot_html_parts)

                # 2. Build the full HTML table row for this raid entry
                new_row_html = f"""
                <tr>
                    <td>{timestamp}</td>
                    <td>{raid_id}</td>
                    <td>{raid_name}</td>
                    <td class="loot-cell">{loot_html_string}</td>
                </tr>"""

                # 3. Read the existing log, insert the new row, and write it back
                with open(self.log_filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Insert the new row just before the closing <tbody> tag
                content = content.replace("</tbody>", new_row_html + "\n</tbody>")
                
                with open(self.log_filename, 'w', encoding='utf-8') as f:
                    f.write(content)

                print(f"[✓] Successfully logged {len(loot_items)} item type(s) for raid {raid_id}.")

            except TimeoutException:
                print("[!] Loot container '.prt-item-list' not found. Nothing to log.")
            except Exception as e:
                print(f"[!!] An unexpected error occurred during HTML loot logging: {e}")

        
    def see_battle_result_by_id(self,raid_id,raid_name):
        print(f"[→] Opening result for raid {raid_id}")
        selector = f"#prt-unclaimed-list .btn-multi-raid.lis-raid[data-raid-id='{raid_id}']"
        battle_elem = WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        self.nav.click_element(battle_elem)

        # Process result
        try:
            result_ok_btn = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-usual-ok"))
            )
            self.nav.click_element(result_ok_btn)
            time.sleep(random.uniform(0.2, 0.7))
            self.log_raid_results(raid_id,raid_name)

            self.driver.back()

            # Wait until we’re back to the pending list
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#prt-unclaimed-list .btn-multi-raid.lis-raid"))
            )
            print(f"[✓] Finished raid {raid_id}")

        except Exception as e:
            print(f"[!] Error processing raid {raid_id}: {e}")
            return "next"

# --- Main script execution ---
try:
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")


    driver = uc.Chrome(
        options=chrome_options,
        user_data_dir=r"C:\\Selenium\\ChromeProfile",
        version_main = 146
    )

    eventUrl="https://game.granbluefantasy.jp/#event/treasureraid170"
    nav = NavigationHelper(driver)
    bat = BattleHelper(driver,nav)
    rh = RaidHelper(driver,nav,bat)
    sh = StoryEventHelper(driver,eventUrl,nav,bat)
    jh = jutenEventHelper(driver,nav,bat)
    fh = freeQuestHelper(driver,nav,bat)
    gwh = gwHelper(driver,nav,bat)

    type_option = {
    "1": rh.do_raid,
    "2": sh.getStoryBattleUrl,
    "3":jh.getQuestBattleUrl,
    "4": fh.doQuestBattle,
    "5" : gwh.doNMBattle,
    }

    type_choice = input("Select mode:\n1. Raid\n2. Story Event \n> ")

    if type_choice in type_option:
        if type_choice == "1" :
            amount = input("Enter number of iteration.")
            time.sleep(3)
            type_option[type_choice](int(amount))# call the correct function
        if type_choice == "2" :
            time.sleep(3)
            type_option[type_choice]()
            story_option = {
                "1": sh.doMeatBattle,
                "2": sh.doHellBattle,
                }
            story_choice = input("Select mode:\n1. Mats Battle\n2. Hell Battle \n> ")
            amount = input("Enter number of iteration.")
            time.sleep(3)
            story_option[story_choice](int(amount))# call the correct function

        if type_choice == "3" :
            time.sleep(3)
            type_option[type_choice]()
            difficulty_option = {
                "1": "very_hard",
                "2": "extreme",
                "3":"impossible"
                }
            difficulty_choice = input("Select quest difficulty:\n1. Very Hard\n2. Extreme\n3. Impossible\n> ")
            amount = input("Enter number of iteration.")
            time.sleep(3)
            jh.doQuestBattle(int(amount),difficulty_option[difficulty_choice])# call the correct function
        if type_choice == "4" :
            time.sleep(3)
            amount = input("Enter number of iteration.")
            time.sleep(3)
            type_option[type_choice](int(amount))
        if type_choice == "5" :
            time.sleep(3)
            amount = input("Enter number of iteration.")
            time.sleep(3)
            type_option[type_choice](int(amount))

    else:
        print("Invalid selection")
        sh.getStoryBattleUrl()


        
finally:
    print("[i] Script finished or was interrupted.")
    if driver:
        print("[i] Closing browser...")
        driver.quit()

