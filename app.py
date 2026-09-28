import os
import sys
import threading
from pathlib import Path

from core.config import SignatureConfig, load_signature, profile_dir, save_signature
from core.browser import attach_driver, launch_browser
from core.signature import build_signature
from modules.auto_renewal import run_auto_renewal
from modules.cgc_checker import run_cgc_checker
from modules.renewal_checker import run_renewal_checker
from modules.valid_checker import run_valid_checker


def configure_tk_runtime():
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return

    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
    roots.extend((Path(sys.base_prefix), Path(sys.executable).parent))

    for root in roots:
        tcl_root = root / "tcl"
        tcl_candidates = sorted(tcl_root.glob("tcl8.*"))
        tk_candidates = sorted(tcl_root.glob("tk8.*"))
        if tcl_candidates and tk_candidates:
            os.environ.setdefault("TCL_LIBRARY", str(tcl_candidates[-1]))
            os.environ.setdefault("TK_LIBRARY", str(tk_candidates[-1]))
            return


configure_tk_runtime()

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


MODULES = {
    "Valid Checker": "Otomatis memvalidasi lisensi yang valid dan durasinya, serta menolak lisensi yang dibatalkan melalui portal.",
    "Auto Renewal": "Otomatis menemukan lisensi yang sudah kedaluwarsa dan mengirimkan pemberitahuan untuk proses renewal.",
    "Renewal Check": "Mengecek pemilik lisensi yang tidak merespons pengajuan renewal setelah diingatkan selama tiga hari, lalu menolaknya.",
    "CGC Checker": "Mengecek Certificate of Good Conduct yang sudah kedaluwarsa, memberi penanda expired, dan mengarsipkannya.",
}


class AutomationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LU Automation Engine")
        self.root.geometry("1080x700")
        self.root.minsize(920, 620)
        self.selected_module = tk.StringVar(value="Valid Checker")
        self.status_text = tk.StringVar(value="Ready")
        self.signature = load_signature()
        self.worker = None
        self.driver = None
        self.browser_process = None
        self.debug_port = None
        self.browser_state = "closed"
        self.stop_event = threading.Event()
        self.module_buttons = {}
        self.officer_entry = None
        self.data_directory = tk.StringVar()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._configure_style()
        self._build_layout()
        self._select_module("Valid Checker")
        self.root.after(1000, self._check_browser_session)

    def _configure_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#F5F7FA")
        style.configure("Sidebar.TFrame", background="#17212B")
        style.configure("Title.TLabel", background="#F5F7FA", foreground="#17212B", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background="#F5F7FA", foreground="#5B6875", font=("Segoe UI", 10))
        style.configure("SidebarTitle.TLabel", background="#17212B", foreground="#FFFFFF", font=("Segoe UI", 15, "bold"))
        style.configure("Sidebar.TButton", background="#17212B", foreground="#E7EDF3", anchor="w", padding=(16, 10), borderwidth=0)
        style.map("Sidebar.TButton", background=[("active", "#2C536F"), ("pressed", "#123D5B")], foreground=[("active", "#FFFFFF")])
        style.configure("SidebarActive.TButton", background="#2185C5", foreground="#FFFFFF", anchor="w", padding=(16, 10), borderwidth=0)
        style.map("SidebarActive.TButton", background=[("active", "#2F9BD8"), ("pressed", "#1769AA")], foreground=[("active", "#FFFFFF")])
        style.configure("Primary.TButton", background="#1769AA", foreground="#FFFFFF", padding=(18, 9), borderwidth=0, focuscolor="#1769AA")
        style.map("Primary.TButton", background=[("active", "#2185C5"), ("pressed", "#0F4F80"), ("disabled", "#A9C7DD")], foreground=[("active", "#FFFFFF"), ("disabled", "#FFFFFF")])
        style.configure("Danger.TButton", background="#C0392B", foreground="#FFFFFF", padding=(18, 9), borderwidth=0, focuscolor="#C0392B")
        style.map("Danger.TButton", background=[("active", "#E05245"), ("pressed", "#922B21"), ("disabled", "#D9AAA5")], foreground=[("active", "#FFFFFF"), ("disabled", "#FFFFFF")])
        style.configure("Secondary.TButton", background="#E7EEF5", foreground="#24445C", padding=(14, 8), borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#D3E3F1"), ("pressed", "#BED5E7")], foreground=[("active", "#17384F")])
        style.configure("Status.TLabel", background="#E8F5EE", foreground="#1D6B45", padding=8)
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure("Card.TLabel", background="#FFFFFF", foreground="#243B53")
        style.configure("Card.TLabelframe", background="#FFFFFF", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background="#FFFFFF", foreground="#17212B", font=("Segoe UI", 10, "bold"))

    def _build_layout(self):
        container = ttk.Frame(self.root, style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True)
        sidebar = ttk.Frame(container, width=250, style="Sidebar.TFrame")
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        ttk.Label(sidebar, text="LU Automation\nEngine", style="SidebarTitle.TLabel").pack(anchor="w", padx=20, pady=(28, 24))
        for name in MODULES:
            button = ttk.Button(sidebar, text=name, style="Sidebar.TButton", command=lambda item=name: self._select_module(item))
            button.pack(fill=tk.X, padx=10, pady=3)
            self.module_buttons[name] = button

        content = ttk.Frame(container, style="App.TFrame", padding=32)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        header = ttk.Frame(content, style="App.TFrame")
        header.pack(fill=tk.X)
        self.module_title = ttk.Label(header, style="Title.TLabel")
        self.module_title.pack(anchor="w")
        self.module_description = ttk.Label(header, style="Subtitle.TLabel", wraplength=760)
        self.module_description.pack(anchor="w", pady=(6, 18))

        self.settings = ttk.LabelFrame(content, text="Module settings", style="Card.TLabelframe", padding=16)
        self.settings.pack(fill=tk.X, pady=(0, 14))
        self.settings_grid = ttk.Frame(self.settings, style="Card.TFrame")
        self.settings_grid.pack(fill=tk.X)

        self.signature_frame = ttk.LabelFrame(content, text="Global signature", style="Card.TLabelframe", padding=16)
        self.signature_frame.pack(fill=tk.X, pady=(0, 14))
        self.position = self._field(self.signature_frame, "Staff position", self.signature.position, 0)
        self.staff_name = self._field(self.signature_frame, "Staff name", self.signature.staff_name, 1)
        self.image_url = self._field(self.signature_frame, "Signature image URL (optional)", self.signature.image_url, 2)
        ttk.Button(self.signature_frame, text="Preview signature", style="Secondary.TButton", command=self._preview_signature).grid(row=0, column=3, rowspan=3, padx=(18, 0), sticky="ns")

        controls = ttk.Frame(content, style="App.TFrame")
        controls.pack(fill=tk.X, pady=(0, 12))
        self.start_button = ttk.Button(controls, text="Open Login Browser", style="Primary.TButton", command=self._handle_start_click)
        self.start_button.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_button = ttk.Button(controls, text="Stop", style="Danger.TButton", command=self.stop, state="disabled")
        self.stop_button.pack(side=tk.LEFT)
        ttk.Label(controls, textvariable=self.status_text, style="Status.TLabel").pack(side=tk.RIGHT)

        self.log = tk.Text(content, height=14, state="disabled", background="#FFFFFF", foreground="#263746", relief=tk.FLAT, padx=12, pady=12, font=("Consolas", 10))
        self.log.pack(fill=tk.BOTH, expand=True)

    def _field(self, parent, label, value, row):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, width=62)
        entry.insert(0, value)
        entry.grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=3)
        parent.columnconfigure(1, weight=1)
        return entry

    def _select_module(self, name):
        self.selected_module.set(name)
        for module_name, button in self.module_buttons.items():
            button.configure(style="SidebarActive.TButton" if module_name == name else "Sidebar.TButton")
        self._update_start_button()
        if name == "Valid Checker":
            self.signature_frame.pack_forget()
        elif not self.signature_frame.winfo_manager():
            self.signature_frame.pack(fill=tk.X, pady=(0, 14), before=self.start_button.master)
        self.module_title.configure(text=name)
        self.module_description.configure(text=MODULES[name])
        for child in self.settings_grid.winfo_children():
            child.destroy()
        if name == "Valid Checker":
            self.officer_entry = self._field(self.settings_grid, "Issuing officer", "", 0)
            ttk.Label(self.settings_grid, text="Data directory", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=3)
            ttk.Entry(self.settings_grid, textvariable=self.data_directory, width=62, state="readonly").grid(row=1, column=1, sticky="ew", padx=(14, 0), pady=3)
            ttk.Button(self.settings_grid, text="Browse", style="Secondary.TButton", command=self._choose_directory).grid(row=1, column=2, padx=(8, 0), pady=3)
        else:
            self.officer_entry = None
            ttk.Label(self.settings_grid, text="Chrome profile: shared bot_profile", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=3)
            ttk.Label(self.settings_grid, text="Login is handled manually in Chrome.", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        self.status_text.set(f"{name} selected")

    def _update_start_button(self):
        if self.browser_state == "opening":
            text = "Opening Browser..."
        elif self.browser_state in {"ready", "running"}:
            text = "Start Automation"
        else:
            text = "Open Login Browser"
        self.start_button.configure(
            text=text,
            command=self._handle_start_click,
            state="disabled" if self.browser_state == "opening" else "normal",
        )

    def _driver_is_alive(self):
        if self.driver is None:
            return False
        try:
            self.driver.current_url
            return True
        except Exception:
            return False

    def _check_browser_session(self):
        browser_closed = (
            self.browser_process is None
            or self.browser_process.poll() is not None
        )
        if self.browser_state == "ready" and browser_closed:
            self.debug_port = None
            self.browser_state = "closed"
            self.stop_event.set()
            self.stop_button.configure(state="disabled")
            self._update_start_button()
            self.status_text.set("Chrome session closed")
            self._append_log("Chrome was closed. Click Open Login Browser to start a new session.")
        if self.root.winfo_exists():
            self.root.after(1000, self._check_browser_session)

    def _choose_directory(self):
        selected = filedialog.askdirectory(title="Select data directory")
        if selected:
            self.data_directory.set(selected)
            self.status_text.set("Data directory selected")

    def _preview_signature(self):
        config = SignatureConfig(self.position.get(), self.staff_name.get(), self.image_url.get())
        save_signature(config)
        self.signature = config
        messagebox.showinfo("Signature preview", build_signature(config))

    def _handle_start_click(self):
        try:
            self._append_log(
                f"Start clicked for {self.selected_module.get()} (browser state: {self.browser_state})."
            )
            if self.browser_state == "closed":
                self._start_browser_login()
            elif self.browser_state == "ready":
                self._start_automation()
            elif self.browser_state == "running":
                self._append_log("Automation is already running.")
        except Exception as exc:
            self.status_text.set("Unable to start automation")
            self._append_log(f"Start error: {type(exc).__name__}: {exc}")
            messagebox.showerror("Start error", str(exc))

    def _start_automation(self):
        self._append_log("Preparing automation worker...")
        if self.worker and self.worker.is_alive():
            self._append_log("A browser or automation operation is already in progress.")
            return
        if self.browser_state != "ready":
            self.browser_state = "closed"
            self._update_start_button()
            self._append_log("Chrome session is not ready. Click Open Login Browser first.")
            return
        try:
            self.driver = attach_driver(self.debug_port)
            page_info = self._get_browser_page_info()
        except Exception as exc:
            self.driver = None
            self._append_log(f"Unable to attach to Chrome: {type(exc).__name__}: {exc}")
            messagebox.showerror("Browser connection error", str(exc))
            return
        if page_info["challenge_detected"]:
            self.status_text.set("Complete browser verification first")
            self._append_log(
                "Automation blocked: human verification/login page is still active "
                f"(URL: {page_info['url']}, title: {page_info['title']})."
            )
            messagebox.showwarning(
                "Verification required",
                "Complete the human verification and login in Chrome, then click Start Automation again.",
            )
            return
        officer = self.officer_entry.get().strip() if self.officer_entry else ""
        data_directory = self.data_directory.get().strip()
        if self.browser_state == "ready" and self.selected_module.get() == "Valid Checker":
            if not officer or not data_directory:
                messagebox.showwarning("Missing settings", "Enter an issuing officer and choose a data directory.")
                return
            if not Path(data_directory).is_dir():
                messagebox.showerror("Invalid directory", "The selected data directory does not exist.")
                return
        self.signature = SignatureConfig(self.position.get(), self.staff_name.get(), self.image_url.get())
        save_signature(self.signature)
        self.stop_event.clear()
        self.browser_state = "running"
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        module_name = self.selected_module.get()
        self.worker = threading.Thread(
            target=self._run_selected_module,
            args=(module_name, officer, data_directory),
            daemon=True,
        )
        self.status_text.set(f"Starting {module_name}...")
        self._append_log(f"{module_name} runner starting.")
        self.worker.start()
        self._append_log(f"{module_name} worker started.")

    def _start_browser_login(self):
        if self.worker and self.worker.is_alive():
            self._append_log("A browser operation is already in progress.")
            return
        self.stop_event.clear()
        self.browser_state = "opening"
        self._update_start_button()
        self.stop_button.configure(state="normal")
        self.status_text.set("Opening Chrome for manual login...")
        self._append_log("Login browser opening...")
        self.worker = threading.Thread(target=self._open_browser, daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status_text.set("Stop requested")
        self._append_log("Stop requested; the active browser operation will finish first.")

    def _run_selected_module(self, module_name, officer, data_directory):
        driver = self.driver
        try:
            self.root.after(0, self._append_log, f"{module_name} runner is active.")
            callback = lambda index, total, result: self.root.after(
                0, self._handle_result, index, total, result
            )
            if module_name == "Valid Checker":
                summary = run_valid_checker(officer, data_directory, driver=driver, stop_event=self.stop_event, on_result=callback)
            elif module_name == "Auto Renewal":
                summary = run_auto_renewal(driver=driver, stop_event=self.stop_event, on_result=callback, signature_config=self.signature)
            elif module_name == "Renewal Check":
                summary = run_renewal_checker(driver=driver, stop_event=self.stop_event, on_result=callback, signature_config=self.signature)
            else:
                summary = run_cgc_checker(driver=driver, stop_event=self.stop_event, on_result=callback, signature_config=self.signature)
            self.root.after(0, self._finish_run, summary)
        except Exception as exc:
            self.root.after(0, self._finish_run, None, exc)
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
                self.driver = None
                self.browser_state = "closed"
            self._terminate_browser_process()
            self.root.after(0, self._update_start_button)

    def _open_browser(self):
        try:
            self.root.after(0, self._append_log, "Creating Selenium Chrome session...")
            process, port, profile = launch_browser()
            self.browser_process = process
            self.debug_port = port
            self.root.after(0, self._append_log, f"Chrome profile: {profile}")
            self.root.after(0, self._browser_started)
            if self.stop_event.is_set():
                process.terminate()
                self.browser_process = None
                self.debug_port = None
                self.browser_state = "closed"
                self.root.after(0, self._finish_run, {"stopped": True})
                return
            self.root.after(0, self._browser_ready)
        except Exception as exc:
            self.root.after(0, self._append_log, f"Chrome startup failed: {type(exc).__name__}: {exc}")
            self.browser_process = None
            self.debug_port = None
            self.browser_state = "closed"
            self.root.after(0, self._finish_run, None, exc)

    def _browser_started(self):
        self.status_text.set("Chrome opened. Complete verification and login manually...")
        self._append_log("Chrome process started successfully.")

    def _get_browser_page_info(self):
        try:
            url = self.driver.current_url
            title = self.driver.title
            source = self.driver.page_source[:50000].lower()
        except Exception:
            return {"url": "unavailable", "title": "unavailable", "challenge_detected": True}
        challenge_markers = (
            "verify you are human",
            "human verification",
            "checking your browser",
            "just a moment",
            "captcha",
        )
        login_page = "mode=login" in url.lower() or "login" in title.lower()
        challenge_detected = login_page or any(marker in f"{title} {source}" for marker in challenge_markers)
        return {"url": url, "title": title, "challenge_detected": challenge_detected}

    def _browser_ready(self):
        self.worker = None
        self.browser_state = "ready"
        self.start_button.configure(state="normal")
        self._update_start_button()
        self.stop_button.configure(state="disabled")
        self.status_text.set("Complete verification/login in Chrome")
        self._append_log(
            "Chrome is ready for manual verification/login. "
            "Complete it before clicking Start Automation."
        )

    def _handle_result(self, index, total, result):
        status = result.get("status", "Failed")
        title = result.get("final_title") or result.get("original_title") or result.get("name", "Unknown")
        self.status_text.set(f"Processed {index} / {total}: {status}")
        self._append_log(f"({index}/{total}) {status} - {title}")
        if result.get("reason"):
            self._append_log(f"  {result['reason']}")

    def _finish_run(self, summary, error=None):
        self.worker = None
        if error or summary is not None and summary.get("stopped"):
            self.browser_state = "closed"
        self.start_button.configure(state="normal")
        self._update_start_button()
        self.stop_button.configure(state="disabled")
        if error:
            self.status_text.set("Automation failed")
            self._append_log(f"Error: {type(error).__name__}: {error}")
            messagebox.showerror("Processing error", str(error))
            return
        if summary and summary.get("stopped"):
            self.status_text.set("Stopped")
            self._append_log("Valid Checker stopped.")
        else:
            stats = summary.get("stats", {}) if summary else {}
            self.status_text.set("Completed")
            self._append_log(f"Completed. Results: {stats}")

    def _append_log(self, message):
        self.log.configure(state="normal")
        self.log.insert(tk.END, f"{message}\n")
        self.log.configure(state="disabled")
        self.log.see(tk.END)

    def _close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Konfirmasi keluar", "Proses masih berjalan. Tutup aplikasi setelah operasi aktif selesai?"):
                return
            self.stop_event.set()
        save_signature(SignatureConfig(self.position.get(), self.staff_name.get(), self.image_url.get()))
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
        self._terminate_browser_process()
        self.root.destroy()

    def _terminate_browser_process(self):
        process = self.browser_process
        self.browser_process = None
        self.debug_port = None
        if process is not None and process.poll() is None:
            process.terminate()


def main():
    root = tk.Tk()
    AutomationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
