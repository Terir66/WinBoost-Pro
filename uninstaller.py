"""
uninstaller.py — список установленных программ и безопасное удаление.

Данные берутся из ветвей реестра Uninstall (HKLM/HKCU, 32/64-битные view).
Поддерживаются:
  * поиск программ в фоновом потоке;
  * вызов стандартного/тихого деинсталлятора;
  * резервная копия и удаление записи реестра, если деинсталлятора нет;
  * сканирование и удаление «хвостов» в AppData / LocalAppData / ProgramData
    и в реестре (только после явного подтверждения списка).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from cache import app_data_dir

try:  # модуль Windows — импорт защищён, чтобы приложение не падало на других ОС
    import winreg
except Exception:  # pragma: no cover
    winreg = None  # type: ignore

UNINSTALL_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
BACKUP_DIR = app_data_dir() / "winboost_reg_backups"

# Слова, которые не помогают идентифицировать программу
GENERIC_WORDS = {
    "microsoft", "windows", "win", "application", "app", "setup", "installer",
    "update", "package", "redistributable", "runtime", "tool", "tools", "soft",
    "software", "inc", "corp", "corporation", "ltd", "llc", "version", "x64",
    "x86", "64bit", "32bit", "ru", "en", "full", "free", "pro", "light",
    "program", "files", "common", "system", "service", "services", "client",
    "desktop", "modul", "module", "component", "components", "update", "kb",
}

# Имена папок, которые никогда не удаляем при очистке хвостов
PROTECTED_DIRS = {
    "microsoft", "windows", "programs", "temp", "cache", "packages", "crashdumps",
    "downloads", "documents", "desktop", "music", "pictures", "videos", "local",
    "roaming", "appdata", "programdata", "common", "system32", "drivers",
    "javascript", "python", "node", "nuget", "fonts", "assembly", "policies",
}


@dataclass
class InstalledApp:
    name: str
    version: str = ""
    publisher: str = ""
    install_location: str = ""
    uninstall_string: str = ""
    quiet_uninstall_string: str = ""
    key_name: str = ""
    root: str = "HKLM"          # HKLM или HKCU
    view: str = "64-bit"        # 64-bit или 32-bit
    estimated_size: int = 0

    @property
    def registry_path(self) -> str:
        return rf"{self.root}\{UNINSTALL_PATH}\{self.key_name}"

    @property
    def has_uninstaller(self) -> bool:
        return bool((self.quiet_uninstall_string or self.uninstall_string).strip())

    def to_row(self) -> list[str]:
        return [
            self.name,
            self.version,
            self.publisher,
            f"{self.estimated_size // (1024 * 1024)} МБ" if self.estimated_size else "—",
        ]

    def tokens(self) -> list[str]:
        """Отличительные слова названия для поиска остатков."""
        words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", self.name.lower())
        return [w for w in words if w not in GENERIC_WORDS][:4]


def _reg_value(key, name: str, default="") -> str:
    try:
        value, _type = winreg.QueryValueEx(key, name)
        return str(value) if value is not None else default
    except Exception:
        return default


def scan_installed_apps() -> list[InstalledApp]:
    """Читает реестр Uninstall. При любой ошибке возвращает то, что удалось прочитать."""
    apps: list[InstalledApp] = []
    if winreg is None:
        return apps

    roots = [
        (winreg.HKEY_LOCAL_MACHINE, "HKLM"),
        (winreg.HKEY_CURRENT_USER, "HKCU"),
    ]
    views = [
        (0, "64-bit"),
        (getattr(winreg, "KEY_WOW64_32KEY", 0x0200), "32-bit"),
    ]

    for root, root_name in roots:
        for flag, view_name in views:
            try:
                with winreg.OpenKey(
                    root, UNINSTALL_PATH, 0,
                    winreg.KEY_READ | flag,
                ) as uninstall_key:
                    index = 0
                    while True:
                        try:
                            key_name = winreg.EnumKey(uninstall_key, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            with winreg.OpenKey(uninstall_key, key_name) as key:
                                # Пропускаем системные компоненты и записи без имени
                                if _reg_value(key, "SystemComponent") == "1":
                                    continue
                                if _reg_value(key, "ParentKeyName").strip():
                                    continue
                                name = _reg_value(key, "DisplayName").strip()
                                if not name:
                                    continue
                                app = InstalledApp(
                                    name=name,
                                    version=_reg_value(key, "DisplayVersion"),
                                    publisher=_reg_value(key, "Publisher"),
                                    install_location=_reg_value(key, "InstallLocation"),
                                    uninstall_string=_reg_value(key, "UninstallString"),
                                    quiet_uninstall_string=_reg_value(key, "QuietUninstallString"),
                                    key_name=key_name,
                                    root=root_name,
                                    view=view_name,
                                )
                                try:
                                    app.estimated_size = (
                                        int(_reg_value(key, "EstimatedSize") or 0) * 1024
                                    )
                                except (TypeError, ValueError):
                                    app.estimated_size = 0
                                apps.append(app)
                        except Exception:
                            # Битая или недоступная запись — просто пропускаем
                            continue
            except Exception:
                continue

    # Убираем дубликаты (одна программа может быть в 32 и 64 view)
    unique: dict[tuple[str, str], InstalledApp] = {}
    for app in apps:
        dedupe_key = (app.name.lower(), (app.uninstall_string or app.key_name).lower())
        if dedupe_key not in unique:
            unique[dedupe_key] = app
    return sorted(unique.values(), key=lambda a: a.name.lower())


class UninstallScanWorker(QThread):
    """Фоновый поиск установленных программ."""
    log = Signal(str)
    progress = Signal(int)
    finished_with_apps = Signal(object)

    def run(self) -> None:
        try:
            apps = scan_installed_apps()
            self.log.emit(f"Найдено программ в реестре: {len(apps)}")
            self.finished_with_apps.emit(apps)
        except Exception as exc:
            self.log.emit(f"Ошибка сканирования реестра: {exc}")
            self.finished_with_apps.emit([])
        self.progress.emit(100)


class Uninstaller:
    """Выполняет удаление программ и очистку остатков."""

    # --- удаление ---
    def uninstall(self, app: InstalledApp) -> tuple[bool, str]:
        """Сначала тихий деинсталлятор, затем обычный."""
        command = (app.quiet_uninstall_string or app.uninstall_string or "").strip()
        if not command:
            return False, "Команда деинсталляции в реестре не найдена"
        try:
            cwd = str(Path(app.install_location).parent) if app.install_location else None
            completed = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=600, check=False, errors="replace",
                cwd=cwd if cwd and Path(cwd).exists() else None,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output = ((completed.stdout or "") + (completed.stderr or "")).strip()
            if completed.returncode == 0:
                return True, "Стандартный деинсталлятор выполнен успешно"
            return False, f"Деинсталлятор вернул код {completed.returncode}. {output[:500]}"
        except subprocess.TimeoutExpired:
            return False, "Деинсталлятор работает слишком долго (timeout 10 мин)"
        except Exception as exc:
            return False, f"Ошибка запуска деинсталлятора: {exc}"

    def backup_registry_key(self, app: InstalledApp) -> tuple[bool, str]:
        """Экспортирует ветку реестра в .reg перед удалением."""
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = re.sub(r"[^\w\-.]", "_", app.key_name)[:60] or "entry"
            out_file = BACKUP_DIR / f"{stamp}_{safe}.reg"
            completed = subprocess.run(
                ["reg.exe", "export", app.registry_path, str(out_file), "/y"],
                capture_output=True, text=True, timeout=30, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode == 0:
                return True, str(out_file)
            return False, (completed.stdout or completed.stderr or "Ошибка reg export").strip()
        except Exception as exc:
            return False, f"Ошибка резервной копии реестра: {exc}"

    def delete_registry_entry(self, app: InstalledApp) -> tuple[bool, str]:
        """Удаляет ветку Uninstall после предварительного экспорта."""
        ok, backup = self.backup_registry_key(app)
        if not ok:
            return False, f"Резервная копия не создана: {backup}. Удаление отменено."
        if winreg is None:
            return False, "winreg недоступен"
        try:
            root = winreg.HKEY_LOCAL_MACHINE if app.root == "HKLM" else winreg.HKEY_CURRENT_USER
            flag = getattr(winreg, "KEY_WOW64_32KEY", 0x0200) if app.view == "32-bit" else 0
            with winreg.OpenKey(root, UNINSTALL_PATH, 0, winreg.KEY_WRITE | flag) as parent:
                self._delete_tree(parent, app.key_name)
            return True, f"Запись реестра удалена. Резервная копия: {backup}"
        except Exception as exc:
            return False, f"Ошибка удаления записи реестра: {exc}. Резервная копия: {backup}"

    def _delete_tree(self, parent_key, sub_key: str) -> None:
        """Рекурсивно удаляет ветку реестра."""
        try:
            with winreg.OpenKey(parent_key, sub_key) as key:
                while True:
                    try:
                        child = winreg.EnumKey(key, 0)
                    except OSError:
                        break
                    self._delete_tree(key, child)
        except Exception:
            pass
        winreg.DeleteKey(parent_key, sub_key)

    # --- поиск остатков ---
    def find_leftovers(self, app: InstalledApp) -> tuple[list[Path], list[str]]:
        """Ищет папки и записи реестра с названием программы."""
        tokens = app.tokens()
        dirs: list[Path] = []
        registry: list[str] = []

        if not tokens:
            return dirs, registry

        roots = [
            Path(os.environ.get("APPDATA", "")),
            Path(os.environ.get("LOCALAPPDATA", "")),
            Path(os.environ.get("ProgramData", r"C:\ProgramData")),
        ]
        for base in roots:
            if not base or not base.exists():
                continue
            try:
                for child in base.iterdir():
                    try:
                        if not child.is_dir() or child.is_symlink():
                            continue
                        if child.name.lower() in PROTECTED_DIRS:
                            continue
                        if any(token in child.name.lower() for token in tokens):
                            dirs.append(child)
                    except Exception:
                        continue
            except Exception:
                continue

        # Поиск по реестру Uninstall
        if winreg is not None:
            for root, root_name in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"),
                                    (winreg.HKEY_CURRENT_USER, "HKCU")):
                for flag in (0, getattr(winreg, "KEY_WOW64_32KEY", 0x0200)):
                    try:
                        with winreg.OpenKey(
                            root, UNINSTALL_PATH, 0, winreg.KEY_READ | flag
                        ) as key:
                            i = 0
                            while True:
                                try:
                                    sub = winreg.EnumKey(key, i)
                                except OSError:
                                    break
                                i += 1
                                try:
                                    with winreg.OpenKey(key, sub) as entry:
                                        value = _reg_value(entry, "DisplayName").lower()
                                    if value and any(t in value for t in tokens):
                                        registry.append(rf"{root_name}\{UNINSTALL_PATH}\{sub}")
                                except Exception:
                                    continue
                    except Exception:
                        continue

        return dirs, registry

    def force_cleanup(self, dirs: list[Path], registry_keys: list[str]) -> list[tuple[str, bool, str]]:
        """Удаляет подтверждённые папки и ветки реестра."""
        results: list[tuple[str, bool, str]] = []

        for directory in dirs:
            try:
                resolved = directory.resolve()
                if not resolved.exists() or directory.is_symlink():
                    results.append((str(directory), False, "Путь не существует или является ссылкой"))
                    continue
                if str(resolved).lower().strip("\\/") in {
                    str(Path(os.environ.get("APPDATA", "")).resolve()).lower().strip("\\/"),
                    str(Path(os.environ.get("LOCALAPPDATA", "")).resolve()).lower().strip("\\/"),
                }:
                    results.append((str(directory), False, "Защищённый корневой путь"))
                    continue
                if directory.is_dir():
                    shutil.rmtree(directory)
                else:
                    directory.unlink()
                results.append((str(directory), True, "Папка удалена"))
            except Exception as exc:
                results.append((str(directory), False, f"Ошибка удаления: {exc}"))

        for key_path in registry_keys:
            ok, msg = self._delete_registry_path(key_path)
            results.append((key_path, ok, msg))
        return results

    def _delete_registry_path(self, full_path: str) -> tuple[bool, str]:
        """Удаляет ветку реестра по полному пути вида HKLM\\Software\\..."""
        if winreg is None:
            return False, "winreg недоступен"
        try:
            parts = full_path.split("\\")
            root_name = parts[0]
            sub_path = "\\".join(parts[1:])
            root = winreg.HKEY_LOCAL_MACHINE if root_name == "HKLM" else winreg.HKEY_CURRENT_USER
            # Резервная копия перед удалением
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["reg.exe", "export", full_path,
                 str(BACKUP_DIR / f"leftover_{datetime.now():%Y%m%d_%H%M%S_%f}.reg"), "/y"],
                capture_output=True, timeout=20, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            parent_path, leaf = sub_path.rsplit("\\", 1)
            with winreg.OpenKey(root, parent_path, 0, winreg.KEY_WRITE) as parent:
                self._delete_tree(parent, leaf)
            return True, "Ветка реестра удалена"
        except Exception as exc:
            return False, f"Ошибка удаления ветки: {exc}"


class UninstallWorker(QThread):
    """Фоновый вызов деинсталлятора или удаление записи реестра."""
    log = Signal(str)
    finished_with_result = Signal(bool, str)

    def __init__(self, uninstaller: Uninstaller, app: InstalledApp,
                 remove_registry: bool = False, parent=None):
        super().__init__(parent)
        self.uninstaller = uninstaller
        self.app = app
        self.remove_registry = remove_registry

    def run(self) -> None:
        try:
            if self.app.has_uninstaller:
                self.log.emit(f"Запуск деинсталлятора: {self.app.name}")
                ok, msg = self.uninstaller.uninstall(self.app)
            elif self.remove_registry:
                self.log.emit(f"Деинсталлятора нет, удаляем запись реестра: {self.app.name}")
                ok, msg = self.uninstaller.delete_registry_entry(self.app)
            else:
                ok, msg = False, "Деинсталлятор отсутствует (требуется подтверждение удаления записи)"
            self.finished_with_result.emit(ok, msg)
        except Exception as exc:
            self.finished_with_result.emit(False, f"Исключение при удалении: {exc}")


class LeftoverScanWorker(QThread):
    """Фоновый поиск остатков программы."""
    log = Signal(str)
    finished_with_leftovers = Signal(object, object)

    def __init__(self, uninstaller: Uninstaller, app: InstalledApp, parent=None):
        super().__init__(parent)
        self.uninstaller = uninstaller
        self.app = app

    def run(self) -> None:
        try:
            dirs, registry = self.uninstaller.find_leftovers(self.app)
            self.log.emit(f"Найдено остатков: папок {len(dirs)}, записей реестра {len(registry)}")
            self.finished_with_leftovers.emit(dirs, registry)
        except Exception as exc:
            self.log.emit(f"Ошибка поиска остатков: {exc}")
            self.finished_with_leftovers.emit([], [])


class CleanupWorker(QThread):
    """Фоновая очистка подтверждённых остатков."""
    log = Signal(str)
    progress = Signal(int)
    finished_with_results = Signal(object)

    def __init__(self, uninstaller: Uninstaller, dirs: list[Path],
                 registry: list[str], parent=None):
        super().__init__(parent)
        self.uninstaller = uninstaller
        self.dirs = dirs
        self.registry = registry

    def run(self) -> None:
        total = max(1, len(self.dirs) + len(self.registry))
        done = 0
        results = []
        for path in self.dirs:
            self.log.emit(f"Удаление папки: {path}")
            done += 1
            self.progress.emit(int(done / total * 100))
            try:
                results.append(self.uninstaller.force_cleanup([path], []))
            except Exception as exc:
                results.append([(str(path), False, str(exc))])
        for key in self.registry:
            self.log.emit(f"Удаление ветки реестра: {key}")
            done += 1
            self.progress.emit(int(done / total * 100))
            try:
                results.append(self.uninstaller.force_cleanup([], [key]))
            except Exception as exc:
                results.append([(key, False, str(exc))])
        flat = [item for group in results for item in group]
        self.progress.emit(100)
        self.finished_with_results.emit(flat)
