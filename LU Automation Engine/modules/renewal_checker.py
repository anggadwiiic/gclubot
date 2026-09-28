import os
import logging
import time
import re
from datetime import datetime
from selenium import webdriver
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
    '1082': {'type': 'LT', 'name': 'Lorry Trucker', 'archive_id': '155'},
    '1081': {'type': 'HT', 'name': 'Heavy Trucker', 'archive_id': '875'},
    '1083': {'type': 'LL', 'name': 'Lumberjack License', 'archive_id': '209'},
    '877':  {'type': 'IL', 'name': 'Impound License', 'archive_id': '868'},
}

DENIED_MESSAGE_TEMPLATE = """[divbox=#F1F1F1][center]
[img]https://i.imgur.com/iHky2fT.png[/img]
[b][size=125]Administrative Services Bureau - Gun Control and Licensing Unit[/size][/b]
[b][size=125]License Application Response[/size][/b][/center]
[hr][/hr]
[divbox=#20354C][color=white][center]License Renewal[/center][/color][/divbox]

Dear Mr./Mrs. {LAST_NAME},

We've reviewed your application and your record, and after a long deliberation, we'd like to inform you that your application has been [b]DENIED[/b] because of the following reason:

[b]Reason(s):[/b]
[list][*] Exceeded the 3-day renewal grace period[/list]

[b]Note(s):[/b]
[list][*] You must submit a completely new license application form[/list]

{SIGNATURE}[/divbox]"""

MAX_DAYS_ALLOWANCE = 3

# ================= UTILITIES =================

def destroy_cookie_banner(driver):
    try:
        driver.execute_script(
            "var b=document.querySelector('.cc-window');if(b){b.remove();}"
            "var c=document.querySelector('[aria-label=\"cookieconsent\"]');if(c){c.remove();}"
            "var d=document.getElementById('loading_indicator');if(d){d.remove();}"
        )
    except: pass

def normalize_date_text(date_text):
    date_text = date_text.strip()
    date_text = re.sub(r'^(Posted|By|on)\s+', '', date_text, flags=re.IGNORECASE)
    replacements = {
        'Januari': 'January', 'Februari': 'February', 'Maret': 'March', 
        'April': 'April', 'Mei': 'May', 'Juni': 'June', 
        'Juli': 'July', 'Agustus': 'August', 'September': 'September', 
        'Oktober': 'October', 'November': 'November', 'Desember': 'December',
        'Pebruari': 'February' 
    }
    for id_month, en_month in replacements.items():
        date_text = date_text.replace(id_month, en_month)
    return date_text

def parse_forum_date(date_string):
    clean_str = normalize_date_text(date_string)
    match = re.search(r'((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+[A-Za-z]+\s+\d{1,2}.*|\d{1,2}\s+[A-Za-z]+\s+\d{4}.*)', clean_str, re.IGNORECASE)
    if match:
        clean_str = match.group(1).strip()
        
    formats = [
        "%d %B %Y, %H:%M", "%d %b %Y, %H:%M", 
        "%a %b %d, %Y %I:%M %p", "%d %B %Y"
    ]
    for fmt in formats:
        try: return datetime.strptime(clean_str, fmt)
        except ValueError: continue
    return None

def extract_last_name(title):
    try:
        pre_tag = re.split(r'\[(?:RENEWAL|EXP)', title, flags=re.IGNORECASE)[0]
        clean_name = re.sub(r'^\[.*?\]', '', pre_tag).strip()
        parts = clean_name.split()
        if parts:
            last_name = parts[-1]
            return re.sub(r'[^a-zA-Z]', '', last_name)
    except: pass
    return "Applicant"

def get_last_post_data(driver):
    posts = driver.find_elements(By.CSS_SELECTOR, ".post")
    if not posts: return None, None, None
    last_post = posts[-1]
    try:
        content = last_post.find_element(By.CSS_SELECTOR, "div.content").text
        date_elem = last_post.find_element(By.CSS_SELECTOR, ".author")
        raw_text = date_elem.text
        date_part = raw_text.split('»')[1].strip() if '»' in raw_text else raw_text
        date_obj = parse_forum_date(date_part)
        return "Unknown", content, date_obj
    except:
        return None, None, None


def snapshot_topic_links(driver):
    for attempt in range(2):
        try:
            return [
                (topic.get_attribute("href"), topic.text)
                for topic in driver.find_elements(By.CSS_SELECTOR, "a.topictitle")
            ]
        except StaleElementReferenceException:
            if attempt == 1:
                raise
            time.sleep(0.2)
    return []

def wait_for_form_token(driver):
    try: WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "form_token")))
    except: pass

def setup_driver():
    try:
        from ..core.browser import create_driver
    except ImportError:
        from core.browser import create_driver

    driver = create_driver()
    try:
        driver.get(f"{FORUM_BASE}/ucp.php?mode=login")
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
        
    if res.get("expected_date"):
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
    
    for key in ["Denied", "Already processed", "Pending", "Failed"]:
        if stats.get(key, 0) > 0:
            print(f"{key:<17} {stats[key]:>3}")
            
    manual_review = stats.get("Pending", 0) + stats.get("Failed", 0)
    if manual_review > 0:
        plural = "s" if manual_review > 1 else ""
        print(f"\n{manual_review} application{plural} requires manual review.")
    print("\n" + "="*50)

# ================= ACTIONS =================

def process_thread_execution(driver, c, signature_config=None):
    url = c['url']
    original_title = c['title']
    archive_id = c['archive_id']
    task = c['task']
    wait = WebDriverWait(driver, 10)
    
    res = {
        "url": url,
        "original_title": original_title,
        "final_title": original_title,
        "section_name": c.get("section_name")
    }
    
    try:
        driver.get(url)
        destroy_cookie_banner(driver)
        
        if task == "AUTOFIX":
            tools_icon = driver.find_elements(By.XPATH, "//a[contains(@title, 'Quick mod tools')]")
            if tools_icon:
                driver.execute_script("arguments[0].click();", tools_icon[0])
                human_pause(0.9, 1.5)
            
            move_link = driver.find_element(By.XPATH, "//a[contains(@href, 'action=move')]")
            driver.get(move_link.get_attribute("href"))
            
            dest_select = wait.until(EC.presence_of_element_located((By.NAME, "to_forum_id")))
            Select(dest_select).select_by_value(str(archive_id))
            
            try:
                shadow = driver.find_element(By.NAME, "move_leave_shadow")
                if shadow.is_selected(): shadow.click()
            except: pass
            
            driver.find_element(By.NAME, "confirm").click()
            human_pause(1.8, 2.8)
            
            res["status"] = "Already processed"
            res["reason"] = "Thread was already denied but not moved. Relocated successfully."
            return res

        if task == "DENY":
            last_name = extract_last_name(original_title)
            name_part = re.split(r'\[(?:RENEWAL)', original_title, flags=re.IGNORECASE)[0].strip()
            new_title = f"{name_part} [DENIED]" if name_part else f"{original_title} [DENIED]"
            
            # 1. Rename
            edit_btns = driver.find_elements(By.XPATH, "//a[contains(@href, 'mode=edit')]")
            if edit_btns:
                driver.execute_script("arguments[0].click();", edit_btns[0])
                wait_for_form_token(driver)
                subj_box = wait.until(EC.visibility_of_element_located((By.NAME, "subject")))
                subj_box.clear()
                subj_box.send_keys(new_title)
                human_pause(1.8, 2.8)
                driver.find_element(By.NAME, "post").click()
                human_pause(1.8, 2.8)
                if "submitted form was invalid" in driver.page_source.lower():
                    res["status"] = "Failed"
                    res["reason"] = "Form validation failed (submitted form was invalid)."
                    return res
                
            # 2. Reply
            match_t = re.search(r't=(\d+)', url)
            t_id = match_t.group(1) if match_t else ""
            driver.get(f"{FORUM_BASE}/posting.php?mode=reply&t={t_id}")
            destroy_cookie_banner(driver)
            wait_for_form_token(driver)
            
            msg_box = wait.until(EC.visibility_of_element_located((By.NAME, "message")))
            msg_box.clear()
            message = DENIED_MESSAGE_TEMPLATE.replace("{LAST_NAME}", last_name)
            msg_box.send_keys(message.replace("{SIGNATURE}", signature_or_default(signature_config)))
            human_pause(1.8, 2.8)
            driver.find_element(By.NAME, "post").click()
            human_pause(1.8, 2.8)
            if "submitted form was invalid" in driver.page_source.lower():
                res["status"] = "Failed"
                res["reason"] = "Form validation failed (submitted form was invalid)."
                return res
            
            # 3. Move
            driver.get(url)
            destroy_cookie_banner(driver)
            tools_icon = driver.find_elements(By.XPATH, "//a[contains(@title, 'Quick mod tools')]")
            if tools_icon: driver.execute_script("arguments[0].click();", tools_icon[0])
            move_link = driver.find_element(By.XPATH, "//a[contains(@href, 'action=move')]")
            driver.get(move_link.get_attribute("href"))
            dest_select = wait.until(EC.presence_of_element_located((By.NAME, "to_forum_id")))
            Select(dest_select).select_by_value(str(archive_id))
            try:
                shadow = driver.find_element(By.NAME, "move_leave_shadow")
                if shadow.is_selected(): shadow.click()
            except: pass
            driver.find_element(By.NAME, "confirm").click()
            
            # Verify
            driver.get(url)
            try: final_title = driver.find_element(By.CSS_SELECTOR, "h2.topic-title a").text
            except: final_title = new_title
            
            res["status"] = "Denied"
            res["final_title"] = final_title
            res["reason"] = "Exceeded the 3-day renewal grace period."
            return res

    except Exception as e:
        res["status"] = "Failed"
        res["reason"] = f"Execution error: {type(e).__name__}"
        return res

def run_renewal_checker(stop_event=None, on_result=None, driver=None, signature_config=None):
    """Discover and process renewal threads without GUI dependencies."""
    import threading

    event = stop_event or threading.Event()
    owned_driver = driver is None
    active_driver = driver or setup_driver()
    candidates = []

    try:
        for f_id, config in FORUM_MAP.items():
            if event.is_set():
                break
            current_url = f"{FORUM_BASE}/viewforum.php?f={f_id}"
            while True:
                if event.is_set():
                    break
                active_driver.get(current_url)
                destroy_cookie_banner(active_driver)
                try:
                    WebDriverWait(active_driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.topictitle"))
                    )
                except Exception:
                    pass

                thread_data = snapshot_topic_links(active_driver)
                for url, title in thread_data:
                    if event.is_set():
                        break
                    if "[DENIED]" in title.upper():
                        candidates.append({
                            "url": url, "title": title, "task": "AUTOFIX",
                            "archive_id": config["archive_id"],
                            "section_name": config["name"],
                        })
                        continue
                    if "[RENEWAL]" not in title.upper():
                        continue

                    active_driver.get(url)
                    destroy_cookie_banner(active_driver)
                    posts = active_driver.find_elements(By.CSS_SELECTOR, ".post")
                    pagination = active_driver.find_elements(
                        By.CSS_SELECTOR, ".pagination a.button"
                    )
                    if len(posts) <= 1 and not pagination:
                        continue
                    if pagination:
                        number_urls = [
                            button.get_attribute("href")
                            for button in pagination
                            if button.text.isdigit()
                        ]
                        if number_urls:
                            active_driver.get(number_urls[-1])

                    _, content, date_obj = get_last_post_data(active_driver)
                    if not content:
                        continue
                    content_lower = content.lower()
                    expired_warning = any(
                        phrase in content_lower
                        for phrase in (
                            "must respond within 3 days",
                            "response is expected within 3 days",
                            "3x24 after",
                            "3 (three) days",
                            "mandatory action required",
                        )
                    )
                    user_replied = any(
                        phrase in content_lower
                        for phrase in (
                            "personal information",
                            "duration of license",
                            "license application form",
                        )
                    )
                    if user_replied or not expired_warning or not date_obj:
                        continue
                    if (datetime.now().date() - date_obj.date()).days > MAX_DAYS_ALLOWANCE:
                        candidates.append({
                            "url": url, "title": title, "task": "DENY",
                            "archive_id": config["archive_id"],
                            "section_name": config["name"],
                        })

                next_url = None
                try:
                    next_url = active_driver.find_element(
                        By.XPATH,
                        "//a[descendant::i[contains(@class, 'fa-chevron-right')]]",
                    ).get_attribute("href")
                except Exception:
                    try:
                        next_url = active_driver.find_element(
                            By.CSS_SELECTOR, "a[rel='next']"
                        ).get_attribute("href")
                    except Exception:
                        pass
                if not next_url or next_url == current_url:
                    break
                current_url = next_url

        results = []
        stats = {"Denied": 0, "Already processed": 0, "Pending": 0, "Failed": 0}
        total = len(candidates)
        for index, candidate in enumerate(candidates, 1):
            if event.is_set():
                break
            try:
                result = process_thread_execution(
                    active_driver,
                    candidate,
                    signature_config=signature_config,
                )
            except Exception as exc:
                logging.exception("Renewal thread processing failed")
                result = {
                    "url": candidate.get("url"),
                    "original_title": candidate.get("title"),
                    "final_title": candidate.get("title"),
                    "section_name": candidate.get("section_name"),
                    "status": "Failed",
                    "reason": f"Execution error: {type(exc).__name__}",
                }
            results.append(result)
            status = result.get("status", "Failed")
            stats[status] = stats.get(status, 0) + 1
            if on_result:
                on_result(index, total, result)
        return {
            "candidates": candidates,
            "results": results,
            "stats": stats,
            "stopped": event.is_set(),
        }
    finally:
        if owned_driver:
            try:
                active_driver.quit()
            except Exception:
                pass


def main():
    print("="*50)
    print("RENEWAL CHECKER")
    print("="*50)
    driver = setup_driver()
    input(" [ACTION] Press ENTER if you are logged in to start processing... ")
    print("")
    
    candidates = []
    
    # --- PHASE 1: DISCOVERY ---
    for f_id, config in FORUM_MAP.items():
        print(f"Scanning {config['name']} (ID: {f_id})...")
        current_url = f"{FORUM_BASE}/viewforum.php?f={f_id}"
        page_count = 1
        
        while True:
            driver.get(current_url)
            destroy_cookie_banner(driver)
            try: WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.topictitle")))
            except: pass
            
            threads = driver.find_elements(By.CSS_SELECTOR, "a.topictitle")
            page_threads = [(t.get_attribute('href'), t.text) for t in threads]
            
            for url, title in page_threads:
                if "[DENIED]" in title.upper():
                    candidates.append({
                        "url": url, 
                        "title": title, 
                        "task": "AUTOFIX", 
                        "archive_id": config['archive_id'],
                        "section_name": config['name']
                    })
                    continue
                    
                if "[RENEWAL]" in title.upper():
                    driver.get(url)
                    destroy_cookie_banner(driver)
                    posts = driver.find_elements(By.CSS_SELECTOR, ".post")
                    pagination = driver.find_elements(By.CSS_SELECTOR, ".pagination a.button")
                    if len(posts) <= 1 and not pagination: continue
                    
                    if pagination:
                        number_links = [btn for btn in pagination if btn.text.isdigit()]
                        if number_links: driver.get(number_links[-1].get_attribute("href"))
                    
                    author, content, date_obj = get_last_post_data(driver)
                    if not content: continue
                    
                    c_lower = content.lower()
                    is_expired_warning = any(x in c_lower for x in ["must respond within 3 days", "response is expected within 3 days", "3x24 after", "3 (three) days", "mandatory action required"])
                    is_user_replied = any(x in c_lower for x in ["personal information", "duration of license", "license application form"])
                    
                    if is_user_replied or not is_expired_warning or not date_obj: continue
                    
                    diff_days = (datetime.now().date() - date_obj.date()).days
                    if diff_days > MAX_DAYS_ALLOWANCE:
                        candidates.append({
                            "url": url,
                            "title": title, 
                            "task": "DENY", 
                            "archive_id": config['archive_id'],
                            "section_name": config['name']
                        })

            # Next Page
            next_url = None
            try: next_url = driver.find_element(By.XPATH, "//a[descendant::i[contains(@class, 'fa-chevron-right')]]").get_attribute("href")
            except:
                try: next_url = driver.find_element(By.CSS_SELECTOR, "a[rel='next']").get_attribute("href")
                except: pass
                
            if next_url and next_url != current_url: current_url = next_url
            else: break
            
    print(f"\nDiscovery completed. {len(candidates)} actionable records found.\n")
    
    # --- PHASE 2: EXECUTION ---
    stats = {"Denied": 0, "Already processed": 0, "Pending": 0, "Failed": 0}
    total = len(candidates)
    
    for i, c in enumerate(candidates):
        res = process_thread_execution(driver, c)
        status = res.get("status", "Failed")
        stats[status] = stats.get(status, 0) + 1
        print_activity(i + 1, total, res)
        
    print_summary(total, stats)
    driver.quit()

if __name__ == "__main__":
    main()