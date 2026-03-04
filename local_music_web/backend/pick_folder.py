# 调用系统级“选择文件夹”对话框，返回选中路径（后端运行在本机时有效）
import os
import platform
import subprocess
import sys
from typing import Optional


def pick_folder(prompt: str = "选择音乐文件夹") -> Optional[str]:
    """
    弹出系统原生选择文件夹对话框，返回选中路径；用户取消则返回 None。
    仅在本地运行后端时有效（会阻塞请求直到用户操作完成）。
    """
    sys_name = platform.system()
    try:
        if sys_name == "Darwin":
            # macOS: AppleScript
            out = subprocess.run(
                ["osascript", "-e", f'return POSIX path of (choose folder with prompt "{prompt}")'],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if out.returncode != 0:
                return None
            path = (out.stdout or "").strip()
            return path if path and os.path.isdir(path) else None

        if sys_name == "Windows":
            # Windows: PowerShell 调用 Shell.Application.BrowseForFolder
            ps = f'''
$shell = New-Object -ComObject Shell.Application
$folder = $shell.BrowseForFolder(0, "{prompt}", 0, 0)
if ($folder) {{ $folder.Self.Path }}
'''
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if out.returncode != 0 or not (out.stdout or "").strip():
                return None
            path = (out.stdout or "").strip()
            return path if path and os.path.isdir(path) else None

        # Linux: zenity 或 kdialog
        for cmd in [
            ["zenity", "--file-selection", "--directory", "--title", prompt],
            ["kdialog", "--getexistingdirectory", os.path.expanduser("~"), "--title", prompt],
        ]:
            try:
                out = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if out.returncode == 0 and (out.stdout or "").strip():
                    path = (out.stdout or "").strip()
                    if os.path.isdir(path):
                        return path
            except FileNotFoundError:
                continue
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None
