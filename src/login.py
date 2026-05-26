"""校园网登录/注销引擎 - 支持 Dr.COM 哆点 / 锐捷 ePortal"""
import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode


class LoginEngine:
    def __init__(self, config, log_func=None):
        self.cfg = config
        self.log = log_func or (lambda msg: None)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        self._login_url = None
        self._logout_url = None
        self._form_fields = None
        self._drcom_config = None
        self._carrier_options = []

    # ── 页面获取 ──────────────────────────────────

    def _fetch_page(self, url, timeout=8):
        try:
            resp = self.session.get(url, timeout=timeout, allow_redirects=True)
            resp.encoding = resp.apparent_encoding or resp.headers.get(
                "content-type", "").split("charset=")[-1] or "utf-8"
            return resp
        except requests.RequestException as e:
            self.log(f"请求 {url} 失败: {e}")
            return None

    # ── Dr.COM 哆点配置解析 ─────────────────────

    def _parse_drcom_config(self, html):
        """解析 Dr.COM 哆点系统的 JS 配置变量"""
        patterns = {
            "login_ip": r"authloginIP\s*=\s*'([^']*)'",
            "login_port": r"authloginport\s*=\s*(\d+)",
            "login_path": r"authloginpath\s*=\s*'([^']*)'",
            "login_param": r"authloginparam\s*=\s*'([^']*)'",
            "user_field": r"authuserfield\s*=\s*'([^']*)'",
            "pass_field": r"authpassfield\s*=\s*'([^']*)'",
            "logout_ip": r"authlogoutIP\s*=\s*'([^']*)'",
            "logout_port": r"authlogoutport\s*=\s*(\d+)",
            "logout_path": r"authlogoutpath\s*=\s*'([^']*)'",
            "logout_param": r"authlogoutparam\s*=\s*'([^']*)'",
            "success_page": r"authsuccess\s*=\s*'([^']*)'",
            "fail_page": r"authfail\s*=\s*'([^']*)'",
            "charset": r"charset\s*=\s*'([^']*)'",
            "uid": r"uid\s*=\s*'([^']*)'",
            "v4ip": r"v4ip\s*=\s*'([^']*)'",
        }

        config = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, html)
            if match:
                config[key] = match.group(1)

        # 解析运营商选项
        carrier_match = re.search(r"carrier\s*=\s*'(.*?{.*?})'", html)
        if carrier_match:
            try:
                carrier_data = json.loads(carrier_match.group(1))
                for group in carrier_data.values():
                    if "data" in group:
                        self._carrier_options = group["data"]
                        config["carrier_default"] = group.get("defaultID", "")
                        self.log(f"解析到 {len(self._carrier_options)} 个运营商选项")
            except (json.JSONDecodeError, KeyError):
                pass

        if "login_path" in config:
            self.log("检测到 Dr.COM 哆点系统")
            self._drcom_config = config
            return True
        return False

    def get_carrier_options(self):
        """返回运营商选项列表 [{id, name, suffix}]（浏览器抓包确认）"""
        return [
            {"id": "3", "name": "校园网", "suffix": ""},
            {"id": "1", "name": "移动", "suffix": "@cmccyt"},
            {"id": "2", "name": "联通", "suffix": "@unicomyt"},
            {"id": "0", "name": "电信", "suffix": "@telecomyt"},
        ]

    def _build_drcom_url(self, base_host, ip, port, path, param):
        """构建 Dr.COM 完整 URL"""
        host = ip or base_host
        port_str = f":{port}" if port else ""
        full_path = path
        if param:
            full_path += ("&" if "?" in path else "?") + param
        return f"http://{host}{port_str}{full_path}"

    # ── 表单解析 ─────────────────────────────────

    def _find_login_form(self, html, base_url):
        """从 HTML 中提取登录表单信息"""
        soup = BeautifulSoup(html, "lxml")
        forms = soup.find_all("form")
        for form in forms:
            action = form.get("action", "")
            action = urljoin(base_url, action) if action else base_url
            method = (form.get("method", "post")).upper()

            inputs = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                if name:
                    inputs[name] = inp.get("value", "")

            name_fields = ["username", "userId", "userid", "account", "user",
                           "name", "uname", "phone", "DDDDD"]
            pwd_fields = ["password", "passwd", "pwd", "pass", "userPwd",
                          "upass", "upwd", "v6"]

            has_user = any(f in {k.lower() for k in inputs} for f in name_fields)
            has_pwd = any(f in {k.lower() for k in inputs} for f in pwd_fields)

            if has_user and has_pwd:
                self.log(f"找到登录表单: action={action}, method={method}")
                return {"action": action, "method": method, "fields": inputs}

        return None

    # ── API 检测入口 ────────────────────────────

    def _detect_portal_api(self):
        """自动检测门户登录/注销 API"""
        portal = self.cfg.get("portal_url", "http://172.26.3.60")
        resp = self._fetch_page(portal)
        if not resp:
            return False

        html = resp.text
        final_url = resp.url
        portal_host = urlparse(portal).hostname

        # 尝试 Dr.COM 哆点解析
        if self._parse_drcom_config(html):
            cfg = self._drcom_config
            port = cfg.get("login_port", "801")

            # Dr.COM 4.x portal API 路径 (JSONP 端点)
            self._login_url = f"http://{portal_host}:{port}/eportal/portal/login"
            self._logout_url = f"http://{portal_host}:{port}/eportal/portal/logout"

            # Dr.COM portal API 使用 user_account / user_password
            self._form_fields = {
                "user_account": "",
                "user_password": "",
            }
            self.log(f"登录 URL: {self._login_url}")
            self.log(f"注销 URL: {self._logout_url}")
            return True

        # 尝试传统表单解析
        form_info = self._find_login_form(html, final_url)
        if form_info:
            self._login_url = form_info["action"]
            self._form_fields = form_info["fields"]
            self._find_logout_url(html, final_url)
            return True

        # 尝试常见锐捷 ePortal 路径
        return self._try_common_paths(portal)

    def _try_common_paths(self, portal):
        portal_host = urlparse(portal).hostname
        common = [
            f"http://{portal_host}:801/eportal/portal/login",
            f"http://{portal_host}/eportal/portal/login",
            f"http://{portal_host}:801/eportal/?c=ACSetting&a=Login",
        ]
        for url in common:
            try:
                r = self.session.get(url, timeout=5)
                if r.status_code != 404:
                    self._login_url = url
                    self._logout_url = f"http://{portal_host}:801/eportal/portal/logout"
                    self.log(f"使用候选 URL: {url}")
                    return True
            except Exception:
                continue

        self.log("未能自动检测到登录 API，请在设置中手动配置")
        return False

    def _find_logout_url(self, html, base_url):
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True).lower()
            if any(kw in href.lower() + text
                   for kw in ["logout", "offline", "注销", "下线", "exit"]):
                self._logout_url = urljoin(base_url, href)
                self.log(f"找到注销 URL: {self._logout_url}")
                return

    # ── 登录 ────────────────────────────────────

    def login(self):
        username = self.cfg.get("username", "")
        from .config import get_password
        password = get_password(self.cfg)

        if not username or not password:
            self.log("账号或密码未配置")
            return False

        manual_login = self.cfg.get("login_api", "")
        if manual_login:
            return self._do_login(manual_login, username, password)

        if not self._login_url:
            if not self._detect_portal_api():
                return False

        if not self._login_url:
            self.log("未找到登录接口")
            return False

        return self._do_login(self._login_url, username, password)

    def _do_login(self, url, username, password):
        self.log(f"正在登录: {url}")
        data = self._build_login_data(username, password)

        try:
            # Dr.COM 4.x: JSONP-style GET with all params as query string
            if "c=ACSetting" in url or "eportal" in url.lower():
                resp = self.session.get(url, params=data, timeout=10)
            elif "method=login" in url or "InterFace" in url:
                # 锐捷 ePortal: GET with query params
                resp = self.session.get(url, params=data, timeout=10)
            else:
                resp = self.session.get(url, params=data, timeout=10)

            resp.encoding = resp.apparent_encoding or "utf-8"
        except requests.RequestException as e:
            self.log(f"登录请求失败: {e}")
            return False

        self.log(f"登录响应 [{resp.status_code}]: {resp.text[:300]}")
        return self._check_login_success(resp)

    def _build_login_data(self, username, password):
        carrier_id = self.cfg.get("carrier_id", "0")
        carrier_suffix = self.cfg.get("carrier_suffix", "")

        # Dr.COM 实际格式: ,<carrier_id>,<username>@<suffix>
        full_username = f",{carrier_id},{username}{carrier_suffix}"

        data = {
            "callback": f"dr{__import__('random').randint(1000, 9999)}",
            "login_method": "1",
            "user_account": full_username,
            "user_password": password,
            "wlan_user_ip": self._drcom_config.get("v4ip", "") if self._drcom_config else "",
            "wlan_user_ipv6": "",
            "wlan_user_mac": "000000000000",
            "wlan_ac_ip": "",
            "wlan_ac_name": "",
            "jsVersion": "4.2.1",
            "terminal_type": "1",
            "lang": "zh-cn",
            "v": str(__import__('random').randint(1000, 9999)),
        }

        # 设备 IP 优先从 portal 解析
        if not data["wlan_user_ip"] and self._drcom_config:
            data["wlan_user_ip"] = self._drcom_config.get("v4ip", "")

        return data

    def _check_login_success(self, resp):
        text = resp.text

        # 解析 JSONP 响应: dr1234({"result":0,...})
        jsonp_match = re.search(r'(?:dr\d+)?\s*\(?\s*(\{.*?\})\s*\)?\s*;?\s*$', text, re.DOTALL)
        if jsonp_match:
            try:
                data = json.loads(jsonp_match.group(1))
                result = data.get("result", "")
                msg = data.get("msg", "")
                self.log(f"JSONP 响应: result={result}, msg={msg}")

                # result=1 或 "ok" 表示成功 (Dr.COM portal API)
                if result == 1 or str(result).lower() == "ok":
                    self.log("登录成功")
                    return True

                # result=0 或 "fail"/"error" 表示失败
                if result == 0 or str(result).lower() in ("fail", "error"):
                    self.log(f"登录失败: {msg}")
                    return False
            except (json.JSONDecodeError, KeyError):
                pass

        text_lower = text.lower()

        fail_kw = ["dr.comwebLoginid_2.htm", "失败", "密码错误",
                   "账号不存在", "账号已", "欠费", "禁用",
                   "error", "fail", "认证失败", "登录失败"]

        for kw in fail_kw:
            if kw.lower() in text_lower:
                self.log(f"登录失败 ({kw})")
                return False

        success_kw = ["dr.comwebLoginid_3.htm", "success", "成功",
                      "登录成功", "认证成功", "已连接", "在线", "注销页"]

        for kw in success_kw:
            if kw.lower() in text_lower:
                self.log("登录成功")
                return True

        if resp.status_code == 200:
            self.log("登录可能成功 (HTTP 200)")
            return True

        return False

    # ── 注销 ────────────────────────────────────

    def logout(self):
        manual_logout = self.cfg.get("logout_api", "")
        if manual_logout:
            return self._do_logout(manual_logout)

        if not self._logout_url:
            self._detect_portal_api()

        if not self._logout_url:
            portal = self.cfg.get("portal_url", "http://172.26.3.60")
            portal_host = urlparse(portal).hostname
            self._logout_url = f"http://{portal_host}:801/eportal/portal/logout"

        return self._do_logout(self._logout_url)

    def _do_logout(self, url):
        self.log(f"正在注销: {url}")
        try:
            resp = self.session.get(
                url,
                params={"callback": f"dr{__import__('random').randint(1000, 9999)}"},
                timeout=10,
            )
            resp.encoding = resp.apparent_encoding or "utf-8"
            self.log(f"注销响应 [{resp.status_code}]: {resp.text[:200]}")

            # 检查注销结果
            jsonp_match = re.search(r'\{.*?\}', resp.text)
            if jsonp_match:
                data = json.loads(jsonp_match.group())
                if data.get("result") == 1:
                    self.log("注销成功")
            return True
        except requests.RequestException as e:
            self.log(f"注销请求失败: {e}")
            return False
