from typing import Optional
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import random
import time
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
        offset_y = win_position['y'] + self.driver.execute_script(
            "return window.outerHeight - window.innerHeight;"
        )
        
        # Scroll element into view
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'nearest', inline: 'nearest'});", 
            element
        )
        
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
        
        pyautogui.click()  
    
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
    
    def _fast_move(self, end_pos: tuple):
        """Fast mouse movement - less natural but faster"""
        start_pos = pyautogui.position()
        distance = ((end_pos[0]-start_pos[0])**2 + (end_pos[1]-start_pos[1])**2) ** 0.5
        
        # Very fast: 50-100ms for most moves
        duration = random.uniform(0.05, 0.1) if distance < 300 else random.uniform(0.1, 0.15)
        steps = 2
        
        # Simple linear interpolation
        for i in range(steps + 1):
            t = i / steps
            x = start_pos[0] + (end_pos[0] - start_pos[0]) * t
            y = start_pos[1] + (end_pos[1] - start_pos[1]) * t
            pyautogui.moveTo(x, y)
            time.sleep(duration / steps)

    def _move_away(self, element):
        """Move mouse away from element after click"""
        rect = self.get_element_rect(element)
        screen_w, screen_h = pyautogui.size()
        
        # Pick random direction
        direction = random.choice(['left', 'right', 'up', 'down'])
        if direction == 'left':
            new_x = max(0, rect["x"] - random.randint(50, 200))
            new_y = rect["y"] + random.randint(-50, 50)
        elif direction == 'right':
            new_x = min(screen_w, rect["x"] + rect["width"] + random.randint(50, 200))
            new_y = rect["y"] + random.randint(-50, 50)
        elif direction == 'up':
            new_x = rect["x"] + random.randint(-50, 50)
            new_y = max(0, rect["y"] - random.randint(50, 200))
        else:
            new_x = rect["x"] + random.randint(-50, 50)
            new_y = min(screen_h, rect["y"] + rect["height"] + random.randint(50, 200))
        
        pyautogui.moveTo(new_x, new_y, duration=random.uniform(0.1, 0.2))

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
                x: rect.x + window.pageXOffset,
                y: rect.y + window.pageYOffset,
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