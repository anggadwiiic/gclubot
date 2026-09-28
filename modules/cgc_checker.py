"""GUI-independent Certificate of Good Conduct expiry checker."""

import re
import threading
import time
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from core.signature import signature_or_default
from core.timing import human_pause


FORUM_BASE = "https://police.san-andreas.net"
FORUM_MAP = {
    "516": {
        "type": "CGC",
        "name": "Certificate of Good Conduct",
        "archive_id": "522",
    }
}

EXPIRED_MESSAGE_TEMPLATE = """[divbox=#F1F1F1][center]
[img]https://i.imgur.com/iHky2fT.png[/img]
[b][size=125]Administrative Services Bureau - Gun Control and Licensing Unit[/size][/b]
[b][size=125]Certificate of Good Conduct[/size][/b]
[/center]
[hr][/hr]
[divbox=#20354C][color=white][center]Certificate of Good Conduct[/center][/color][/divbox]

Dear Mr./Mrs. {LAST_NAME},

This Certificate of Good Conduct (CGC) has been officially marked as [b][color=red]EXPIRED[/color][/b] and is no longer valid for any form of identification, verification, or administrative use. Any use of this document beyond its expiration date is considered invalid and will not be recognized by the issuing authority. The holder is advised to apply for a new Certificate of Good Conduct if continued authorization or verification is required.

[b]Note(s):[/b]
[list][*]This thread has been locked and archived.[/list]

{SIGNATURE}
[/divbox]"""


def destroy_cookie_banner(driver):
    try:
        driver.execute_script(
            "var b=document.querySelector('.cc-window');if(b)b.remove();"
            "var c=document.querySelector('[aria-label=\"cookieconsent\"]');if(c)c.remove();"
            "var d=document.getElementById('loading_indicator');if(d)d.remove();"
        )
    except Exception:
        pass


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


def snapshot_numeric_page_urls(driver):
    for attempt in range(2):
        try:
            return [
                link.get_attribute("href")
                for link in driver.find_elements(By.CSS_SELECTOR, ".pagination a.button")
                if link.text.isdigit()
            ]
        except StaleElementReferenceException:
            if attempt == 1:
                raise
            time.sleep(0.2)
    return []


def extract_cgc_name_from_title(title):
    clean_name = re.sub(r"\[CGC\]|\[SA-\d+\]", "", title, flags=re.IGNORECASE).strip()
    parts = clean_name.split()
    last_name = parts[-1] if parts else "Applicant"
    return clean_name, re.sub(r"[^a-zA-Z]", "", last_name)


def start_browser():
    """Create the engine browser, including its shared profile."""
    try:
        from ..core.browser import create_driver
    except ImportError:
        from core.browser import create_driver
    return create_driver()


def _move_to_archive(driver, archive_id, wait):
    tools = driver.find_elements(By.XPATH, "//a[contains(@title, 'Quick mod tools')]")
    if tools:
        driver.execute_script("arguments[0].click();", tools[0])
    move_link = wait.until(
        EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'action=move')]"))
    )
    driver.get(move_link.get_attribute("href"))
    destination = wait.until(EC.presence_of_element_located((By.NAME, "to_forum_id")))
    Select(destination).select_by_value(str(archive_id))
    try:
        shadow = driver.find_element(By.NAME, "move_leave_shadow")
        if shadow.is_selected():
            shadow.click()
    except Exception:
        pass
    driver.find_element(By.NAME, "confirm").click()


def process_cgc_execution(driver, candidate, stop_event=None, signature_config=None):
    event = stop_event or threading.Event()
    url = candidate["url"]
    original_title = candidate["title"]
    result = {
        "url": url,
        "original_title": original_title,
        "final_title": original_title,
        "section_name": candidate.get("section_name"),
    }
    if event.is_set():
        return {**result, "status": "Stopped"}

    wait = WebDriverWait(driver, 10)
    try:
        driver.get(url)
        destroy_cookie_banner(driver)
        if event.is_set():
            return {**result, "status": "Stopped"}

        if candidate["task"] == "AUTOFIX":
            _move_to_archive(driver, candidate["archive_id"], wait)
            result.update(
                status="Already processed",
                reason="Document was already EXPIRED but not moved. Relocated successfully.",
            )
            return result

        name_full, last_name = extract_cgc_name_from_title(original_title)
        new_title = f"[CGC] {name_full} [EXPIRED]"
        edit_buttons = driver.find_elements(By.XPATH, "//a[contains(@href, 'mode=edit')]")
        if edit_buttons:
            driver.execute_script("arguments[0].click();", edit_buttons[0])
            wait.until(EC.presence_of_element_located((By.NAME, "form_token")))
            subject = wait.until(EC.visibility_of_element_located((By.NAME, "subject")))
            subject.clear()
            subject.send_keys(new_title)
            human_pause(2.0, 3.0)
            driver.find_element(By.NAME, "post").click()
            human_pause(1.8, 2.8)
            if "submitted form was invalid" in driver.page_source.lower():
                result.update(
                    status="Failed",
                    reason="Form validation failed (submitted form was invalid).",
                )
                return result

        match = re.search(r"t=(\d+)", url)
        thread_id = match.group(1) if match else ""
        if event.is_set():
            return {**result, "status": "Stopped"}
        driver.get(f"{FORUM_BASE}/posting.php?mode=reply&t={thread_id}")
        destroy_cookie_banner(driver)
        wait.until(EC.presence_of_element_located((By.NAME, "form_token")))
        message = wait.until(EC.visibility_of_element_located((By.NAME, "message")))
        message.clear()
        message_text = EXPIRED_MESSAGE_TEMPLATE.replace("{LAST_NAME}", last_name)
        message.send_keys(message_text.replace("{SIGNATURE}", signature_or_default(signature_config)))
        human_pause(2.0, 3.0)
        driver.find_element(By.NAME, "post").click()
        human_pause(1.8, 2.8)
        if "submitted form was invalid" in driver.page_source.lower():
            result.update(
                status="Failed",
                reason="Form validation failed (submitted form was invalid).",
            )
            return result

        if event.is_set():
            return {**result, "status": "Stopped"}
        driver.get(url)
        destroy_cookie_banner(driver)
        _move_to_archive(driver, candidate["archive_id"], wait)
        driver.get(url)
        try:
            final_title = driver.find_element(By.CSS_SELECTOR, "h2.topic-title a").text
        except Exception:
            final_title = new_title
        result.update(
            status="Expired",
            final_title=final_title,
            reason=f"Validity period exceeded ({candidate['diff']} days ago).",
        )
        return result
    except Exception as exc:
        result.update(status="Failed", reason=f"Execution error: {type(exc).__name__}")
        return result


def discover_cgc_candidates(driver, stop_event=None):
    event = stop_event or threading.Event()
    candidates = []
    for forum_id, config in FORUM_MAP.items():
        if event.is_set():
            break
        driver.get(f"{FORUM_BASE}/viewforum.php?f={forum_id}")
        destroy_cookie_banner(driver)
        try:
            numeric_page_urls = snapshot_numeric_page_urls(driver)
            if numeric_page_urls:
                driver.get(numeric_page_urls[-1])
        except Exception:
            pass

        stop_scanning = False
        while not stop_scanning and not event.is_set():
            current_url = driver.current_url
            destroy_cookie_banner(driver)
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.topictitle"))
                )
            except Exception:
                pass
            threads = snapshot_topic_links(driver)
            for url, title in reversed(threads):
                if event.is_set():
                    break
                if "[CGC]" not in title.upper():
                    continue
                if "[EXPIRED]" in title.upper():
                    candidates.append(
                        {"url": url, "title": title, "task": "AUTOFIX",
                         "archive_id": config["archive_id"], "section_name": config["name"]}
                    )
                    continue
                driver.get(url)
                destroy_cookie_banner(driver)
                try:
                    page_urls = snapshot_numeric_page_urls(driver)
                    if page_urls:
                        driver.get(page_urls[-1])
                except Exception:
                    pass
                valid_date = None
                try:
                    posts = driver.find_elements(By.CSS_SELECTOR, ".post div.content")
                    for post in reversed(posts):
                        match = re.search(
                            r"Valid To:\s*(\d{1,2}/\d{1,2}/\d{4})", post.text, re.IGNORECASE
                        )
                        if match:
                            valid_date = datetime.strptime(match.group(1), "%d/%m/%Y")
                            break
                except Exception:
                    pass
                if not valid_date:
                    continue
                diff = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - valid_date).days
                if diff > 0:
                    candidates.append(
                        {"url": url, "title": title, "task": "EXPIRE",
                         "archive_id": config["archive_id"], "diff": diff, "section_name": config["name"]}
                    )
                else:
                    stop_scanning = True
                    break
            if stop_scanning or event.is_set():
                break
            driver.get(current_url)
            previous = None
            try:
                previous = driver.find_element(
                    By.XPATH, "//a[descendant::i[contains(@class, 'fa-chevron-left')]]"
                ).get_attribute("href")
            except Exception:
                try:
                    previous = driver.find_element(By.CSS_SELECTOR, "a[rel='prev']").get_attribute("href")
                except Exception:
                    pass
            if previous:
                driver.get(previous)
            else:
                break
    return candidates


def run_cgc_checker(stop_event=None, on_result=None, driver=None, signature_config=None):
    """Discover and process expired CGCs using the engine's shared browser."""
    event = stop_event or threading.Event()
    owned_driver = driver is None
    active_driver = driver or start_browser()
    results = []
    stats = {"Expired": 0, "Already processed": 0, "Pending": 0, "Failed": 0, "Stopped": 0}
    try:
        candidates = discover_cgc_candidates(active_driver, event)
        total = len(candidates)
        for index, candidate in enumerate(candidates, 1):
            if event.is_set():
                break
            result = process_cgc_execution(active_driver, candidate, event, signature_config)
            results.append(result)
            status = result.get("status", "Failed")
            stats[status] = stats.get(status, 0) + 1
            if on_result:
                on_result(index, total, result)
            if status == "Stopped":
                break
        return {"candidates": candidates, "results": results, "stats": stats, "stopped": event.is_set()}
    finally:
        if owned_driver:
            try:
                active_driver.quit()
            except Exception:
                pass
