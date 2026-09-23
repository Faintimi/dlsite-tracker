"""PyInstaller 打包入口：产物的行为等价于 ``python -m dlsite_tracker``。

桌面端「内嵌管道」用它构建单文件可执行程序（Tauri sidecar）；构建方式见
``scripts/build-sidecar.sh`` 与 CI 的 desktop-release 工作流：

    pyinstaller --onefile --name radar-pipeline --paths . packaging/pipeline_entry.py
"""

from dlsite_tracker.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
