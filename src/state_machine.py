from enum import Enum 
from typing import Dict 
import re

class State(Enum):
    IDLE="idle"
    MAIN_MENU="main_menu"
    RAID_LIST="raid_list"
    RAID_SUMMON_SELECT="raid_summon_select"
    RAID_RESULT="raid_result"
    RAID_UNCLAIMED="raid_unclaimed"
    QUEST_SUMMON_SELECT="quest_summon_select"
    QUEST_BATTLE="quest_battle"
    QUEST_RESULT="quest_result"
    ERROR_RECOVERY="error_recovery"

STATE_URL_PATTERNS: Dict[State, str] = {
    State.MAIN_MENU: r"https://game\.granbluefantasy\.jp/#mypage/.*",
    State.RAID_LIST: r"https://game\.granbluefantasy\.jp/#quest/assist/.*",
    State.RAID_SUMMON_SELECT: r"https://game\.granbluefantasy\.jp/#quest/supporter_raid/.*",
    State.RAID_BATTLE: r"https://game\.granbluefantasy\.jp/#raid_multi/.*",
    State.RAID_RESULT: r"https://game\.granbluefantasy\.jp/#result_multi/.*",
    State.RAID_UNCLAIMED: r"https://game\.granbluefantasy\.jp/#quest/assist/unclaimed/.*",
    State.QUEST_SUMMON_SELECT: r"https://game\.granbluefantasy\.jp/#quest/supporter/.*",
    State.QUEST_BATTLE: r"https://game\.granbluefantasy\.jp/#raid/.*",
    State.QUEST_RESULT: r"https://game\.granbluefantasy\.jp/#result/.*",
}

def detect_state(url:str)->State:
    for state,pattern in STATE_URL_PATTERNS.items():
        if re.match(pattern,url):
            return state
    return State.IDLE



