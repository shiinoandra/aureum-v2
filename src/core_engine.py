from config_manager import ConfigManager
from state_machine import State, detect_state
from navigator import Navigator
from task_executor import TaskExecutor
from context import ActionContext,ActionRegistry
from pathlib import Path
import threading
# Import actions to trigger @ActionRegistry.register decorators
from actions import (
    action_select_raid,
    action_select_summon,
    action_join_battle,
    action_do_battle,
    action_refresh_raid_list,
    action_clean_raid_queue,
    action_go_to_raid_list,
    action_go_to_main_menu,
)

class CoreEngine:
    def __init__(self, navigator: Navigator):
        self.navigator = navigator
        self.config = ConfigManager()
        self.task_executor = TaskExecutor(navigator, self.config)
        self._running = False
        self._current_task = None
        self._task_thread = None
    
    def start(self):
        """Start the main automation loop"""
        self._running = True
        while self._running:
            self._main_loop()
    
    def stop(self):
        """Stop the automation loop"""
        self._running = False
        self.task_executor.stop()
    
    def start_task(self, task_path: Path):
        """Start a specific task in background thread"""
        self._current_task = self.task_executor.load_task(task_path)
        self._task_thread = threading.Thread(target=self._run_task_loop)
        self._task_thread.daemon = True
        self._running = True
        self._task_thread.start()
    
    def _run_task_loop(self):
        """
        Run task loop - executes raid cycle repeatedly until exit condition met.
        
        Flow per raid:
        1. Reset context for new raid (turn, battle_finished)
        2. Execute all actions (select_raid → select_summon → join_battle → do_battle)
        3. Check exit condition (raids_completed >= target)
        4. Repeat or exit
        """
        print("[*] Task loop started")
        while self._running and self._current_task:
            try:
                self.task_executor.context.reset()
                print("[*] Context reset, executing task...")
                
                result = self.task_executor.execute_task(self._current_task)
                print(f"[*] Execute result: {result}")
                
                if not result:
                    print("[!] Execute returned False")
                    break
                
                exit_met = self.task_executor.check_exit_condition(self._current_task)
                print(f"[*] Exit condition met: {exit_met}")
                
                if exit_met:
                    break
            except Exception as e:
                print(f"[!] Exception in task: {e}")
                import traceback
                traceback.print_exc()

    def _main_loop(self):
        """
        Main loop - monitors state and handles recovery.
        This runs in the main thread while task runs in background.
        """
        url = self.navigator.get_current_url()
        current_state = detect_state(url)
        self.config.current_state = current_state
        
        if current_state == State.IDLE:
            # Unknown state, wait and check again
            self.navigator.wait(1, 2)
        elif current_state == State.ERROR_RECOVERY:
            self._handle_recovery()
        else:
            # Normal operation - task executor handles it
            self.navigator.wait(0.5, 1)
    
    def _handle_recovery(self):
        """
        Handle recovery based on current detected state.
        
        When something goes wrong, we detect where we are via URL,
        then decide what action to take.
        """
        print("[*] Attempting recovery...")
        
        url = self.navigator.get_current_url()
        actual_state = detect_state(url)
        
        if actual_state == State.RAID_BATTLE:
            # We're in battle but something interrupted - continue battle
            print("[*] Detected raid battle - continuing")
            battle_action = ActionRegistry.get("do_battle")
            if battle_action:
                battle_action({}, self.task_executor.context)
        
        elif actual_state == State.RAID_LIST:
            # We're at raid list - could be task didn't start or we need to restart
            print("[*] Detected raid list - checking if task should restart")
            if not self.task_executor.should_continue(self._current_task):
                print("[*] Task already complete")
                self._running = False
        
        elif actual_state == State.MAIN_MENU:
            # Fell back to main menu - restart task
            print("[*] Back at main menu - restarting task")
            self.task_executor.execute_task(self._current_task)
        
        elif actual_state == State.RAID_UNCLAIMED:
            # Have pending raids - clean them first
            print("[*] Detected unclaimed raids - cleaning queue")
            clean_action = ActionRegistry.get("clean_raid_queue")
            if clean_action:
                clean_action({}, self.task_executor.context)
        
        else:
            # Unknown state - wait and retry
            print(f"[*] Unknown recovery state {actual_state} - waiting")
            self.navigator.wait(2, 3)