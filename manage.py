"""Explicit opt-in autostart. Never run automatically by the assistant."""
import argparse
from pathlib import Path
import subprocess
import winreg

ROOT = Path(__file__).resolve().parent
KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "JarvisOffline"


def main():
    p = argparse.ArgumentParser(description="Автозапуск Джарвиса для текущего пользователя")
    p.add_argument("action", choices=["status", "enable", "disable"])
    action = p.parse_args().action
    if action == "enable":
        pythonw = ROOT / ".venv/Scripts/pythonw.exe"
        if not pythonw.is_file():
            raise SystemExit("Сначала установите зависимости")
        value = subprocess.list2cmdline([str(pythonw), str(ROOT / "jarvis.py")])
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, value)
        print("Автозапуск включён. Удалять или перемещать папку теперь нельзя.")
    elif action == "disable":
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass
        print("Автозапуск выключен.")
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
                print(winreg.QueryValueEx(key, NAME)[0])
        except FileNotFoundError:
            print("Автозапуск выключен.")


if __name__ == "__main__":
    main()
