"""Non-GUI Valid Checker workflow adapter.

Business rules intentionally mirror the legacy Valid Checker while exposing
callable functions for the LU Automation Engine UI.
"""
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
import time
import re
from datetime import timedelta
import logging
import warnings
import glob
import os
from core.timing import human_pause

warnings.filterwarnings("ignore")

# Configure Developer Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

FORUM_MAP = {"LT": {30: 156, 60: 915, 90: 779}, "HT": {30: 872, 60: 914, 90: 874}, "LL": 208, "IL": 869}
ARCHIVE_MAP = {"LT": 155, "HT": 875, "LL": 209, "IL": 868}
TYPE_FORMAT = {"HT": "Heavy Truck", "LT": "Trucking", "LL": "Lumberjack", "IL": "Impound"}
TYPE_MAPPING = {"HAULING": "HEAVY TRUCK", "TRUCKING": "LIGHT TRUCK", "LUMBERJACK": "LUMBERJACK", "IMPOUND": "IMPOUND", "SMALL FIREARMS": "SMALL FIREARMS"}

NEGATIVE_KEYWORDS = ["DENIED", "REVOKED", "REFUSED", "SUSPENDED", "CANCELED", "REJECTED", "ARCHIVED"]
HOLD_KEYWORDS = ["RENEWAL"]
FORUM_BASE = "https://police.san-andreas.net"

def read_data_smart(filepath):
    try:
        if filepath.endswith('.xlsx'):
            df = pd.read_excel(filepath)
            if 'Issued by' in df.columns: return df
    except (OSError, ValueError, ImportError) as exc:
        logging.warning("Unable to read XLSX file %s: %s", filepath, exc)
    
    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath, sep=';')
            if 'Issued by' in df.columns: return df
            df = pd.read_csv(filepath, sep=',')
            if 'Issued by' in df.columns: return df
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        logging.warning("Unable to read CSV file %s: %s", filepath, exc)
    
    return pd.DataFrame()

def load_all_data(folder_path, prefix):
    pattern_xlsx = os.path.join(folder_path, f"{prefix}*.xlsx")
    pattern_csv = os.path.join(folder_path, f"{prefix}*.csv")
    
    files = glob.glob(pattern_xlsx) + glob.glob(pattern_csv)
    if not files: return pd.DataFrame()
    
    df_list = []
    for filepath in files:
        data = read_data_smart(filepath)
        if not data.empty:
            df_list.append(data)
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

def get_candidates(target_officer, data_folder):
    df_lic = load_all_data(data_folder, "licenses")
    df_log = load_all_data(data_folder, "log")
    
    if df_lic.empty:
        return []
    
    df_lic.columns = df_lic.columns.str.strip()
    for col in ['Issued by', 'Status', 'Person']:
        if col in df_lic.columns: df_lic[col] = df_lic[col].astype(str).str.strip()
    
    mask = (df_lic['Issued by'].str.lower() == target_officer.lower()) & (df_lic['Status'].str.lower().isin(['done', 'cancelled']))
    df_targets = df_lic[mask]
    
    candidates = []
    
    if not df_log.empty:
        df_log.columns = df_log.columns.str.strip()
        for col in ['Person', 'Type']:
            if col in df_log.columns: df_log[col] = df_log[col].astype(str).str.strip()
        if 'License Type' in df_log.columns:
             df_log['License Type'] = df_log['License Type'].astype(str).str.strip().str.upper()

    for _, row in df_targets.iterrows():
        name = row['Person']
        status = row['Status'].lower()
        csv_lic_type = str(row['License Type']).strip().upper()
        
        raw_reason = str(row['Reason'])
        tid_match = re.search(r'[?&]t=(\d+)', raw_reason)
        pid_match = re.search(r'[?&]p=(\d+)', raw_reason)
        
        has_t = bool(tid_match)
        tid = int(tid_match.group(1)) if tid_match else None
        pid = int(pid_match.group(1)) if pid_match else None
        if not tid and not pid: continue

        lic_type_code = "UNKNOWN"
        target_forum_id = None
        target_archive_id = None
        
        if any(k in csv_lic_type for k in ["HAULING", "HEAVY"]):
            lic_type_code = "HT"
        elif any(k in csv_lic_type for k in ["TRUCKING", "LORRY", "LIGHT"]):
            lic_type_code = "LT"
        elif "LUMBERJACK" in csv_lic_type:
            lic_type_code = "LL"
        elif "IMPOUND" in csv_lic_type:
            lic_type_code = "IL"
            
        if lic_type_code != "UNKNOWN":
            target_archive_id = ARCHIVE_MAP.get(lic_type_code)

        if status == 'cancelled':
            candidates.append({
                "tid": tid, "pid": pid, "has_t": has_t, "name": name, 
                "task_type": "CANCELLED", "target_forum": target_archive_id, "lic_type_code": lic_type_code
            })
            continue 
            
        elif status == 'done':
            if df_log.empty: continue
                
            target_log_type = TYPE_MAPPING.get(csv_lic_type, "UNKNOWN")
            user_logs = df_log[(df_log['Person'].str.lower() == name.lower()) & 
                               (df_log['Type'].str.lower() == 'issue') &
                               (df_log['License Type'] == target_log_type)]
            
            if user_logs.empty: continue 

            try:
                clean_date = user_logs['Date & Time'].astype(str).str.replace('.', ':', regex=False)
                last_date = pd.to_datetime(clean_date, format='mixed', dayfirst=True, errors='coerce').max()
            except: continue

            if pd.isna(last_date): continue

            raw_dur = int(row['Duration']) if pd.notnull(row['Duration']) else 1
            final_days = raw_dur * 30 if raw_dur < 10 else raw_dur
            map_dur = 30 if final_days <= 45 else (60 if final_days <= 75 else 90)
            
            valid_str = (last_date + timedelta(days=final_days)).strftime("%d/%B/%Y").upper()
            
            if lic_type_code != "UNKNOWN":
                target_forum_id = FORUM_MAP[lic_type_code].get(map_dur) if lic_type_code in ["HT", "LT"] else FORUM_MAP[lic_type_code]
            
            if target_forum_id:
                candidates.append({
                    "tid": tid, "pid": pid, "has_t": has_t, "name": name, 
                    "task_type": "DONE", "valid_until": valid_str, 
                    "target_forum": target_forum_id, "duration": final_days
                })

    return candidates

def start_browser():
    """Create the shared browser using the engine browser service."""
    try:
        from ..core.browser import create_driver
    except ImportError:
        from core.browser import create_driver
    return create_driver()
def destroy_cookie(driver):
    try: driver.execute_script("var b=document.querySelector('.cc-window');if(b)b.remove();var c=document.querySelector('[aria-label=\"cookieconsent\"]');if(c)c.remove();")
    except: pass

def perform_move(driver, target_forum_id):
    if not target_forum_id: return
    move_url = None
    
    try:
        move_link = driver.find_elements(By.XPATH, "//a[contains(@href, 'action=move')]")
        if move_link: move_url = move_link[0].get_attribute("href")
        else:
            for xpath in ["//a[contains(@title, 'Quick mod tools')]", "//i[contains(@class, 'fa-gavel')]/..", "//i[contains(@class, 'fa-tools')]/.."]:
                elems = driver.find_elements(By.XPATH, xpath)
                if elems:
                    driver.execute_script("arguments[0].click();", elems[0])
                    human_pause(0.8, 1.3)
                    ml = driver.find_elements(By.XPATH, "//a[contains(@href, 'action=move')]")
                    if ml: move_url = ml[0].get_attribute("href")
                    break
    except: pass

    if move_url:
        try:
            driver.get(move_url)
            human_pause(1.6, 2.4)
            Select(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "to_forum_id")))).select_by_value(str(target_forum_id))
            try:
                shadow = driver.find_element(By.NAME, "move_leave_shadow")
                if shadow.is_selected(): shadow.click()
            except: pass
            for selector in [(By.NAME, "confirm"), (By.XPATH, "//input[@value='Yes']"), (By.NAME, "post")]:
                try:
                    driver.find_element(*selector).click()
                    human_pause(1.6, 2.4)
                    break
                except: pass
        except: pass

def resolve_pid(driver, pid):
    logging.info(f"Resolving thread ID from PID: {pid}")
    try:
        driver.get(f"{FORUM_BASE}/viewtopic.php?p={pid}")
        human_pause(1.6, 2.4)
        
        # 1. URL Resolution
        match = re.search(r'[?&]t=(\d+)', driver.current_url)
        if match: return int(match.group(1))
        
        # 2. Canonical Meta Tag
        try:
            canonical = driver.find_element(By.CSS_SELECTOR, "link[rel='canonical']").get_attribute("href")
            match = re.search(r'[?&]t=(\d+)', canonical)
            if match: return int(match.group(1))
        except: pass
        
        # 3. Post Breadcrumb or Subject Anchor
        try:
            links = driver.find_elements(By.CSS_SELECTOR, f"a[href*='p={pid}']")
            for link in links:
                match = re.search(r'[?&]t=(\d+)', link.get_attribute("href"))
                if match: return int(match.group(1))
        except: pass
        
        # 4. Page Body Internal Scan
        try:
            post_body = driver.find_element(By.ID, "page-body")
            match = re.search(r'viewtopic\.php\?(?:[^"\'&]*&)?t=(\d+)', post_body.get_attribute('innerHTML'))
            if match: return int(match.group(1))
        except: pass
        
        # 5. Last Resort Full Source Match
        match = re.search(r'viewtopic\.php\?(?:[^"\'&]*&)?t=(\d+)', driver.page_source)
        if match: return int(match.group(1))
        
        return None
    except: return None

def get_valid_date(text):
    if not text: return None
    match = re.search(r'VALID UNTIL\s+([0-9]{1,2}/[A-Z]+/[0-9]{4})', text.upper())
    return match.group(1).strip() if match else None

def repair_title(driver, thread_id, expected_date):
    driver.get(f"{FORUM_BASE}/viewtopic.php?t={thread_id}&start=0")
    human_pause(1.2, 1.8)
    try:
        posts = driver.find_elements(By.CSS_SELECTOR, ".post")
        if posts:
            edit_btn = posts[0].find_element(By.CSS_SELECTOR, "a[title='Edit post']")
            driver.execute_script("arguments[0].click();", edit_btn)
            human_pause(1.6, 2.4)
            
            box = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.NAME, "subject")))
            curr = box.get_attribute("value")
            
            if re.search(r'\[VALID UNTIL.*?\]', curr, flags=re.IGNORECASE):
                new_title = re.sub(r'\[VALID UNTIL.*?\]', f'[VALID UNTIL {expected_date}]', curr, flags=re.IGNORECASE)
            else:
                clean = re.sub(r'\[(RENEWAL|EXPIRED|ADMINISTRATION)\]', '', curr, flags=re.IGNORECASE).strip()
                clean = " ".join(clean.split())
                new_title = f"{clean} [VALID UNTIL {expected_date}]"
            
            box.clear()
            box.send_keys(new_title)
            destroy_cookie(driver)
            
            btn = driver.find_element(By.NAME, "post")
            driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn)
            human_pause(1.6, 2.4)
            return True
    except Exception as e:
        logging.error(f"Failed to repair title: {e}")
    return False

def repair_paid_response(driver, expected_date):
    try:
        posts = driver.find_elements(By.CSS_SELECTOR, ".post")
        for post in reversed(posts):
            try:
                content_div = post.find_element(By.CLASS_NAME, "content")
                text = content_div.text.upper()
                if "PAID" in text and "VALID UNTIL" in text:
                    edit_btn = post.find_element(By.CSS_SELECTOR, "a[title='Edit post']")
                    driver.execute_script("arguments[0].click();", edit_btn)
                    human_pause(1.6, 2.4)
                    
                    box = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.NAME, "message")))
                    msg = f"[divbox=white] [center][color=green][b][size=200]PAID[/size][/b][/color][/center][/divbox]\n[divbox=white][b][center]VALID UNTIL {expected_date}[/center][/b][/divbox]"
                    box.clear()
                    box.send_keys(msg)
                    
                    destroy_cookie(driver)
                    btn = driver.find_element(By.NAME, "post")
                    driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn)
                    human_pause(1.6, 2.4)
                    return True
            except: continue
    except Exception as e:
        logging.error(f"Failed to repair paid response post: {e}")
    return False

def post_new_paid_response(driver, expected_date):
    try:
        msg = f"[divbox=white] [center][color=green][b][size=200]PAID[/size][/b][/color][/center][/divbox]\n[divbox=white][b][center]VALID UNTIL {expected_date}[/center][/b][/divbox]"
        box = driver.find_element(By.NAME, "message")
        box.clear()
        box.send_keys(msg)
        destroy_cookie(driver)
        btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit'][name='post']")
        driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn)
        human_pause(2.4, 3.2)
        return True
    except Exception as e:
        logging.error(f"Failed to post new paid response: {e}")
    return False

def process_cancelled_thread(driver, c, stop_event, is_already_denied):
    driver.get(f"{FORUM_BASE}/viewtopic.php?t={c['real_tid']}&start=0")
    human_pause(1.6, 2.4)
    if stop_event.is_set(): return {"status": "Stopped"}
    
    try:
        posts = driver.find_elements(By.CSS_SELECTOR, ".post")
        if posts:
            edit_btn = posts[0].find_element(By.CSS_SELECTOR, "a[title='Edit post']")
            driver.execute_script("arguments[0].click();", edit_btn)
            human_pause(1.6, 2.4)
            
            box = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.NAME, "subject")))
            curr_subj = box.get_attribute("value").upper()
            
            if "[DENIED]" not in curr_subj:
                clean_subj = re.sub(r'\[(RENEWAL|EXPIRED|ADMINISTRATION)\]', '', box.get_attribute("value"), flags=re.IGNORECASE).strip()
                clean_subj = " ".join(clean_subj.split())
                box.clear()
                box.send_keys(f"{clean_subj} [DENIED]")
                destroy_cookie(driver)
                btn = driver.find_element(By.NAME, "post")
                driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn)
                human_pause(1.6, 2.4)
    except Exception as e:
        logging.error(f"Error modifying title for cancelled thread: {e}")

    if stop_event.is_set(): return {"status": "Stopped"}

    if not is_already_denied:
        driver.get(f"{FORUM_BASE}/viewtopic.php?t={c['real_tid']}&start=999999")
        human_pause(1.6, 2.4)
        
        full_name = c.get('name', 'Applicant')
        last_name = full_name.split()[-1] if len(full_name.split()) > 1 else full_name
        lic_format = TYPE_FORMAT.get(c['lic_type_code'], "License")
        
        bbcode_msg = (
            f"[divbox=#F1F1F1][center]\n"
            f"[img]https://i.imgur.com/iHky2fT.png[/img]\n"
            f"[b][size=125]Administrative Services Bureau - Gun Control and Licensing Unit[/size][/b]\n"
            f"[b][size=125]License Application Response[/size][/b][/center]\n"
            f"[hr][/hr]\n"
            f"[divbox=#20354C][color=white][center]{lic_format} License[/center][/color][/divbox]\n\n"
            f"Dear Mr./Mrs. {last_name},\n\n"
            f"We've reviewed your application and your record, and after a long deliberation, we'd like to inform you that your application has been [b]DENIED[/b] because of the following reason:\n\n"
            f"[b]Reason(s):[/b]\n"
            f"[list][*] Didn't complete administration within 3 days[/list]\n\n"
            f"[b]Note(s):[/b]\n"
            f"[list][*] You can create a new form[/list]\n"
            f"[/divbox]"
        )
        try:
            msg_box = driver.find_element(By.NAME, "message")
            msg_box.clear()
            msg_box.send_keys(bbcode_msg)
            destroy_cookie(driver)
            btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit'][name='post']")
            driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", btn)
            human_pause(2.4, 3.2)
        except Exception as exc:
            logging.error("Failed to post denial response for %s: %s", full_name, exc, exc_info=True)
            return {
                "status": "Failed",
                "name": full_name,
                "reason": f"Denial response failed: {type(exc).__name__}",
            }
            
    perform_move(driver, c['target_forum'])
    return {
        "status": "Denied",
        "detail": "Administration deadline exceeded"
    }

def process_thread(driver, c, stop_event):
    if stop_event.is_set(): return {"status": "Stopped"}

    applicant_name = c.get('name', 'Unknown Applicant')
    expected_date = c.get('valid_until')
    task_type = c.get('task_type')
    pid = c.get('pid')

    # Data Safety Boundary
    if task_type == 'DONE' and not expected_date:
        return {
            "status": "Failed",
            "name": applicant_name,
            "expected_date": "N/A",
            "pid": pid,
            "reason": "Missing expected valid_until date in source data."
        }
    
    c['real_tid'] = c['tid'] if c['has_t'] else resolve_pid(driver, pid)
    if not c.get('real_tid'): 
        return {
            "status": "Failed", 
            "name": applicant_name,
            "expected_date": expected_date if expected_date else "N/A",
            "pid": pid,
            "reason": "Unable to resolve thread ID from PID"
        }

    url = f"{FORUM_BASE}/viewtopic.php?t={c['real_tid']}"
    
    try: 
        driver.get(url + "&start=999999")
        human_pause(1.6, 2.4)
    except Exception as e: 
        return {
            "status": "Failed", 
            "name": applicant_name,
            "expected_date": expected_date if expected_date else "N/A",
            "url": url,
            "reason": f"Unable to load forum thread URL: {e}"
        }
        
    destroy_cookie(driver)
    
    # 1. Capture Original State
    try:
        title_elem = driver.find_element(By.CSS_SELECTOR, "h2.topic-title a")
        original_title = title_elem.text
    except:
        original_title = driver.title.split(" - ")[0] if " - " in driver.title else applicant_name

    original_title_date = get_valid_date(original_title)
    
    posts = driver.find_elements(By.CLASS_NAME, "post")
    is_paid = False
    original_post_date = None
    last_text = ""

    if posts:
        try:
            last_text = posts[-1].find_element(By.CLASS_NAME, "content").text.upper()
        except: pass
    
    for post in reversed(posts):
        try:
            content_div = post.find_element(By.CLASS_NAME, "content")
            p_text = content_div.text.upper()
            if "PAID" in p_text and "VALID UNTIL" in p_text:
                is_paid = True
                original_post_date = get_valid_date(p_text)
                break
        except: continue

    is_already_denied = "DENIED" in last_text

    # 2. Cancelled Flow
    if task_type == "CANCELLED":
        if is_paid:
            return {
                "status": "Pending", 
                "name": applicant_name,
                "expected_date": "N/A",
                "original_title": original_title,
                "url": url,
                "reason": "Payment detected on cancelled application\nManual review required"
            }
        
        res_status = process_cancelled_thread(driver, c, stop_event, is_already_denied)
        if stop_event.is_set(): return {"status": "Stopped"}

        # Get After State
        driver.get(url + "&start=999999")
        human_pause(1.6, 2.4)
        try:
            final_title = driver.find_element(By.CSS_SELECTOR, "h2.topic-title a").text
        except:
            final_title = original_title + " [DENIED]"
            
        return {
            "status": res_status["status"],
            "name": applicant_name,
            "expected_date": "N/A",
            "original_title": original_title,
            "final_title": final_title,
            "url": url,
            "reason": res_status["detail"]
        }

    # 3. Done Task Flow
    if not is_paid and any(k in last_text for k in NEGATIVE_KEYWORDS + HOLD_KEYWORDS):
        return {
            "status": "Pending", 
            "name": applicant_name,
            "expected_date": expected_date,
            "original_title": original_title,
            "url": url,
            "reason": "Conflicting status detected\nManual review required"
        }

    title_correct = (original_title_date == expected_date)
    post_correct = (original_post_date == expected_date)

    if title_correct and post_correct:
        perform_move(driver, c['target_forum'])
        return {
            "status": "Verified", 
            "name": applicant_name,
            "expected_date": expected_date,
            "original_title": original_title,
            "final_title": original_title,
            "original_post_date": original_post_date,
            "final_post_date": original_post_date,
            "url": url
        }
    
    # 4. Correct/Repair State
    if not title_correct:
        repair_title(driver, c['real_tid'], expected_date)
        if stop_event.is_set(): return {"status": "Stopped"}

    if not post_correct:
        driver.get(url + "&start=999999")
        human_pause(1.2, 1.8)
        if is_paid:
            repair_paid_response(driver, expected_date)
        else:
            post_new_paid_response(driver, expected_date)
        if stop_event.is_set(): return {"status": "Stopped"}

    # 5. Mandatory Post-Repair Verification
    driver.get(url + "&start=999999")
    human_pause(1.6, 2.4)
    
    try:
        final_title = driver.find_element(By.CSS_SELECTOR, "h2.topic-title a").text
    except:
        final_title = original_title
        
    final_title_date = get_valid_date(final_title)

    new_posts = driver.find_elements(By.CLASS_NAME, "post")
    final_post_date = None
    
    for post in reversed(new_posts):
        try:
            content_div = post.find_element(By.CLASS_NAME, "content")
            p_text = content_div.text.upper()
            if "PAID" in p_text and "VALID UNTIL" in p_text:
                final_post_date = get_valid_date(p_text)
                break
        except: continue

    final_title_correct = (final_title_date == expected_date)
    final_post_correct = (final_post_date == expected_date)

    perform_move(driver, c['target_forum'])

    res_dict = {
        "name": applicant_name,
        "expected_date": expected_date,
        "original_title": original_title,
        "final_title": final_title,
        "original_post_date": original_post_date,
        "final_post_date": final_post_date,
        "url": url
    }

    if final_title_correct and final_post_correct:
        res_dict["status"] = "Corrected"
    else:
        res_dict["status"] = "Failed"
        res_dict["reason"] = f"Verification failed after repair attempt.\nThread Title Date: {final_title_date if final_title_date else 'Not found'}\nPaid Reply Body Date: {final_post_date if final_post_date else 'Not found'}"
        
    return res_dict


def run_valid_checker(target_officer, data_folder, driver=None, stop_event=None, on_result=None):
    """Process Valid Checker candidates without owning any GUI state.

    ``stop_event`` may be shared with the application; it is checked before
    and between records by ``process_thread``.  ``on_result`` receives
    ``(index, total, result)`` after each processed record.
    """
    import threading

    event = stop_event or threading.Event()
    candidates = get_candidates(target_officer, data_folder)
    owned_driver = driver is None
    active_driver = driver or start_browser()
    stats = {"Verified": 0, "Corrected": 0, "Denied": 0, "Pending": 0, "Failed": 0}
    results = []

    try:
        total = len(candidates)
        for index, candidate in enumerate(candidates, 1):
            if event.is_set():
                break
            try:
                result = process_thread(active_driver, candidate, event)
            except Exception as exc:
                logging.error("Unexpected error processing %s: %s", candidate.get("name", "Unknown"), exc, exc_info=True)
                result = {
                    "name": candidate.get("name", "Unknown Applicant"),
                    "status": "Failed",
                    "expected_date": candidate.get("valid_until", "N/A"),
                    "reason": f"Unexpected Exception: {type(exc).__name__}",
                    "url": None,
                }
            results.append(result)
            status = result.get("status", "Failed")
            stats[status] = stats.get(status, 0) + 1
            if on_result:
                on_result(index, total, result)
            if result.get("status") == "Stopped":
                break
        return {"candidates": candidates, "results": results, "stats": stats, "stopped": event.is_set()}
    finally:
        if owned_driver:
            try:
                active_driver.quit()
            except Exception:
                pass
