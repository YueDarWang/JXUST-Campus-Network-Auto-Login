"""
校园网门户调试脚本
用法:
  python debug_portal.py              # 分析门户页面
  python debug_portal.py --login      # 测试登录 (用 CARRIER 变量指定)
  python debug_portal.py --try-all    # 逐个测试 4 个运营商 找出正确的
  python debug_portal.py --logout     # 测试注销
  python debug_portal.py --check      # 检查连接状态
"""

import os
import sys
import time
import json
import requests
import random
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

PORTAL_URL = "http://172.26.3.60"
LOG_FILE = "debug_log.txt"
RESULT_FILE = "debug_result.json"

USERNAME = ""
PASSWORD = ""
CARRIER = "3"  # 0=电信, 1=移动, 2=联通, 3=校园网（用 --try-all 可逐个测试）


def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{t}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def clear_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")


def save_result(data):
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_page(url, session=None, timeout=8):
    s = session or requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    })
    try:
        resp = s.get(url, timeout=timeout, allow_redirects=True)
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp
    except requests.RequestException as e:
        log(f"请求 {url} 失败: {e}")
        return None


def parse_drcom_config(html):
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
    }
    config = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, html)
        if match:
            config[key] = match.group(1)
    return config if "login_path" in config else None


def analyze_portal():
    log("=" * 60)
    log("开始分析门户页面")
    log(f"门户 URL: {PORTAL_URL}")
    session = requests.Session()
    resp = fetch_page(PORTAL_URL, session)
    if not resp:
        log("无法访问门户页面")
        return None

    final_url = resp.url
    log(f"最终 URL: {final_url}")
    log(f"响应状态: {resp.status_code}")
    html_file = "portal_page.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(resp.text)
    log(f"页面 HTML 已保存到: {html_file}")

    soup = BeautifulSoup(resp.text, "lxml")
    result = {"portal_url": PORTAL_URL, "final_url": final_url}

    drcom = parse_drcom_config(resp.text)
    if drcom:
        log("==> 检测到 Dr.COM 哆点系统 <==")
        result["drcom"] = drcom
        portal_host = PORTAL_URL.split("://")[-1].split("/")[0].split(":")[0]
        port = drcom.get("login_port", "801")
        log(f"  Portal API 登录 URL: http://{portal_host}:{port}/eportal/portal/login")
        log(f"  Portal API 注销 URL: http://{portal_host}:{port}/eportal/portal/logout")
        log(f"  当前 UID: {drcom.get('uid', 'N/A')}")

        # 解析运营商
        carrier_match = re.search(r"carrier\s*=\s*'(.*?\{.*?\})'", resp.text)
        if carrier_match:
            try:
                carrier_data = json.loads(carrier_match.group(1))
                for group in carrier_data.values():
                    if "data" in group:
                        log(f"  HTML 运营商配置 ({len(group['data'])} 个):")
                        for opt in group["data"]:
                            log(f"    [{opt['id']}] {opt['name']} (suffix={opt.get('suffix', '无')})")
                        log("  注意: 页面实际显示的运营商可能与此不同!")
            except json.JSONDecodeError:
                pass

    forms = soup.find_all("form")
    log(f"找到 {len(forms)} 个表单")
    for i, form in enumerate(forms):
        action = form.get("action", "")
        action = urljoin(final_url, action) if action else final_url
        method = (form.get("method", "post")).upper()
        log(f"  表单#{i + 1}: action={action}, method={method}")

    save_result(result)
    return result


CARRIERS = {
    "1": {"name": "移动", "suffix": "@cmccyt"},
    "2": {"name": "联通", "suffix": "@unicomyt"},
    "3": {"name": "校园网", "suffix": ""},
    "0": {"name": "电信", "suffix": "@telecomyt"},
}


def try_login(carrier_id):
    """尝试用指定运营商登录，返回 (result_dict, session)"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
        "Referer": "http://172.26.3.60/",
    })

    # 先访问门户获取设备 IP
    v4ip = ""
    try:
        r = session.get("http://172.26.3.60/", timeout=10)
        m = re.search(r"v4ip\s*=\s*'([^']*)'", r.text)
        if m:
            v4ip = m.group(1)
    except Exception:
        pass

    carrier = CARRIERS.get(str(carrier_id), {"suffix": ""})
    # 实际 user_account 格式: ,<运营商ID>,<用户名>@<后缀>
    account = f",{carrier_id},{USERNAME}{carrier['suffix']}"

    data = {
        "callback": f"dr{random.randint(1000, 9999)}",
        "login_method": "1",
        "user_account": account,
        "user_password": PASSWORD,
        "wlan_user_ip": v4ip,
        "wlan_user_ipv6": "",
        "wlan_user_mac": "000000000000",
        "wlan_ac_ip": "",
        "wlan_ac_name": "",
        "jsVersion": "4.2.1",
        "terminal_type": "1",
        "lang": "zh-cn",
        "v": str(random.randint(1000, 9999)),
    }

    try:
        resp = session.get(
            "http://172.26.3.60:801/eportal/portal/login",
            params=data, timeout=10,
        )
        resp.encoding = resp.apparent_encoding or "utf-8"
        m = re.search(r'\{.*?\}', resp.text)
        if m:
            return json.loads(m.group()), session
        return {"error": "parse failed", "raw": resp.text[:200]}, session
    except requests.RequestException as e:
        return {"error": str(e)}, session


def check_internet(session):
    """检查是否能访问外网"""
    try:
        r = session.get("https://www.baidu.com", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def test_login():
    """测试登录"""
    log("=" * 60)
    log("开始登录测试")

    if not USERNAME or not PASSWORD:
        log("请在脚本顶部填入 USERNAME 和 PASSWORD!")
        return

    if CARRIER == "0":
        log("逐一测试所有运营商...")
        log("(认证成功 ≠ 能上网，关键看最后的外网验证)")
        log("")
        # 按已知顺序测试
        for cid in ["0", "1", "2", "3"]:
            cname = CARRIERS.get(cid, {}).get("name", "?")
            log(f"--- 尝试运营商 [{cid}] {cname} ---")
            result, session = try_login(cid)
            ret = result.get("result", "")
            msg = result.get("msg", "")

            if "在线" in msg:
                log(f"yys={cid}: 已在线（之前测试成功了），停止测试")
                break

            log(f"yys={cid}: result={ret}, msg={msg}")

            if ret == 1:
                time.sleep(2)
                if check_internet(session):
                    log(f">>> yys={cid} 认证成功 + 外网可达! 这就是正确的运营商! <<<")
                    return
                else:
                    log(f">>> yys={cid} 认证成功但外网不可达（运营商不对）<<<")
                    # 注销后再试下一个
                    session.get(
                        "http://172.26.3.60:801/eportal/portal/logout",
                        params={"callback": f"dr{random.randint(1000, 9999)}"},
                        timeout=10,
                    )
                    time.sleep(2)
            time.sleep(1)
        log("所有运营商测试完毕")
        return

    # 单个运营商
    result, session = try_login(CARRIER)
    cname = CARRIERS.get(str(CARRIER), {}).get("name", "?")
    log(f"运营商 [{CARRIER}] {cname}")
    log(f"响应: {json.dumps(result, ensure_ascii=False)}")

    ret = result.get("result", "")
    msg = result.get("msg", "")
    if ret == 1:
        time.sleep(2)
        if check_internet(session):
            log("*** 登录成功，外网可达！***")
        else:
            log("*** 认证成功但外网不可达 — 运营商可能选错了 ***")
            log("试试 CARRIER='0' 逐个测试所有运营商")
    else:
        log(f"登录失败: {msg}")


def test_logout():
    log("=" * 60)
    log("开始注销测试")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    })
    cb = f"dr{random.randint(1000, 9999)}"
    try:
        resp = session.get(
            "http://172.26.3.60:801/eportal/portal/logout",
            params={"callback": cb}, timeout=10,
        )
        log(f"注销响应: {resp.text[:200]}")
        m = re.search(r'\{.*?\}', resp.text)
        if m:
            data = json.loads(m.group())
            if data.get("result") == 1:
                log("注销成功!")
            else:
                log(f"注销可能失败: {data.get('msg')}")
    except requests.RequestException as e:
        log(f"请求失败: {e}")


def check_connectivity():
    log("=" * 60)
    log("检查网络连通性")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    try:
        r = session.get("https://www.baidu.com", timeout=5)
        log(f"百度 HTTPS: HTTP {r.status_code} (外网正常)")
    except requests.RequestException as e:
        log(f"百度 HTTPS: 不可达 ({e})")

    try:
        r = session.get(PORTAL_URL, timeout=5)
        log(f"门户: HTTP {r.status_code}")
    except requests.RequestException as e:
        log(f"门户: 不可达 ({e})")

    try:
        r = session.get("http://www.baidu.com", timeout=5, allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            log(f"HTTP百度: {r.status_code} -> {loc} (被重定向，说明已下线)")
        else:
            log(f"HTTP百度: {r.status_code} (无重定向)")
    except requests.RequestException as e:
        log(f"HTTP百度: 不可达 ({e})")


if __name__ == "__main__":
    clear_log()
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "--login":
        test_login()
    elif mode == "--try-all":
        CARRIER = "0"
        test_login()
    elif mode == "--logout":
        test_logout()
    elif mode == "--check":
        check_connectivity()
    else:
        check_connectivity()
        analyze_portal()
        log("")
        log("用法:")
        log("  python debug_portal.py --login     测试登录")
        log("  python debug_portal.py --try-all   逐个测试所有运营商")
        log("  python debug_portal.py --logout    测试注销")
        log("  python debug_portal.py --check     检查连接状态")
