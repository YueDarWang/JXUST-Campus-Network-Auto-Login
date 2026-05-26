"""配置文件管理"""
import os
import json
import base64
import sys


APP_NAME = "校园网自动登录"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), f".{APP_NAME}")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "carrier_id": "3",
    "carrier_suffix": "",
    "check_interval": 60,
    "auto_start": False,
    "portal_url": "http://172.26.3.60",
    "test_url": "https://www.baidu.com",
    "login_api": "",
    "logout_api": "",
    "max_retries": 3,
    "traffic_threshold_kbps": 100,
    "quiet_hours": {
        "enabled": False,
        "start": "23:00",
        "end": "07:00",
    },
}


def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    ensure_config_dir()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = {**DEFAULT_CONFIG, **data}
            return cfg
        except Exception:
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_password(cfg):
    pwd = cfg.get("password", "")
    if not pwd:
        return ""
    try:
        return base64.b64decode(pwd.encode()).decode()
    except Exception:
        return pwd


def set_password(cfg, plain_text):
    cfg["password"] = base64.b64encode(plain_text.encode()).decode()


def get_auto_start():
    """检查是否已设置开机自启"""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ,
        )
        try:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_auto_start(enable):
    """设置或取消开机自启"""
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE | winreg.KEY_READ,
    )
    try:
        if enable:
            exe_path = sys.executable
            if exe_path.endswith("python.exe"):
                script = os.path.abspath(sys.argv[0])
                cmd = f'"{exe_path}" "{script}"'
            else:
                cmd = f'"{exe_path}"'
            cmd += " --minimized"
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)
