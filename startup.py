"""
startup.py — сбор и изменение записей автозагрузки Windows.

Источники: WMI (Win32_StartupCommand), реестр Run (HKCU/HKLM),
папка shell:startup и Планировщик заданий (schtasks).

Ядро очистки кэша и служб НЕ изменяется: этот модуль новый и работает
только с автозагрузкой. Все ошибки доступа гасятся и превращаются в записи
результата, чтобы UI не падал.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import wmi  # type: ignore
except Exception:
    wmi = None  # type: ignore

try:
    import win32api  # type: ignore
except Exception:
    win32api = None  # type: ignore

try:
    import winreg
except Exception:  # pragma: no cover
    winreg = None  # type: ignore

RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
SOURCE_REG_HKCU = "reg_hkcu"
SOURCE_REG_HKLM = "reg_hklm"
SOURCE_FOLDER = "folder"
SOURCE_TASK = "task"

SOURCE_LABELS = {
    SOURCE_REG_HKCU: "Реестр HKCU",
    SOURCE_REG_HKLM: "Реестр HKLM",
    SOURCE_FOLDER: "Папка автозагрузки",
    SOURCE_TASK: "Планировщик",
}


@dataclass
class StartupEntry:
    """Одна запись автозагрузки."""
    name: str
    command: str
    source: str = SOURCE_REG_HKCU          # код источника
    source_label: str = "Реестр HKCU"
    path: str = ""
    arguments: str = ""
    enabled: bool = True
    key_name: str = ""                      # имя значения в Run / имя файла / имя задачи
    root: str = "HKCU"                      # HKCU / HKLM
    view: str = "64-bit"
    broken: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "source": self.source,
            "source_label": self.source_label,
            "path": self.path,
            "arguments": self.arguments,
            "enabled": self.enabled,
            "key_name": self.key_name,
            "root": self.root,
            "view": self.view,
            "broken": self.broken,
            "error": self.error,
        }

    @staticmethod
    def from_dict(data: dict) -> "StartupEntry":
        return StartupEntry(**{k: v for k, v in data.items()
                               if k in StartupEntry.__dataclass_fields__})

    def identity(self) -> tuple:
        return (self.name.lower(), self.source,
                (self.key_name or self.path or self.command).lower())


def _expand(value: str) -> str:
    """Разворачивает %VAR% и переменные вида $env: через win32api при возможности."""
    value = str(value or "").strip()
    if win32api is not None:
        try:
            return os.path.expandvars(str(win32api.ExpandEnvironmentStrings(value)))
        except Exception:
            pass
    return os.path.expandvars(value)


def split_command(command: str) -> tuple[str, str]:
    """Делит строку запуска на путь к exe и аргументы."""
    raw = _expand(command).strip()
    if not raw:
        return "", ""
    if raw.startswith('"'):
        end = raw.find('"', 1)
        if end != -1:
            return raw[1:end], raw[end + 1:].strip()
    # Путь Windows с пробелами: ищем от диска до первого .exe
    match = re.match(
        r"^([A-Za-z]:\\.*?\.(?:exe|dll|bat|cmd|vbs|ps1|lnk))(?:\s|$)",
        raw, re.IGNORECASE,
    )
    if match:
        return match.group(1), raw[match.end():].strip()
    try:
        parts = shlex.split(raw, posix=False)
    except Exception:
        parts = raw.split()
    if not parts:
        return "", ""
    path_part = parts[0].strip('"')
    match = re.search(r"\.exe", path_part, re.IGNORECASE)
    if match and match.end() < len(path_part):
        # путь вида C:\Program.exe Flag -> обрезаем до .exe
        path_part = path_part[:match.end()]
    rest = raw[len(parts[0]):].strip()
    return path_part, rest


def _mark_broken(entry: StartupEntry) -> StartupEntry:
    path = entry.path.strip('"')
    if not path:
        entry.broken = False
        return entry
    if path.lower().endswith((".lnk", ".url")):
        target = _shortcut_target(path)
        entry.broken = not (target and os.path.exists(target))
    elif re.match(r"^[a-zA-Z]:\\", path):
        entry.broken = not os.path.exists(path)
    else:
        # системные команды без абсолютного пути (rundll32, svchost и т.п.)
        entry.broken = not bool(shutil_which(path))
    return entry


def shutil_which(name: str) -> str:
    import shutil
    try:
        return shutil.which(name) or ""
    except Exception:
        return ""


def _shortcut_target(path: str) -> str:
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(path)
        return _expand(shortcut.TargetPath or "")
    except Exception:
        return path


def _from_wmi() -> list[StartupEntry]:
    entries: list[StartupEntry] = []
    if wmi is None:
        return entries
    try:
        conn = wmi.WMI()
        for item in conn.Win32_StartupCommand():
            try:
                name = str(item.Name or item.Caption or "Запись автозагрузки")
                command = str(item.Command or "")
                location = str(item.Location or "").upper()
                if "HKLM" in location:
                    source, root = SOURCE_REG_HKLM, "HKLM"
                elif "HKCU" in location or "USER" in location:
                    source, root = SOURCE_REG_HKCU, "HKCU"
                elif "STARTUP" in location:
                    source, root = SOURCE_FOLDER, ""
                else:
                    source, root = SOURCE_REG_HKCU, "HKCU"
                path, args = split_command(command)
                entry = StartupEntry(
                    name=name, command=command, source=source,
                    source_label=SOURCE_LABELS.get(source, location or "Неизвестно"),
                    path=path, arguments=args, enabled=True,
                    key_name=name, root=root,
                )
                entries.append(_mark_broken(entry))
            except Exception:
                continue
    except Exception:
        pass
    return entries


def _reg_open(root, path: str, flag: int):
    """Открывает ключ через win32api, при отсутствии — через winreg."""
    if win32api is not None:
        try:
            return win32api.RegOpenKeyEx(root, path, 0, flag)
        except Exception:
            pass
    if winreg is not None:
        return winreg.OpenKey(root, path, 0, flag)
    raise OSError("Нет доступа к реестру")


def _reg_enum(key, index: int):
    if win32api is not None:
        try:
            return win32api.RegEnumValue(key, index)
        except Exception:
            pass
    return winreg.EnumValue(key, index)


def _reg_read(root, path: str, name: str) -> str | None:
    try:
        key = _reg_open(root, path, 0x20019)  # KEY_READ
        try:
            if win32api is not None:
                try:
                    return str(win32api.RegQueryValueEx(key, name)[0])
                except Exception:
                    pass
            return str(winreg.QueryValueEx(key, name)[0])
        finally:
            try:
                if win32api is not None:
                    win32api.RegCloseKey(key)
                else:
                    winreg.CloseKey(key)
            except Exception:
                pass
    except Exception:
        return None
    return None


def _reg_delete(root, path: str, name: str, view: int = 0) -> tuple[bool, str]:
    try:
        key = _reg_open(root, path, 0x20006 | view)  # KEY_WRITE + view
        try:
            if win32api is not None:
                try:
                    win32api.RegDeleteValue(key, name)
                    return True, "Значение удалено"
                except Exception:
                    pass
            winreg.DeleteValue(key, name)
            return True, "Значение удалено"
        finally:
            try:
                if win32api is not None:
                    win32api.RegCloseKey(key)
                else:
                    winreg.CloseKey(key)
            except Exception:
                pass
    except Exception as exc:
        return False, str(exc)
    return False, "Неизвестная ошибка реестра"


def _reg_write(root, path: str, name: str, value: str,
               view: int = 0) -> tuple[bool, str]:
    try:
        key = _reg_open(root, path, 0x20006 | view)
        try:
            if win32api is not None:
                try:
                    win32api.RegSetValueEx(key, name, 0, 1, value)  # REG_SZ
                    return True, "Значение восстановлено"
                except Exception:
                    pass
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            return True, "Значение восстановлено"
        finally:
            try:
                if win32api is not None:
                    win32api.RegCloseKey(key)
                else:
                    winreg.CloseKey(key)
            except Exception:
                pass
    except Exception as exc:
        return False, str(exc)
    return False, "Неизвестная ошибка реестра"


def _from_registry() -> list[StartupEntry]:
    entries: list[StartupEntry] = []
    if winreg is None and win32api is None:
        return entries
    roots = []
    if winreg is not None:
        roots = [
            (winreg.HKEY_CURRENT_USER, SOURCE_REG_HKCU, "HKCU", 0),
            (winreg.HKEY_LOCAL_MACHINE, SOURCE_REG_HKLM, "HKLM", 0),
            (winreg.HKEY_LOCAL_MACHINE, SOURCE_REG_HKLM, "HKLM", 0x0200),
        ]
    for root, source, root_name, flag in roots:
        try:
            key = _reg_open(root, RUN_PATH, 0x20019 | flag)
        except Exception:
            continue
        index = 0
        try:
            while True:
                try:
                    name, value, _typ = _reg_enum(key, index)
                except Exception:
                    break
                index += 1
                command = str(value)
                path, args = split_command(command)
                entries.append(_mark_broken(StartupEntry(
                    name=str(name), command=command, source=source,
                    source_label=SOURCE_LABELS[source], path=path, arguments=args,
                    enabled=True, key_name=str(name), root=root_name,
                    view="32-bit" if flag else "64-bit",
                )))
        finally:
            try:
                if win32api is not None:
                    win32api.RegCloseKey(key)
                else:
                    winreg.CloseKey(key)
            except Exception:
                pass
    return entries


def _startup_folders() -> list[Path]:
    folders = []
    for env in ("APPDATA", "ProgramData"):
        base = os.environ.get(env)
        if not base:
            continue
        folders.append(Path(base) / "Microsoft" / "Windows" /
                       "Start Menu" / "Programs" / "Startup")
    return [f for f in folders if f.exists()]


def _from_folder() -> list[StartupEntry]:
    entries: list[StartupEntry] = []
    for folder in _startup_folders():
        try:
            for item in folder.iterdir():
                if item.suffix.lower() not in (".lnk", ".exe", ".bat", ".cmd", ".url"):
                    continue
                enabled = not item.name.lower().endswith(".disabled")
                real_path = item
                if item.name.lower().endswith(".disabled"):
                    real_path = item.with_name(item.name[:-9])
                path = _shortcut_target(str(real_path)) if real_path.suffix.lower() == ".lnk" \
                    else str(real_path)
                entries.append(_mark_broken(StartupEntry(
                    name=real_path.stem, command=str(real_path), source=SOURCE_FOLDER,
                    source_label=SOURCE_LABELS[SOURCE_FOLDER], path=path,
                    arguments="", enabled=enabled, key_name=item.name,
                )))
        except Exception:
            continue
    return entries


def _decode_output(data: bytes | None) -> str:
    """Декодирует вывод консоли Windows (OEM cp866 на русской системе)."""
    if not data:
        return ""
    for encoding in ("utf-8", "cp866", "cp1251"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return data.decode("cp866", errors="replace").strip()


def _run(args: list[str], timeout: int = 15) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return _decode_output(result.stdout) + "\n" + _decode_output(result.stderr)
    except Exception as exc:
        return f"__ERROR__: {exc}"


def _from_tasks(limit: int = 200) -> list[StartupEntry]:
    entries: list[StartupEntry] = []
    output = _run(["schtasks.exe", "/Query", "/FO", "CSV", "/NH"], 40)
    if output.startswith("__ERROR__"):
        return entries
    import csv
    import io
    names: list[str] = []
    try:
        for row in csv.reader(io.StringIO(output)):
            if row and row[0].strip().startswith("\\"):
                task = row[0].strip()
                # пропускаем служебные задачи Microsoft, их слишком много
                if task.lower().startswith("\\microsoft\\"):
                    continue
                names.append(task)
    except Exception:
        return entries

    for task in names[:limit]:
        xml_text = _run(["schtasks.exe", "/Query", "/TN", task, "/XML"], 15)
        if xml_text.startswith("__ERROR__") or "<Task" not in xml_text:
            continue
        try:
            # в выводе может быть BOM/преамбула — ищем корневой тег
            start = xml_text.find("<Task")
            root = ET.fromstring(xml_text[start:])
            ns = {"t": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
            def find(path: str):
                if ns:
                    return root.find(path, ns)
                return root.find(path.replace("t:", ""))
            command_node = find(".//t:Exec/t:Command") if ns else find(".//Exec/Command")
            args_node = find(".//t:Exec/t:Arguments") if ns else find(".//Exec/Arguments")
            enabled_node = find(".//t:Enabled") if ns else find(".//Enabled")
            command = (command_node.text or "").strip() if command_node is not None else ""
            args = (args_node.text or "").strip() if args_node is not None else ""
            enabled = True
            if enabled_node is not None:
                enabled = (enabled_node.text or "true").strip().lower() != "false"
            if not command:
                continue
            path, cmd_args = split_command(command)
            if args:
                cmd_args = (cmd_args + " " + args).strip()
            entries.append(_mark_broken(StartupEntry(
                name=task.strip("\\").split("\\")[-1] or task,
                command=command + ((" " + args) if args else ""),
                source=SOURCE_TASK, source_label=SOURCE_LABELS[SOURCE_TASK],
                path=path, arguments=cmd_args, enabled=enabled,
                key_name=task,
            )))
        except Exception:
            continue
    return entries


def collect_startup_entries() -> list[StartupEntry]:
    """Собирает все записи автозагрузки и убирает дубликаты."""
    entries: list[StartupEntry] = []
    for getter in (_from_wmi, _from_registry, _from_folder, _from_tasks):
        try:
            entries.extend(getter())
        except Exception:
            continue
    unique: dict[tuple, StartupEntry] = {}
    for entry in entries:
        key = entry.identity()
        if key not in unique:
            unique[key] = entry
        elif not unique[key].path and entry.path:
            unique[key] = entry
    return sorted(unique.values(),
                  key=lambda item: (item.source, item.name.lower()))


# ------------------------------------------------------------------ действия
def disable_entry(entry: StartupEntry) -> tuple[bool, str]:
    if entry.source == SOURCE_TASK:
        out = _run(["schtasks.exe", "/Change", "/TN", entry.key_name, "/DISABLE"], 25)
        ok = not out.startswith("__ERROR__") and "ERROR" not in out.upper() \
            and "ОШИБКА" not in out.upper()
        return ok, out.strip()[:300] or "Задача отключена"
    if entry.source in (SOURCE_REG_HKCU, SOURCE_REG_HKLM):
        root = winreg.HKEY_CURRENT_USER if entry.root == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        flag = 0x0200 if entry.view == "32-bit" else 0
        return _reg_delete(root, RUN_PATH, entry.key_name,
                           0x0200 if entry.view == "32-bit" else 0)
    if entry.source == SOURCE_FOLDER:
        target = Path(entry.command.strip('"'))
        disabled = target.with_name(target.name + ".disabled")
        try:
            if target.exists():
                target.rename(disabled)
            return True, "Запись отключена (переименована)"
        except Exception as exc:
            return False, str(exc)
    return False, "Неизвестный источник записи"


def enable_entry(entry: StartupEntry) -> tuple[bool, str]:
    if entry.source == SOURCE_TASK:
        out = _run(["schtasks.exe", "/Change", "/TN", entry.key_name, "/ENABLE"], 25)
        ok = not out.startswith("__ERROR__") and "ERROR" not in out.upper() \
            and "ОШИБКА" not in out.upper()
        return ok, out.strip()[:300] or "Задача включена"
    if entry.source in (SOURCE_REG_HKCU, SOURCE_REG_HKLM):
        root = winreg.HKEY_CURRENT_USER if entry.root == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        flag = 0x0200 if entry.view == "32-bit" else 0
        return _reg_write(root, RUN_PATH, entry.key_name, entry.command,
                          0x0200 if entry.view == "32-bit" else 0)
    if entry.source == SOURCE_FOLDER:
        disabled = Path(entry.command.strip('"'))
        target = disabled.with_name(
            disabled.name[:-9] if disabled.name.lower().endswith(".disabled") else disabled.name
        )
        try:
            if disabled.exists():
                disabled.rename(target)
            return True, "Запись включена"
        except Exception as exc:
            return False, str(exc)
    return False, "Неизвестный источник записи"


def delete_entry(entry: StartupEntry) -> tuple[bool, str]:
    if entry.source == SOURCE_TASK:
        out = _run(["schtasks.exe", "/Delete", "/TN", entry.key_name, "/F"], 25)
        ok = not out.startswith("__ERROR__") and "ERROR" not in out.upper() \
            and "ОШИБКА" not in out.upper()
        return ok, out.strip()[:300] or "Задача удалена"
    if entry.source in (SOURCE_REG_HKCU, SOURCE_REG_HKLM):
        root = winreg.HKEY_CURRENT_USER if entry.root == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        return _reg_delete(root, RUN_PATH, entry.key_name,
                           0x0200 if entry.view == "32-bit" else 0)
    if entry.source == SOURCE_FOLDER:
        try:
            target = Path(entry.command.strip('"'))
            if not target.exists():
                target = target.with_name(target.name + ".disabled")
            if target.exists():
                target.unlink()
            return True, "Ярлык удалён"
        except Exception as exc:
            return False, str(exc)
    return False, "Неизвестный источник записи"


def restore_startup_entries(saved: list[dict]) -> list[tuple[str, bool, str]]:
    """Восстанавливает записи автозагрузки из резервной копии."""
    results: list[tuple[str, bool, str]] = []
    for data in saved:
        try:
            entry = StartupEntry.from_dict(data)
            ok, msg = enable_entry(entry)
            results.append((entry.name, ok, msg))
        except Exception as exc:
            results.append((str(data.get("name", "?")), False, str(exc)))
    return results
