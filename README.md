# 校园网自动登录

江西理工大学校园网自动登录工具，支持 Dr.COM 哆点 / 锐捷 ePortal 认证系统。断线自动重连，后台静默运行。

## 功能

- **自动登录** — 连接校园网后自动完成认证
- **断线重连** — 检测到离线自动重新登录，支持失败退避
- **系统托盘** — 最小化到托盘，后台静默运行，绿色图标即表示在线
- **开机自启** — 可设置开机自动启动
- **多运营商** — 支持校园网、移动、联通、电信
- **流量感知** — 检测到高流量（下载/游戏）时推迟重连，避免中断
- **一键打包** — `build.bat` 打包为单个 exe，无 Python 环境也能运行

## 截图

运行后会在系统托盘显示图标：
- 绿色：已连接
- 黄色：检测中
- 红色：离线

右键托盘图标可显示窗口、手动重连、切换开机自启。

## 使用方式

### 方式一：直接运行 exe（推荐）

从 [Releases](../../releases) 下载 `校园网自动登录.exe`，双击运行。

### 方式二：源码运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python src/main.py

# 3. 最小化到托盘启动（配合开机自启）
python src/main.py --minimized
```

### 方式三：自行打包

```bash
build.bat
```

打包产物在 `dist/campus-net.exe`。

## 设置说明

| 设置项 | 说明 |
|--------|------|
| 账号 / 密码 | 校园网账号密码（学号） |
| 运营商 | 校园网 / 移动 / 联通 / 电信 |
| 检测间隔 | 联网状态检测频率（默认 60 秒） |
| 开机自启 | 勾选后开机自动启动 |
| 流量阈值 | 网络流量超过此值时推迟重连，避免影响当前活动 |

> 门户 URL、测试 URL、登录/注销 API 默认自动检测，一般无需修改。

## 调试

如果自动检测登录接口失败，可以用 `debug_portal.py` 手动调试：

```bash
python debug_portal.py              # 分析门户页面，生成 portal_page.html
python debug_portal.py --check      # 检查当前网络连通状态
python debug_portal.py --login      # 测试登录（需先在脚本内填账号密码）
python debug_portal.py --try-all    # 逐一测试所有运营商
python debug_portal.py --logout     # 测试注销
```

## 技术栈

- Python 3.x
- tkinter — GUI 界面
- pystray + Pillow — 系统托盘
- requests + BeautifulSoup — 网络请求与页面解析
- psutil — 流量监控
- PyInstaller — 打包为 exe

## License

MIT
