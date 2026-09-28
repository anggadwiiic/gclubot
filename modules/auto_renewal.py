import time
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from core.signature import signature_or_default
from core.timing import human_pause

# ================= KONFIGURASI UTAMA =================
FORUM_BASE = "https://police.san-andreas.net"

FORUM_MAP = {
    '156': {'type': 'LT', 'name': 'Valid Trucker License (30 Days Period)', 'dest': '1082'},
    '915': {'type': 'LT', 'name': 'Valid Trucker License (60 Days Period)', 'dest': '1082'},
    '779': {'type': 'LT', 'name': 'Valid Trucker License (90 Days Period)', 'dest': '1082'},
    '872': {'type': 'HT', 'name': 'Valid Trucker Licenses (30 Days Period)', 'dest': '1081'},
    '914': {'type': 'HT', 'name': 'Valid Trucker Licenses (60 Days Period)', 'dest': '1081'},
    '874': {'type': 'HT', 'name': 'Valid Trucker License (90 Days Period)', 'dest': '1081'},
    '208': {'type': 'LL', 'name': 'Valid Lumberjack Licenses', 'dest': '1083'},
    '869': {'type': 'IL', 'name': 'Valid Impound License', 'dest': '877'},
}

REPLY_MESSAGE = """[divbox=white] [center][color=red][b][size=200]EXPIRED[/size][/b][/color][/center][/divbox]
[divbox=white][b][center]You must respond within 3 days.[/center][/b][/divbox]
[divbox=white][center][b](( Silakan gunakan format [color=red]RENEWAL[/color] dengan benar. [url=https://police.san-andreas.net/viewtopic.php?t=19279][color=green]CLICK HERE[/color][/url] ))[/b][/center][/divbox]"""

MAX_DAYS_EXPIRED = 3

MONTH_MAPPING = {
    'JANUARY': 'JANUARY', 'FEBRUARY': 'FEBRUARY', 'MARCH': 'MARCH', 'APRIL': 'APRIL',
    'MAY': 'MAY', 'JUNE': 'JUNE', 'JULY': 'JULY', 'AUGUST': 'AUGUST',
    'SEPTEMBER': 'SEPTEMBER', 'OCTOBER': 'OCTOBER', 'NOVEMBER': 'NOVEMBER', 'DECEMBER': 'DECEMBER',
    'JAN': 'JANUARY', 'FEB': 'FEBRUARY', 'MAR': 'MARCH', 'APR': 'APRIL',
    'JUN': 'JUNE', 'JUL': 'JULY', 'AUG': 'AUGUST', 'SEP': 'SEPTEMBER', 
    'OCT': 'OCTOBER', 'NOV': 'NOVEMBER', 'DEC': 'DECEMBER',
    'JANUARI': 'JANUARY', 'FEBRUARI': 'FEBRUARY', 'MARET': 'MARCH', 
    'MEI': 'MAY', 'JUNI': 'JUNE', 'JULI': 'JULY', 'AGUSTUS': 'AUGUST',
    'OKTOBER': 'OCTOBER', 'NOPEMBER': 'NOVEMBER', 'DESEMBER': 'DECEMBER',
    'JANAURY': 'JANUARY', 'JANUIRY': 'JANUARY', 'PEBRUARI': 'FEBRUARY', 
    'AGT': 'AUGUST', 'AGST': 'AUGUST', 'SEPT': 'SEPTEMBER', 'OKT': 'OCTOBER',
    'NOP': 'NOVEMBER', 'DES': 'DECEMBER'
}

# ================= UTILITIES =================

def destroy_cookie_banner(driver):
    try:
        driver.execute_script(
            "var b=document.querySelector('.cc-window');if(b){b.remove();}"
            "var c=document.querySelector('[aria-label=\"cookieconsent\"]');if(c){c.remove();}"
            "var d=document.getElementById('loading_indicator');if(d){d.remove();}"
        )
    except: pass

def click_element_js(driver, element):
    driver.execute_script("arguments[0].click();", element)


def snapshot_thread_rows(driver):
    for attempt in range(2):
        try:
            data = []
            for row in driver.find_elements(By.CSS_SELECTOR, "li.row"):
                row_class = row.get_attribute("class") or ""
                if any(marker in row_class for marker in ("sticky", "announce", "global")):
                    continue
                link = row.find_element(By.CSS_SELECTOR, "a.topictitle")
                data.append((link.get_attribute("href"), link.text))
            return data
        except StaleElementReferenceException:
            if attempt == 1:
                raise
            time.sleep(0.2)
    return []

def extract_thread_id(url):
    match = re.search(r't=(\d+)', url)
    return match.group(1) if match else None

def normalize_date_text(date_text):
    date_text = date_text.upper().strip()
    date_text = re.sub(r'[\s\-\.]+', '/', date_text)
    parts = date_text.split('/')
    cleaned_parts = []
    for p in parts:
        if re.match(r'\d+(ST|ND|RD|TH)', p): p = re.sub(r'(ST|ND|RD|TH)', '', p)
        cleaned_parts.append(MONTH_MAPPING.get(p, p))
    return "/".join(cleaned_parts)

def parse_date(date_string):
    clean_str = normalize_date_text(date_string)
    formats = ["%d/%B/%Y", "%d/%m/%Y", "%d/%b/%Y", "%d/%m/%y"]
    for fmt in formats:
        try: return datetime.strptime(clean_str, fmt)
        except: continue
    return None

def extract_info_from_title(title):
    pattern_date = r"(?:VALID UNTIL|BERLAKU SAMPAI)[\s:\-\.]*([\w\s/\-\.]+)"
    match_date = re.search(pattern_date, title, re.IGNORECASE)
    if not match_date: return None, None
    raw_date = match_date.group(1).strip()
    try:
        name_part = re.split(r"[\[\(]\s*(?:VALID|BERLAKU)", title, flags=re.IGNORECASE)[0]
        name_clean = re.sub(r"^\[.*?\]", "", name_part).strip()
        return name_clean, raw_date
    except: return "Unknown Applicant", raw_date

def setup_driver():
    try:
        from ..core.browser import create_driver
    except ImportError:
        from core.browser import create_driver
    driver = create_driver()
    try: driver.get(f"{FORUM_BASE}/ucp.php?mode=login")
    except: pass
    return driver

# ================= FORMATTING OUTPUT =================

def print_activity(idx, total, res):
    idx_str = str(idx).zfill(len(str(total)))
    status = res.get("status", "Failed")
    title = res.get("final_title") or res.get("original_title") or "Unknown Thread"

    print(f"({idx_str}/{total}) {title}")
    print(f"        {status}")
    
    if res.get("section_name"):
        print(f"        Section: {res['section_name']}")
        
    if res.get("expected_date") and res["expected_date"] != "N/A":
        print(f"        Expected Date: {res['expected_date']}")

    if "original_title" in res and "final_title" in res and res["original_title"] != res["final_title"]:
        print(f"        Thread Title:")
        print(f"          Before: {res['original_title']}")
        print(f"          After:  {res['final_title']}")
        
    if "reason" in res and res["reason"]:
        print(f"        Reason:")
        lines = str(res["reason"]).split('\n')
        for line in lines:
            print(f"          {line}")
            
    if res.get("url"):
        print(f"        View thread: {res['url']}")
    else:
        if status == "Failed":
            print(f"        View thread: unavailable")
    print("")

def print_summary(total, stats):
    print("Processing completed\n")
    print(f"{total} applications processed\n")
    
    for key in ["Renewal Issued", "Skipped", "Pending", "Failed"]:
        if stats.get(key, 0) > 0:
            print(f"{key:<17} {stats[key]:>3}")
            
    manual_review = stats.get("Pending", 0) + stats.get("Failed", 0)
    if manual_review > 0:
        plural = "s" if manual_review > 1 else ""
        print(f"\n{manual_review} application{plural} requires manual review.")
    print("\n" + "="*50)

# ================= PROCESSING LOGIC =================

def process_renewal_execution(driver, c, signature_config=None):
    url = c['url']
    original_title = c['title']
    new_title = c['new_title']
    dest_forum_id = c['dest']
    origin_f_id = c['forum_id']
    wait = WebDriverWait(driver, 10)
    
    res = {
        "url": url,
        "original_title": original_title,
        "final_title": original_title,
        "expected_date": c['expected_date'],
        "section_name": c.get('section_name')
    }
    
    try:
        driver.get(url)
        destroy_cookie_banner(driver)
        
        # 1. Edit
        edit_btns = driver.find_elements(By.XPATH, "//a[contains(@href, 'mode=edit')]")
        if not edit_btns:
            res["status"] = "Failed"
            res["reason"] = "Edit button not found in the original post."
            return res
            
        driver.execute_script("arguments[0].click();", edit_btns[0])
        subj_box = wait.until(EC.visibility_of_element_located((By.NAME, "subject")))
        
        try:
            wait.until(EC.presence_of_element_located((By.NAME, "creation_time")))
            token = wait.until(EC.presence_of_element_located((By.NAME, "form_token")))
            for _ in range(20): 
                if token.get_attribute("value"): break
                time.sleep(0.1)
        except: pass
        
        subj_box.clear()
        subj_box.send_keys(new_title)
        human_pause(1.8, 2.8)
        
        destroy_cookie_banner(driver)
        driver.execute_script("arguments[0].click();", driver.find_element(By.NAME, "post"))
        try: WebDriverWait(driver, 8).until(EC.url_contains("viewtopic.php"))
        except:
            if "submitted form was invalid" in driver.page_source:
                res["status"] = "Failed"
                res["reason"] = "Form validation failed (submitted form was invalid)."
                return res

        # 2. Reply
        t_id = extract_thread_id(url)
        reply_url = f"{FORUM_BASE}/posting.php?mode=reply&f={origin_f_id}&t={t_id}"
        driver.get(reply_url)
        destroy_cookie_banner(driver)

        if "mode=reply" in driver.current_url or "Post a reply" in driver.page_source:
            msg_box = wait.until(EC.visibility_of_element_located((By.NAME, "message")))
            msg_box.clear()
            msg_box.send_keys(f"{REPLY_MESSAGE}\n{signature_or_default(signature_config)}")
            human_pause(1.8, 2.8)
            driver.execute_script("arguments[0].click();", driver.find_element(By.NAME, "post"))
            try:
                WebDriverWait(driver, 8).until(EC.url_contains("viewtopic.php"))
            except Exception:
                if "submitted form was invalid" in driver.page_source.lower():
                    res["status"] = "Failed"
                    res["reason"] = "Form validation failed (submitted form was invalid)."
                    return res

        # 3. Move
        driver.get(url)
        destroy_cookie_banner(driver)
        tools_icon = driver.find_elements(By.XPATH, "//a[contains(@title, 'Quick mod tools')]")
        if tools_icon: driver.execute_script("arguments[0].click();", tools_icon[0])
        move_link = driver.find_elements(By.XPATH, "//a[contains(@href, 'action=move')]")
        if move_link:
            driver.get(move_link[0].get_attribute("href"))
            dest_dropdown = wait.until(EC.presence_of_element_located((By.NAME, "to_forum_id")))
            Select(dest_dropdown).select_by_value(str(dest_forum_id))
            try:
                shadow = driver.find_element(By.NAME, "move_leave_shadow")
                if shadow.is_selected(): driver.execute_script("arguments[0].click();", shadow)
            except: pass
            driver.execute_script("arguments[0].click();", driver.find_element(By.NAME, "confirm"))
            human_pause(1.8, 2.8)

        # 4. Verify
        driver.get(url)
        try: final_title = driver.find_element(By.CSS_SELECTOR, "h2.topic-title a").text
        except: final_title = new_title

        res["status"] = "Renewal Issued"
        res["final_title"] = final_title
        res["reason"] = "Notification posted · Thread relocated"
        return res

    except Exception as e:
        res["status"] = "Failed"
        res["reason"] = f"Execution error: {type(e).__name__}"
        return res

def _stopped(stop_event):
    return stop_event is not None and stop_event.is_set()


def discover_candidates(driver, stop_event=None):
    candidates = []
    for f_id, config in FORUM_MAP.items():
        if _stopped(stop_event):
            break
        print(f"Scanning {config['name']} (ID: {f_id})...")
        current_url = f"{FORUM_BASE}/viewforum.php?f={f_id}"

        while not _stopped(stop_event):
            try: driver.get(current_url)
            except:
                time.sleep(2)
                if _stopped(stop_event):
                    break
                driver.get(current_url)

            destroy_cookie_banner(driver)
            thread_data = snapshot_thread_rows(driver)

            if _stopped(stop_event) or not thread_data:
                break

            for url, title in thread_data:
                if _stopped(stop_event):
                    break
                if "[DONE]" in title: continue
                name, raw_date = extract_info_from_title(title)
                if not raw_date: continue

                valid_date = parse_date(raw_date)
                if not valid_date: continue

                diff = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - valid_date).days

                if 0 <= diff <= MAX_DAYS_EXPIRED:
                    expected_date_str = valid_date.strftime("%d/%B/%Y").upper()
                    new_title = f"[{config['type']}] {name} [RENEWAL]"

                    candidates.append({
                        "url": url,
                        "title": title,
                        "name": name,
                        "expected_date": expected_date_str,
                        "new_title": new_title,
                        "dest": config['dest'],
                        "forum_id": f_id,
                        "section_name": config['name']
                    })

            next_url = None
            try: next_url = driver.find_element(By.XPATH, "//a[descendant::i[contains(@class, 'fa-chevron-right')]]").get_attribute("href")
            except:
                try: next_url = driver.find_element(By.CSS_SELECTOR, "a[rel='next']").get_attribute("href")
                except: pass

            if next_url and next_url != current_url: current_url = next_url
            else: break
    return candidates


def run_auto_renewal(stop_event=None, on_result=None, driver=None, signature_config=None):
    owns_driver = driver is None
    driver = driver or setup_driver()
    print("="*50)
    print(" GCLU AUTO RENEWAL")
    print("="*50)
    print("")
    candidates = discover_candidates(driver, stop_event)
    print(f"\nDiscovery completed. {len(candidates)} actionable records found.\n")

    stats = {"Renewal Issued": 0, "Failed": 0, "Skipped": 0, "Pending": 0}
    results = []
    total = len(candidates)
    for i, c in enumerate(candidates):
        if _stopped(stop_event):
            break
        res = process_renewal_execution(driver, c, signature_config)
        results.append(res)
        status = res.get("status", "Failed")
        stats[status] = stats.get(status, 0) + 1
        print_activity(i + 1, total, res)
        if on_result:
            on_result(i + 1, total, res)
    print_summary(total, stats)
    if owns_driver:
        driver.quit()
    return {
        "candidates": candidates,
        "results": results,
        "stats": stats,
        "stopped": _stopped(stop_event),
    }

if __name__ == "__main__":
    run_auto_renewal()