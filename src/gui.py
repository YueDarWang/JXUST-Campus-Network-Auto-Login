"""GUI - 系统托盘 + 设置窗口"""
import os
import sys
import time
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from PIL import Image, ImageDraw
import pystray

from .config import (
    load_config, save_config, get_password, set_password,
    get_auto_start, set_auto_start, APP_NAME, CONFIG_DIR,
)
from .network import NetworkMonitor, NetworkState
from .login import LoginEngine


# ── 图标生成 ────────────────────────────────────

def make_icon(color):
    """生成指定颜色的圆形图标"""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color, outline=(255, 255, 255, 200), width=3,
    )
    return img


ICON_GREEN = make_icon((76, 175, 80))
ICON_RED = make_icon((244, 67, 54))
ICON_YELLOW = make_icon((255, 193, 7))


# ── 主窗口 ──────────────────────────────────────

class CampusNetApp:
    def __init__(self):
        self.cfg = load_config()
        self.log_queue = queue.Queue()
        self.log_lines = []

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("560x480")
        self.root.minsize(480, 400)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_app_icon()

        self._setup_style()
        self._build_ui()
        self._setup_monitor()

        self._update_tray_icon(ICON_YELLOW)

        # 定时刷新 UI
        self.root.after(500, self._poll)

    # ── 样式 ──────────────────────────────────

    def _setup_style(self):
        style = ttk.Style()
        available = style.theme_names()
        if "clam" in available:
            style.theme_use("clam")
        elif "vista" in available:
            style.theme_use("vista")

        style.configure("TNotebook", padding=0)
        style.configure("TFrame", background="#f0f0f0")
        style.configure("Status.TLabel", font=("Microsoft YaHei", 14, "bold"))
        style.configure("Title.TLabel", font=("Microsoft YaHei", 11, "bold"))

    def _set_app_icon(self):
        try:
            ico_path = os.path.join(CONFIG_DIR, "app.ico")
            if not os.path.exists(ico_path):
                self._generate_ico(ico_path)
            self.root.iconbitmap(ico_path)
        except Exception:
            pass

    def _generate_ico(self, path):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(33, 150, 243), outline=(255, 255, 255, 200), width=3)
        img.save(path, format="ICO", sizes=[(64, 64)])

    # ── UI 构建 ───────────────────────────────

    def _build_ui(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        self.tab_status = ttk.Frame(nb)
        self.tab_settings = ttk.Frame(nb)
        self.tab_logs = ttk.Frame(nb)

        nb.add(self.tab_status, text="  状态  ")
        nb.add(self.tab_settings, text="  设置  ")
        nb.add(self.tab_logs, text="  日志  ")

        self._build_status_tab()
        self._build_settings_tab()
        self._build_logs_tab()

    # ── 状态页 ────────────────────────────────

    def _build_status_tab(self):
        f = self.tab_status
        f.columnconfigure(0, weight=1)

        # 状态画布
        self.status_canvas = tk.Canvas(f, width=80, height=80, bg="#f0f0f0",
                                       highlightthickness=0)
        self.status_canvas.grid(row=0, column=0, pady=(40, 10))
        self._status_circle = self.status_canvas.create_oval(
            15, 15, 65, 65, fill="#999", outline=""
        )

        self.status_label = ttk.Label(f, text="初始化中...", style="Status.TLabel")
        self.status_label.grid(row=1, column=0, pady=(0, 5))

        self.status_detail = ttk.Label(f, text="", foreground="#666")
        self.status_detail.grid(row=2, column=0)

        self.last_check_label = ttk.Label(f, text="", foreground="#888")
        self.last_check_label.grid(row=3, column=0, pady=(15, 3))

        self.last_login_label = ttk.Label(f, text="", foreground="#888")
        self.last_login_label.grid(row=4, column=0)

        ttk.Button(f, text="立即重连", command=self._reconnect_now).grid(
            row=5, column=0, pady=(25, 10),
        )

    # ── 设置页 ────────────────────────────────

    def _build_settings_tab(self):
        f = self.tab_settings
        f.columnconfigure(1, weight=1)

        row = 0

        # 账号
        ttk.Label(f, text="账号:", style="Title.TLabel").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=(20, 5),
        )
        self.entry_user = ttk.Entry(f, width=30)
        self.entry_user.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=(20, 5))
        self.entry_user.insert(0, self.cfg.get("username", ""))
        row += 1

        # 密码
        ttk.Label(f, text="密码:", style="Title.TLabel").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=5,
        )
        self.entry_pass = ttk.Entry(f, width=30, show="•")
        self.entry_pass.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=5)
        self.entry_pass.insert(0, get_password(self.cfg))
        row += 1

        # 运营商
        ttk.Label(f, text="运营商:", style="Title.TLabel").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=5,
        )
        self.carrier_var = tk.StringVar(value="")
        self.carrier_combo = ttk.Combobox(
            f, textvariable=self.carrier_var, state="readonly", width=27,
        )
        self.carrier_combo.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=5)
        self._populate_carrier()
        row += 1

        # 检测间隔
        ttk.Label(f, text="检测间隔(秒):", style="Title.TLabel").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=5,
        )
        interval_frame = ttk.Frame(f)
        interval_frame.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=5)
        self.scale_interval = ttk.Scale(
            interval_frame, from_=30, to=600, orient="horizontal",
            command=self._on_scale_change,
        )
        self.scale_interval.set(self.cfg.get("check_interval", 60))
        self.scale_interval.pack(side="left", fill="x", expand=True)
        self.interval_label = ttk.Label(interval_frame, width=5)
        self.interval_label.pack(side="left", padx=(10, 0))
        self._on_scale_change(None)
        row += 1

        # 开机自启
        ttk.Label(f, text="开机自启:", style="Title.TLabel").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=5,
        )
        self.var_autostart = tk.BooleanVar(value=get_auto_start())
        ttk.Checkbutton(f, variable=self.var_autostart).grid(
            row=row, column=1, sticky="w", padx=(0, 20), pady=5,
        )
        row += 1

        # 分隔
        ttk.Separator(f, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=20, pady=10,
        )
        row += 1

        # 高级设置标签
        ttk.Label(f, text="── 高级设置 ──", foreground="#888").grid(
            row=row, column=0, columnspan=2, pady=(5, 10),
        )
        row += 1

        # 门户 URL
        ttk.Label(f, text="门户 URL:").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=3,
        )
        self.entry_portal = ttk.Entry(f, width=30)
        self.entry_portal.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=3)
        self.entry_portal.insert(0, self.cfg.get("portal_url", ""))
        row += 1

        # 测试 URL
        ttk.Label(f, text="测试 URL:").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=3,
        )
        self.entry_test = ttk.Entry(f, width=30)
        self.entry_test.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=3)
        self.entry_test.insert(0, self.cfg.get("test_url", ""))
        row += 1

        # 登录 API
        ttk.Label(f, text="登录 API:").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=3,
        )
        self.entry_login_api = ttk.Entry(f, width=30)
        self.entry_login_api.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=3)
        self.entry_login_api.insert(0, self.cfg.get("login_api", ""))
        row += 1

        # 注销 API
        ttk.Label(f, text="注销 API:").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=3,
        )
        self.entry_logout_api = ttk.Entry(f, width=30)
        self.entry_logout_api.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=3)
        self.entry_logout_api.insert(0, self.cfg.get("logout_api", ""))
        row += 1

        # 流量阈值
        ttk.Label(f, text="流量阈值(KB/s):").grid(
            row=row, column=0, sticky="e", padx=(20, 10), pady=3,
        )
        self.entry_traffic = ttk.Entry(f, width=10)
        self.entry_traffic.grid(row=row, column=1, sticky="w", padx=(0, 20), pady=3)
        self.entry_traffic.insert(0, str(self.cfg.get("traffic_threshold_kbps", 100)))
        row += 1

        # 保存按钮
        ttk.Button(f, text="保存设置", command=self._save_settings).grid(
            row=row, column=0, columnspan=2, pady=(20, 20),
        )

    def _on_scale_change(self, val):
        v = int(float(self.scale_interval.get()))
        self.interval_label.config(text=f"{v}s")

    def _populate_carrier(self):
        """填充运营商下拉框"""
        # 从浏览器抓包确认的实际运营商
        carriers = [
            {"id": "3", "name": "校园网", "suffix": ""},
            {"id": "1", "name": "移动", "suffix": "@cmccyt"},
            {"id": "2", "name": "联通", "suffix": "@unicomyt"},
            {"id": "0", "name": "电信", "suffix": "@telecomyt"},
        ]

        values = []
        current_idx = 0
        saved_id = self.cfg.get("carrier_id", "3")
        for i, c in enumerate(carriers):
            label = f"{c['name']} (id={c['id']}, 后缀={c['suffix'] or '无'})"
            values.append(label)
            if str(c.get("id")) == str(saved_id):
                current_idx = i

        self.carrier_combo["values"] = values
        self._carrier_data = carriers
        if values:
            self.carrier_combo.current(current_idx)

    # ── 日志页 ────────────────────────────────

    def _build_logs_tab(self):
        f = self.tab_logs
        f.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1)

        self.log_text = tk.Text(f, wrap="word", state="disabled",
                                font=("Consolas", 9), bg="#1e1e1e",
                                fg="#d4d4d4", relief="flat",
                                borderwidth=0, padx=8, pady=8)
        self.log_text.grid(row=0, column=0, columnspan=2, sticky="nsew",
                           padx=10, pady=(10, 5))

        scrollbar = ttk.Scrollbar(f, command=self.log_text.yview)
        scrollbar.grid(row=0, column=2, sticky="ns", pady=(10, 5))
        self.log_text.config(yscrollcommand=scrollbar.set)

        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="w",
                       padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="清空", command=self._clear_logs).pack(side="left", padx=(0, 5))
        ttk.Button(btn_frame, text="复制", command=self._copy_logs).pack(side="left")

    def _clear_logs(self):
        self.log_lines.clear()
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _copy_logs(self):
        text = "\n".join(self.log_lines)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # ── 网络监控 ──────────────────────────────

    def _setup_monitor(self):
        self.monitor = NetworkMonitor(self.cfg, log_func=self._log)
        self.monitor.state_changed = self._on_state_change
        self.engine = LoginEngine(self.cfg, log_func=self._log)
        self._reconnecting = False
        self._reconnect_lock = threading.Lock()
        self._consecutive_failures = 0

    def _on_state_change(self, state):
        self.root.after(0, lambda: self._handle_state(state))

    def _handle_state(self, state):
        states_cn = {
            NetworkState.CONNECTED: "已连接",
            NetworkState.LOGGED_OUT: "离线",
            NetworkState.LOGGED_IN_NO_NET: "离线",
            NetworkState.NO_NETWORK: "网络断开",
            NetworkState.CHECKING: "检测中...",
            NetworkState.UNKNOWN: "未知",
        }
        colors = {
            NetworkState.CONNECTED: "#4CAF50",
            NetworkState.LOGGED_OUT: "#FF9800",
            NetworkState.LOGGED_IN_NO_NET: "#FF9800",
            NetworkState.NO_NETWORK: "#F44336",
            NetworkState.CHECKING: "#FFC107",
            NetworkState.UNKNOWN: "#999",
        }

        text = states_cn.get(state, state)
        color = colors.get(state, state)
        self.status_label.config(text=text)
        self.status_detail.config(text="")
        self.status_canvas.itemconfig(self._status_circle, fill=color)

        self._update_tray_icon({
            NetworkState.CONNECTED: ICON_GREEN,
            NetworkState.CHECKING: ICON_YELLOW,
        }.get(state, ICON_RED))

        # 离线时自动重连（有并发保护）
        if state in (NetworkState.LOGGED_OUT, NetworkState.LOGGED_IN_NO_NET):
            if not self._reconnecting:
                threading.Thread(
                    target=self._do_reconnect, args=(state,), daemon=True
                ).start()

    def _do_reconnect(self, state):
        # 并发保护：同一时间只允许一个重连流程
        with self._reconnect_lock:
            if self._reconnecting:
                return
            self._reconnecting = True

        try:
            if self.monitor.is_traffic_high():
                self._log("流量过高，延迟重连以免影响当前网络活动")
                return

            # 连续失败时退避等待
            if self._consecutive_failures > 0:
                backoff = min(10 * (2 ** (self._consecutive_failures - 1)), 120)
                self._log(f"连续失败 {self._consecutive_failures} 次，等待 {backoff}s 后重试")
                time.sleep(backoff)

            self._log(f"触发自动重连: {state}")

            if state == NetworkState.LOGGED_IN_NO_NET:
                self._log("正在注销...")
                self.engine.logout()
                time.sleep(2)

            self._log("正在登录...")
            success = self.engine.login()
            retries = 0
            max_retries = self.cfg.get("max_retries", 3) - 1

            while not success and retries < max_retries:
                retries += 1
                time.sleep(3)
                self._log(f"重试 {retries}/{max_retries}...")
                success = self.engine.login()

            if success:
                self._consecutive_failures = 0
                self.monitor.mark_login_success()
                self._log("重连成功!")
                self._notify("校园网已重新连接")
            else:
                self._consecutive_failures += 1
                self._log(f"重连失败 (连续 {self._consecutive_failures} 次)")
            self.root.after(0, lambda: self._refresh_status())
        finally:
            self._reconnecting = False

    def _reconnect_now(self):
        threading.Thread(target=self._reconnect_thread, daemon=True).start()

    def _reconnect_thread(self):
        with self._reconnect_lock:
            if self._reconnecting:
                self._log("已有重连进行中，请稍后")
                return
            self._reconnecting = True

        try:
            self._log("手动重连...")
            self.engine.logout()
            time.sleep(2)
            if self.engine.login():
                self._consecutive_failures = 0
                self.monitor.mark_login_success()
                self._log("手动重连成功!")
            else:
                self._log("手动重连失败")
        finally:
            self._reconnecting = False
            self.root.after(0, lambda: self._refresh_status())

    def _refresh_status(self):
        """仅刷新 UI 显示和检测计时器，不触发新的重连"""
        state = self.monitor.check_now()
        # 直接更新 UI，不走 _handle_state 以避免触发新重连
        if state == NetworkState.CONNECTED:
            text, color = "已连接", "#4CAF50"
            self._update_tray_icon(ICON_GREEN)
        elif state in (NetworkState.LOGGED_OUT, NetworkState.LOGGED_IN_NO_NET):
            text, color = "离线", "#FF9800"
            self._update_tray_icon(ICON_RED)
        elif state == NetworkState.NO_NETWORK:
            text, color = "网络断开", "#F44336"
            self._update_tray_icon(ICON_RED)
        else:
            text, color = "检测中...", "#FFC107"
            self._update_tray_icon(ICON_YELLOW)
        self.status_label.config(text=text)
        self.status_canvas.itemconfig(self._status_circle, fill=color)
        self._log(f"连接状态: {text}")
        self.monitor.reset_timer()

    # ── 系统托盘 ──────────────────────────────

    def _update_tray_icon(self, icon):
        if hasattr(self, "_tray_icon") and self._tray_icon:
            self._tray_icon.icon = icon

    def _create_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", self._show_window, default=True),
            pystray.MenuItem("立即重连", self._reconnect_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "开机自启",
                self._toggle_autostart,
                checked=lambda item: get_auto_start(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._quit_app),
        )
        self._tray_icon = pystray.Icon(
            APP_NAME, ICON_YELLOW, APP_NAME, menu,
        )

    def _show_window(self):
        self.root.after(0, self._do_show_window)

    def _do_show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _toggle_autostart(self):
        current = get_auto_start()
        new = not current
        set_auto_start(new)
        self.var_autostart.set(new)
        self._save_settings()

    def _notify(self, msg):
        if hasattr(self, "_tray_icon") and self._tray_icon:
            self._tray_icon.notify(msg, APP_NAME)

    # ── 设置保存 ──────────────────────────────

    def _save_settings(self):
        self.cfg["username"] = self.entry_user.get()
        set_password(self.cfg, self.entry_pass.get())

        # 运营商
        idx = self.carrier_combo.current()
        if idx >= 0 and hasattr(self, "_carrier_data") and idx < len(self._carrier_data):
            self.cfg["carrier_id"] = self._carrier_data[idx].get("id", "")
            self.cfg["carrier_suffix"] = self._carrier_data[idx].get("suffix", "")

        self.cfg["check_interval"] = int(float(self.scale_interval.get()))
        self.cfg["portal_url"] = self.entry_portal.get()
        self.cfg["test_url"] = self.entry_test.get()
        self.cfg["login_api"] = self.entry_login_api.get()
        self.cfg["logout_api"] = self.entry_logout_api.get()

        try:
            self.cfg["traffic_threshold_kbps"] = int(self.entry_traffic.get())
        except ValueError:
            self.cfg["traffic_threshold_kbps"] = 100

        save_config(self.cfg)
        set_auto_start(self.var_autostart.get())
        self.monitor.cfg = self.cfg
        self.engine.cfg = self.cfg
        self._log("设置已保存")
        messagebox.showinfo("提示", "设置已保存")

    # ── 日志 ──────────────────────────────────

    def _log(self, msg):
        t = time.strftime("%H:%M:%S")
        line = f"[{t}] {msg}"
        self.log_lines.append(line)
        self.log_queue.put(line)

    def _poll(self):
        while not self.log_queue.empty():
            try:
                line = self.log_queue.get_nowait()
                self.log_text.config(state="normal")
                self.log_text.insert("end", line + "\n")
                self.log_text.see("end")
                self.log_text.config(state="disabled")
                if len(self.log_lines) > 500:
                    self.log_lines[:100] = []
            except queue.Empty:
                break

        if self.monitor.last_check:
            lt = time.strftime("%Y-%m-%d %H:%M:%S",
                               time.localtime(self.monitor.last_check))
            self.last_check_label.config(text=f"上次检测: {lt}")
        if self.monitor.last_login:
            lt = time.strftime("%Y-%m-%d %H:%M:%S",
                               time.localtime(self.monitor.last_login))
            self.last_login_label.config(text=f"上次登录: {lt}")

        self.root.after(500, self._poll)

    # ── 生命周期 ──────────────────────────────

    def _on_close(self):
        self.root.withdraw()
        if not hasattr(self, "_tray_icon") or not self._tray_icon:
            self._create_tray()
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
            self._log("应用已最小化到系统托盘")

    def _quit_app(self):
        self._log("正在退出...")
        self.monitor.stop()
        if hasattr(self, "_tray_icon") and self._tray_icon:
            self._tray_icon.stop()
        try:
            self.root.destroy()
        except Exception:
            pass
        # 强制立即终止进程，避免 PyInstaller 隐藏窗口卡 Windows 关机
        os._exit(0)

    def run(self):
        self._log(f"{APP_NAME} 启动")
        self.monitor.start()

        if "--minimized" in sys.argv:
            self.root.withdraw()
        else:
            self.root.deiconify()

        # 初始化系统托盘
        self._create_tray()
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

        self.root.mainloop()
