"""网络状态检测与状态机"""
import time
import threading
import requests

import psutil


class NetworkState:
    UNKNOWN = "unknown"
    CONNECTED = "connected"
    LOGGED_OUT = "logged_out"
    LOGGED_IN_NO_NET = "logged_in_no_net"
    NO_NETWORK = "no_network"
    CHECKING = "checking"


class NetworkMonitor:
    def __init__(self, config, log_func=None):
        self.cfg = config
        self.log = log_func or (lambda msg: None)
        self.state = NetworkState.UNKNOWN
        self.state_changed = None  # callback(state)
        self.fail_count = 0
        self.last_check = 0
        self.last_login = 0
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._high_traffic_count = 0
        self._prev_net_io = None
        self._prev_io_time = 0
        self._wake_event = threading.Event()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._wake_event.set()

    def reset_timer(self):
        """重置检测计时器，下次检测从当前时间重新计时"""
        self._wake_event.set()

    def _loop(self):
        while self._running:
            interval = self.cfg.get("check_interval", 60)
            self._wake_event.clear()

            # 流量检测：如果流量过高，推迟检测
            if self.is_traffic_high():
                self._high_traffic_count += 1
                if self._high_traffic_count <= 3:
                    self.log("网络流量较高，推迟检测 (不影响游戏/下载)")
                    self._wake_event.wait(timeout=10)
                    continue
                else:
                    # 持续高流量，延长间隔
                    interval = max(interval, 300)
                    self.log("持续高流量，延长检测间隔至5分钟")
            else:
                self._high_traffic_count = 0

            self._set_state(NetworkState.CHECKING)
            self._check()
            self.last_check = time.time()

            # 前 4 次失败用 3s 短间隔快速复检，确认后才触发重连
            if 1 <= self.fail_count <= 4:
                self._wake_event.wait(timeout=3)
            else:
                self._wake_event.wait(timeout=interval)

    def is_traffic_high(self):
        threshold = self.cfg.get("traffic_threshold_kbps", 100) * 1024
        try:
            now = time.time()
            counters = psutil.net_io_counters()
            if self._prev_net_io is None:
                self._prev_net_io = counters
                self._prev_io_time = now
                return False

            dt = now - self._prev_io_time
            if dt < 1:
                return False

            bytes_sent = counters.bytes_sent - self._prev_net_io.bytes_sent
            bytes_recv = counters.bytes_recv - self._prev_net_io.bytes_recv
            self._prev_net_io = counters
            self._prev_io_time = now

            rate = (bytes_sent + bytes_recv) / dt
            return rate > threshold
        except Exception:
            return False

    def _check(self):
        test_url = self.cfg.get("test_url", "https://www.baidu.com")
        portal_url = self.cfg.get("portal_url", "http://172.26.3.60")

        # 步骤1: 检测外网
        if self._can_access(test_url, https=True):
            self.fail_count = 0
            self._set_state(NetworkState.CONNECTED)
            return

        self.fail_count += 1
        self.log(f"外网不通 (失败计数: {self.fail_count})")

        # 连续 5 次失败才触发重连（避免偶发网络波动误判）
        if self.fail_count < 5:
            return

        # 步骤2: 检测校园网门户
        if not self._can_access(portal_url, https=False):
            self._set_state(NetworkState.NO_NETWORK)
            self.log("校园网门户不可达，网络完全断开")
            return

        # 步骤3: 判断是否需要注销
        if self._is_redirected_to_portal():
            # HTTP 被重定向到门户 → 未登录
            self._set_state(NetworkState.LOGGED_OUT)
        else:
            self._set_state(NetworkState.LOGGED_IN_NO_NET)

    def _can_access(self, url, https=False):
        try:
            resp = requests.get(url, timeout=5, allow_redirects=True)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def _is_redirected_to_portal(self):
        portal = self.cfg.get("portal_url", "http://172.26.3.60")
        portal_host = portal.split("://")[-1].split("/")[0].split(":")[0]
        try:
            resp = requests.get(
                "http://www.baidu.com",
                timeout=5,
                allow_redirects=False,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location", "")
                if portal_host in location or "172.26" in location:
                    return True
            return False
        except requests.RequestException:
            return False

    def _set_state(self, state):
        with self._lock:
            prev = self.state
            self.state = state
        if state != prev and self.state_changed:
            self.state_changed(state)

    def check_now(self):
        """立即执行一次检测，不触发自动重连回调"""
        saved_cb = self.state_changed
        self.state_changed = None
        self.fail_count = 5  # 跳过失败计数门槛
        try:
            self._check()
        finally:
            self.state_changed = saved_cb
        return self.state

    def mark_login_success(self):
        self.last_login = time.time()
        self.fail_count = 0
        self._set_state(NetworkState.CONNECTED)
