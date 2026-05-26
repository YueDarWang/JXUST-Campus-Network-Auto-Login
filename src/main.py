"""校园网自动登录 - 入口"""
import sys
import os

# PyInstaller 打包后 _MEIPASS 是解压目录；源码运行时用脚本所在目录
if getattr(sys, "frozen", False):
    root = sys._MEIPASS
else:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, root)

from src.gui import CampusNetApp


def main():
    app = CampusNetApp()
    app.run()


if __name__ == "__main__":
    main()
