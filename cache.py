"""
cache.py — модуль очистки кэша и временных файлов.

Отвечает за:
  * поиск целей очистки (Chrome, Яндекс, Temp, эскизы);
  * проверку запущенных процессов браузеров;
  * подсчёт размера и безопасное удаление с проверкой результата.

Все тяжёлые операции выполняются в QThread, GUI получает только сигналы.
"""
from __future__ import annotations

import glob
import math
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Signal

# --- константы ---
APP_NAME = "WinBoost"
APP_VERSION = "1.0"


def human_size(num: float) -> str:
    """Человекочитаемый размер: B / KB / MB / GB.

    Устойчив к inf/nan и переполнению: вместо падения возвращает 'н/д',
    чтобы сбой одного числа не ломал весь лог очистки/сканирования.
    """
    try:
        value = float(num)
    except (TypeError, ValueError, OverflowError):
        return "н/д"
    if not math.isfinite(value):
        return "н/д"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(value) < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} GB"


def localappdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


def appdata() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))


def windows_temp() -> Path:
    return Path(os.environ.get("TEMP", localappdata() / "Temp"))


def app_data_dir() -> Path:
    """Постоянная папка данных приложения (не временная папка PyInstaller)."""
    path = localappdata() / APP_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path.home()
    return path


def dir_size(path: Path) -> int:
    """Рекурсивный подсчёт размера. Ошибки доступа безопасно игнорируются."""
    total = 0
    try:
        if path.is_file():
            return path.stat().st_size
        if not path.is_dir():
            return 0
        for root, _dirs, files in os.walk(path, onerror=lambda e: None):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except (OSError, ValueError):
                    continue
    except (OSError, ValueError):
        return total
    return total


@dataclass
class CleanTarget:
    """Одна цель очистки."""
    key: str
    label: str
    paths: list[Path] = field(default_factory=list)
    processes: tuple[str, ...] = ()  # процессы, которые нужно закрыть перед очисткой

    def existing_paths(self) -> list[Path]:
        return [p for p in self.paths if p.exists()]


def build_targets() -> dict[str, CleanTarget]:
    """Формирует список известных целей с учётом переменных окружения."""
    la = localappdata()
    return {
        "chrome": CleanTarget(
            "chrome", "Кэш Chrome",
            [
                la / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
                la / "Google" / "Chrome" / "User Data" / "Default" / "GPUCache",
            ],
            ("chrome.exe",),
        ),
        "yandex": CleanTarget(
            "yandex", "Кэш Яндекс Браузера",
            [
                la / "Yandex" / "YandexBrowser" / "User Data" / "Default" / "Cache",
                la / "Yandex" / "YandexBrowser" / "User Data" / "Default" / "GPUCache",
            ],
            ("yandex.exe",),
        ),
        "temp": CleanTarget("temp", "Системный Temp", [windows_temp()]),
        "thumbnails": CleanTarget("thumbnails", "Эскизы (Thumbnails)", []),
    }


def thumbnail_files() -> list[Path]:
    """Файлы кэша эскизов оболочки Windows."""
    pattern = str(localappdata() / "Microsoft" / "Windows" / "Explorer" / "thumbcache_*.db")
    try:
        return [Path(p) for p in glob.glob(pattern)]
    except (OSError, ValueError):
        return []


def target_size(key: str) -> int:
    """Размер конкретной цели."""
    targets = build_targets()
    target = targets.get(key)
    if not target:
        return 0
    if key == "thumbnails":
        return sum(dir_size(p) for p in thumbnail_files())
    return sum(dir_size(p) for p in target.existing_paths())


def is_process_running(process_name: str) -> bool:
    """
    Проверяет, запущен ли процесс. Сначала через psutil, при отсутствии —
    через стандартную утилиту tasklist. Любая ошибка = процесс не найден.
    """
    name = process_name.lower()
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            try:
                if (proc.info.get("name") or "").lower() == name:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return False
    except Exception:
        pass

    # Резервный путь без psutil
    import subprocess
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return name in (out.stdout or "").lower()
    except Exception:
        return False


@dataclass
class ScanResult:
    """Результат сканирования: размеры и заблокированные цели."""
    sizes: dict[str, int] = field(default_factory=dict)
    blocked: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.sizes.values())


class CacheScanWorker(QThread):
    """Фоновое сканирование кэша (размеры + проверка процессов)."""

    progress = Signal(int)
    finished_with_result = Signal(object)
    error = Signal(str)

    def __init__(self, keys: list[str], parent=None):
        super().__init__(parent)
        self.keys = keys

    def run(self) -> None:
        result = ScanResult()
        targets = build_targets()
        try:
            total_steps = max(1, len(self.keys))
            for i, key in enumerate(self.keys, start=1):
                target = targets.get(key)
                if not target:
                    continue
                result.sizes[key] = target_size(key)
                for proc in target.processes:
                    try:
                        if is_process_running(proc):
                            result.blocked.setdefault(key, []).append(proc)
                    except Exception as exc:  # недостаточно прав и т.п.
                        result.blocked.setdefault(key, []).append(f"{proc} (проверка: {exc})")
                self.progress.emit(int(i / total_steps * 100))
        except Exception as exc:
            self.error.emit(f"Ошибка сканирования кэша: {exc}")
        self.progress.emit(100)
        self.finished_with_result.emit(result)


class CacheCleanWorker(QThread):
    """Фоновая очистка: размер до → удаление → проверка, что размер стал 0."""

    log = Signal(str)
    progress = Signal(int)
    file_removed = Signal(str, int)
    finished_with_stats = Signal(int, int, int)  # папки, файлы, байты

    def __init__(self, keys: list[str], parent=None):
        super().__init__(parent)
        self.keys = keys
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        removed_dirs = removed_files = freed_total = 0
        targets = build_targets()
        steps = max(1, len(self.keys) * 2)
        step = 0

        try:
            self.log.emit("=== Начало очистки ===")
            for key in self.keys:
                if self._cancelled:
                    self.log.emit("Очистка отменена.")
                    break
                target = targets.get(key)
                if not target:
                    continue

                name = target.label
                before = target_size(key)
                step += 1
                self.progress.emit(int(step / steps * 100))
                self.log.emit(f"[{name}] размер до очистки: {human_size(before)}")

                paths = thumbnail_files() if key == "thumbnails" else target.existing_paths()
                freed_before = freed_total

                for path in paths:
                    if self._cancelled:
                        break
                    size = dir_size(path)
                    try:
                        if path.is_dir() and not path.is_symlink():
                            shutil.rmtree(path)
                            removed_dirs += 1
                        elif path.exists() or path.is_symlink():
                            path.unlink()
                            removed_files += 1
                        freed_total += size
                        self.file_removed.emit(str(path), size)
                        self.log.emit(f"  Удалено: {path} ({human_size(size)})")
                    except PermissionError:
                        self.log.emit(f"  Пропущено (файл занят или нет прав): {path}")
                    except (OSError, shutil.Error) as exc:
                        self.log.emit(f"  Ошибка удаления {path}: {exc}")

                after = target_size(key)
                step += 1
                self.progress.emit(int(step / steps * 100))
                if after == 0:
                    self.log.emit(
                        f"[{name}] ✓ Проверка пройдена: размер 0 "
                        f"(освобождено {human_size(freed_total - freed_before)})"
                    )
                else:
                    self.log.emit(
                        f"[{name}] ⚠ Осталось {human_size(after)} "
                        "— возможно, файлы заняты другими процессами"
                    )

            self.progress.emit(100)
            self.log.emit(f"=== Готово. Освобождено: {human_size(freed_total)} ===")
        except Exception as exc:
            self.log.emit(f"Критическая ошибка очистки: {exc}")
        self.finished_with_stats.emit(removed_dirs, removed_files, freed_total)
