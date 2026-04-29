import json
from pathlib import Path
from selenium.webdriver.common.by import By


class DropLogger:
    """DOM-based drop logging.

    Parses result screen DOM to extract dropped items.
    Based on hihihori3.py's log_raid_results() which parses:
    - .prt-item-list
    - .lis-treasure.btn-treasure-item
    - .img-treasure-item (for image URL + item ID)
    - .prt-article-count (for quantity)

    Usage: called by TaskManager after a successful raid cycle when the browser
    is on a result screen (#result_multi/*).
    """

    def __init__(self):
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

    def capture(self, driver, raid_id: str, raid_name: str) -> str:
        """Parse result DOM and return items as a JSON string.

        Returns:
            JSON string: list of {"name": str, "count": int, "image_url": str}
        """
        try:
            # Modern result screen: look for item list container first
            item_list = driver.find_elements(By.CSS_SELECTOR, ".prt-item-list")
            if item_list:
                treasures = item_list[0].find_elements(
                    By.CSS_SELECTOR, ".lis-treasure.btn-treasure-item"
                )
            else:
                treasures = driver.find_elements(
                    By.CSS_SELECTOR, ".lis-treasure.btn-treasure-item"
                )

            items = []
            for treasure in treasures:
                try:
                    # Item name
                    name_els = treasure.find_elements(
                        By.CSS_SELECTOR, ".prt-item-name, .txt-item-name"
                    )
                    name = name_els[0].text.strip() if name_els else "Unknown"

                    # Image URL (may contain item ID)
                    img_els = treasure.find_elements(
                        By.CSS_SELECTOR, ".img-treasure-item"
                    )
                    img_url = img_els[0].get_attribute("src") if img_els else ""

                    # Quantity
                    count_els = treasure.find_elements(
                        By.CSS_SELECTOR, ".prt-article-count, .txt-article-count"
                    )
                    count_text = count_els[0].text.strip() if count_els else "1"
                    try:
                        count = int(count_text.replace("x", "").replace(",", ""))
                    except ValueError:
                        count = 1

                    if name and name != "Unknown":
                        items.append(
                            {"name": name, "count": count, "image_url": img_url}
                        )
                except Exception:
                    # Skip individual malformed treasure nodes
                    continue

            # Fallback: older result screen format
            if not items:
                alt_items = driver.find_elements(By.CSS_SELECTOR, ".prt-item")
                for item in alt_items:
                    try:
                        text = item.text.strip()
                        if text:
                            items.append(
                                {"name": text, "count": 1, "image_url": ""}
                            )
                    except Exception:
                        continue

            print(
                f"[DropLogger] Captured {len(items)} items for "
                f"raid {raid_id} ({raid_name})"
            )
            return json.dumps(items, ensure_ascii=False)
        except Exception as e:
            print(f"[DropLogger] Error capturing drops: {e}")
            return "[]"
