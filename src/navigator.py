from typing import Optional
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import random
import time
import math
import pyautogui
import numpy as np
from bezier import Curve

class Navigator:
    def __init__(self,driver:WebDriver):
        self.driver = driver
    
    def get_current_url(self)->str:
        return self.driver.current_url
    
    def wait_for_element(self,by:By,selector:str,timeout:int=10):
        return WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, selector))
                ) 
                
    def wait_for_clickable(self,by:By,selector:str,timeout:int=10):
        return WebDriverWait(self.driver,timeout).until(
                EC.element_to_be_clickable((by,selector))
        )
    
    def click_element(self,element,fast:bool=False):
        win_position = self.driver.get_window_rect()
        offset_x = win_position['x']
        offset_y = win_position['y'] + self.driver.execute_script("return window.outerHeight - window.innerHeight;")
        try:
            # First, just ensure the element is in the viewport. 'nearest' is less robotic.
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", element
            )

            # Add a small, random "adjustment" scroll. Humans rarely stop perfectly.
            scroll_offset = random.randint(-20, 20)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_offset});")
            # time.sleep(random.uniform(0.1, 0.2)) # A final pause before moving the mouse

        except Exception as e:
            print(f"[!] scrollIntoView failed: {e}")
        
        # Small pause as if to locate element
        time.sleep(random.uniform(0.05, 0.1))
        
        # Get element center
        rect = self.get_element_rect(element)
        center_x = rect["x"] + rect["width"] / 2 + offset_x
        center_y = rect["y"] + rect["height"] / 2 + offset_y
        
        # Add slight random offset (human-like)
        sigma_x = rect["width"] * 0.1
        sigma_y = rect["height"] * 0.1
        x = random.gauss(center_x, sigma_x)
        y = random.gauss(center_y, sigma_y)
        
        if fast:
            self._fast_move((x, y))
        else:
            self._human_move((x, y))
        
        if not fast:
            # 1-2 tiny corrections like old script, but faster
            for _ in range(random.randint(1, 2)):
                pyautogui.move(
                    random.randint(-2, 2),
                    random.randint(-2, 2),
                    duration=random.uniform(0.01, 0.02)
                )
            
            # 2. Variable hold click (the key anti-detection feature)
        hold_time = random.uniform(0.03, 0.08)
        pyautogui.mouseDown()
        time.sleep(hold_time)
        pyautogui.mouseUp()    

        if(random.uniform(0.0,1.0)>0.5):
            self._move_away(element)
        
    def _human_move(self, end_pos: tuple):
        """Move mouse with bezier curve - natural but slower"""
        start_pos = pyautogui.position()
        distance = ((end_pos[0]-start_pos[0])**2 + (end_pos[1]-start_pos[1])**2) ** 0.5
        
        # Distance-based speed
        if distance < 100:
            duration = random.uniform(0.05, 0.1)
            steps = 3
        elif distance < 300:
            duration = random.uniform(0.1, 0.2)
            steps = 5
        else:
            duration = random.uniform(0.2, 0.35)
            steps = 8
        
        # Generate bezier curve points
        dx, dy = end_pos[0] - start_pos[0], end_pos[1] - start_pos[1]
        control1 = (
            start_pos[0] + dx * random.uniform(0.2, 0.4),
            start_pos[1] + dy * random.uniform(0.2, 0.4)
        )
        control2 = (
            start_pos[0] + dx * random.uniform(0.6, 0.8),
            start_pos[1] + dy * random.uniform(0.6, 0.8)
        )
        
        nodes = np.asfortranarray([
            [start_pos[0], control1[0], control2[0], end_pos[0]],
            [start_pos[1], control1[1], control2[1], end_pos[1]],
        ])
        curve = Curve(nodes, degree=3)
        points = curve.evaluate_multi(np.linspace(0, 1, steps))
        points = list(zip(points[0], points[1]))
        
        # Move through points
        for point in points:
            pyautogui.moveTo(point[0], point[1])
            time.sleep(duration / steps)
    
    # def _fast_move(self, end_pos: tuple):
    #     """Fast mouse movement - less natural but faster"""
    #     start_pos = pyautogui.position()
    #     distance = ((end_pos[0]-start_pos[0])**2 + (end_pos[1]-start_pos[1])**2) ** 0.5
        
    #     # Very fast: 50-100ms for most moves
    #     duration = random.uniform(0.05, 0.1) if distance < 300 else random.uniform(0.1, 0.15)
    #     steps = 2
        
    #     # Simple linear interpolation
    #     for i in range(steps + 1):
    #         t = i / steps
    #         x = start_pos[0] + (end_pos[0] - start_pos[0]) * t
    #         y = start_pos[1] + (end_pos[1] - start_pos[1]) * t
    #         pyautogui.moveTo(x, y)
    #         time.sleep(duration / steps)

    def _fast_move(self, end_pos: tuple):
        start_pos = pyautogui.position()
        
        # Overshoot by 5-15px in a random direction
        overshoot_x = end_pos[0] + random.randint(-15, 15)
        overshoot_y = end_pos[1] + random.randint(-15, 15)
        
        # Step 1: Move 80% of the way to overshoot point
        t = 0.8
        mid_x = start_pos[0] + (overshoot_x - start_pos[0]) * t
        mid_y = start_pos[1] + (overshoot_y - start_pos[1]) * t
        pyautogui.moveTo(mid_x, mid_y)
        time.sleep(random.uniform(0.02, 0.04))
        
        # Step 2: Snap to actual target
        pyautogui.moveTo(end_pos[0], end_pos[1])
        time.sleep(random.uniform(0.02, 0.03))

    def _move_away(self, element):
        """Move mouse away from element after click - natural radius-based"""
        rect = self.get_element_rect(element)
        screen_w, screen_h = pyautogui.size()
        
        # Element center
        center_x = rect["x"] + rect["width"] / 2
        center_y = rect["y"] + rect["height"] / 2
        
        # Random offset within radius (-150 to +150 px from center)
        radius = random.randint(80, 150)
        angle = random.uniform(0, 2 * math.pi)
        offset_x = int(radius * math.cos(angle))
        offset_y = int(radius * math.sin(angle))
        
        new_x = center_x + offset_x
        new_y = center_y + offset_y
        
        # Clamp with padding so it doesn't snap to screen borders
        padding = 50
        new_x = max(padding, min(screen_w - padding, new_x))
        new_y = max(padding, min(screen_h - padding, new_y))
        
        self._fast_move((new_x, new_y))

    def scroll_element(self,element):
        # Option 2: Mouse wheel scroll (more human-like)
        # Calculate scroll needed
        scroll_amt = random.randint(200, 500)
        for _ in range(random.randint(2, 4)):
            pyautogui.scroll(-scroll_amt)
            time.sleep(random.uniform(0.1, 0.2))
    
    
    def get_element_rect(self, element):
        """Get element's position and size"""
        return self.driver.execute_script(
            """
            var rect = arguments[0].getBoundingClientRect();
            return {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height
            };
            """, 
            element
        )
    
    def refresh(self):
        """Refresh the browser page"""
        self.driver.refresh()
    
    def wait(self, min_time: float = 0.2, max_time: float = 0.5):
        """Random wait to mimic human behavior"""
        time.sleep(random.uniform(min_time, max_time))