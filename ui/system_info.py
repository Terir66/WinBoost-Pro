"""
ui/system_info.py — чтение системных метрик для «визуала».

Это НЕ ядро: здесь только безопасные чтения, все ошибки гасятся.
Логика очистки/служб/удаления программ в этих функциях не используется.
"""
from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import time

from PySide6.QtCore import QThread, Signal

try:
    import winreg
except Exception:  # pragma: no cover
    winreg = None  # type: ignore


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate() -> bool:
    """Перезапускает приложение с запросом UAC через ShellExecuteW('runas')."""
    try:
        import sys
        import subprocess
        executable = getattr(sys, "executable", sys.argv[0])
        params = " ".join(
            subprocess.list2cmdline(arg) for arg in sys.argv[1:]
        ) if len(sys.argv) > 1 else ""
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, None, 1
        )
        return int(result) > 32
    except Exception:
        return False


def windows_version() -> str:
    try:
        if winreg is not None:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            ) as key:
                build = ""
                display = ""
                try:
                    build = str(winreg.QueryValueEx(key, "CurrentBuild")[0])
                except Exception:
                    pass
                try:
                    display = str(winreg.QueryValueEx(key, "DisplayVersion")[0])
                except Exception:
                    pass
                name = "Windows 11" if build and int(build.split(".")[0]) >= 22000 \
                    else "Windows 10"
                extra = f" {display}" if display else ""
                return f"{name}{extra} (build {build})" if build else f"{name}{extra}"
    except Exception:
        pass
    return f"Windows {platform.win32_ver()[0] or '?'}"


def cpu_name() -> str:
    try:
        if winreg is not None:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except Exception:
        pass
    return os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or "Неизвестно")


def _memory_status() -> tuple[float, float]:
    """Возвращает (всего ГБ, свободно ГБ)."""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return (stat.ullTotalPhys / (1024 ** 3), stat.ullAvailPhys / (1024 ** 3))
    except Exception:
        return (0.0, 0.0)


def free_ram_gb() -> float:
    return _memory_status()[1]


def ram_percent() -> float:
    try:
        total, free = _memory_status()
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, (1.0 - free / total) * 100.0))
    except Exception:
        return 0.0


def cpu_percent() -> float:
    """Единичный замер CPU без запуска фонового потока psutil."""
    try:
        import psutil
        return max(0.0, min(100.0, float(psutil.cpu_percent(interval=None))))
    except Exception:
        pass
    return 0.0


_GPU_NAME_CACHE: str | None = None
_GPU_PERCENT_CACHE: tuple[float, float] = (0.0, 0.0)


def gpu_name() -> str:
    """Имя видеокарты через WMI (AMD/Intel/NVIDIA). Результат кэшируется."""
    global _GPU_NAME_CACHE
    if _GPU_NAME_CACHE is not None:
        return _GPU_NAME_CACHE

    result = "неизвестно"
    try:
        import wmi
        names = [str(item.Name).strip() for item in
                 wmi.WMI().Win32_VideoController() if getattr(item, "Name", None)]
        if names:
            # предпочитаем дискретную карту, если она есть
            for name in names:
                lowered = name.lower()
                if any(word in lowered for word in ("nvidia", "geforce", "rtx",
                                                    "gtx", "radeon rx", "arc")):
                    result = name
                    break
            else:
                result = names[0]
    except Exception:
        pass

    if result == "неизвестно":
        try:
            out = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-CimInstance Win32_VideoController).Name -join ', '"],
                capture_output=True, timeout=8, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            raw = out.stdout or b""
            for encoding in ("utf-8", "cp866", "cp1251"):
                try:
                    result = raw.decode(encoding).strip() or "неизвестно"
                    break
                except UnicodeDecodeError:
                    continue
        except Exception:
            pass

    _GPU_NAME_CACHE = result
    return result


def gpu_percent() -> float:
    """
    Загрузка GPU: сначала nvidia-smi, затем счётчики WMI GPUEngine.
    Значение кэшируется на 10 секунд — опрос сотен WMI-инстансов
    слишком тяжёлый, чтобы делать его часто. Вызывается из фонового потока.
    """
    global _GPU_PERCENT_CACHE
    now = time.monotonic()
    cached_value, cached_at = _GPU_PERCENT_CACHE
    if cached_at and now - cached_at < 10.0:
        return cached_value

    result = 0.0
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        value = (out.stdout or "").strip().splitlines()
        if value:
            result = max(0.0, min(100.0, float(value[0].strip())))
    except Exception:
        pass

    if result == 0.0:
        try:
            import wmi
            rows = wmi.WMI().Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine()
            total = 0.0
            found = False
            for row in rows:
                try:
                    name = str(getattr(row, "Name", "") or "")
                    if "engtype_3D" not in name:
                        continue
                    total += float(getattr(row, "UtilizationPercentage", 0) or 0)
                    found = True
                except Exception:
                    continue
            if found:
                result = max(0.0, min(100.0, total))
        except Exception:
            pass

    _GPU_PERCENT_CACHE = (result, now)
    return result


class SystemMonitorWorker(QThread):
    """
    Фоновый опрос метрик. Тяжёлый запрос GPU (WMI/nvidia-smi) выполняется
    здесь, поэтому GUI не замирает.

    Сигнал: cpu%, ram%, gpu%, free_ram_gb.
    """
    metrics = Signal(float, float, float, float)

    def __init__(self, interval_ms: int = 2500, parent=None):
        super().__init__(parent)
        self.interval_ms = interval_ms
        self._running = True

    def stop(self) -> None:
        self._running = False
        self.requestInterruption()

    def run(self) -> None:
        while self._running and not self.isInterruptionRequested():
            try:
                cpu = cpu_percent()
                ram = ram_percent()
                free = free_ram_gb()
                gpu = gpu_percent()
                self.metrics.emit(cpu, ram, gpu, free)
            except Exception:
                pass
            # прерываемый сон вместо time.sleep
            for _ in range(max(1, self.interval_ms // 100)):
                if not self._running or self.isInterruptionRequested():
                    return
                self.msleep(100)
