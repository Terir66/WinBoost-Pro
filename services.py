"""
services.py — управление службами Windows.

Возможности:
  * перечисление служб (через win32service, PowerShell или `sc`);
  * чтение/изменение типа запуска и состояния;
  * проверка зависимостей перед отключением;
  * профили оптимизации с предварительным просмотром и подтверждением;
  * резервная копия исходных настроек и восстановление.

Все изменения только после явного подтверждения пользователя.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from cache import app_data_dir

BACKUP_FILE = app_data_dir() / "winboost_services_backup.json"

# Критические службы, которые запрещено останавливать/отключать ни при каких профилях.
CRITICAL_SERVICES = {
    "rpcss", "dcomlaunch", "winmgmt", "eventlog", "plugplay", "power",
    "profsvc", "samss", "lsass", "services", "smstsmgr", "trustedinstaller",
    "wininit", "csrss", "smss", "fontdrvhost", "sihost", "winlogon",
    "netlogon", "dhcp", "dnscache", "tcpip", "afd", "nsi", "iphlpsvc",
    "lanmanworkstation", "lmhosts", "gpsvc", "cryptsvc", "appinfo",
    "bam", "userdatamgr", "statecpsvc", "appreadiness", "textinputmanagement",
}
CRITICAL_SERVICES = {name.strip().lower() for name in CRITICAL_SERVICES}

# Профили оптимизации. Значение — желаемый тип запуска: Disabled / Manual / Auto.
# restore=True означает, что службу нужно ещё и остановить.
PROFILES: dict[str, dict[str, dict]] = {
    "Безопасный": {
        "DiagTrack": {"start": "Disabled", "stop": True,
                      "comment": "Телеметрия и диагностика"},
        "dmwappushservice": {"start": "Disabled", "stop": True,
                             "comment": "WAP Push — канал телеметрии"},
        "RetailDemo": {"start": "Disabled", "stop": True,
                       "comment": "Демонстрационный режим магазина"},
        "WdiSystemHost": {"start": "Disabled", "stop": True,
                          "comment": "Диагностика драйверов"},
        "WdiServiceHost": {"start": "Disabled", "stop": True,
                           "comment": "Диагностика драйверов"},
        "MapsBroker": {"start": "Disabled", "stop": True,
                       "comment": "Фоновая загрузка карт"},
        "Fax": {"start": "Disabled", "stop": True,
                "comment": "Факс (обычно не используется)"},
    },
    "Баланс": {
        "DiagTrack": {"start": "Disabled", "stop": True, "comment": "Телеметрия"},
        "dmwappushservice": {"start": "Disabled", "stop": True, "comment": "Телеметрия"},
        "RetailDemo": {"start": "Disabled", "stop": True, "comment": "Демо-режим"},
        "WdiSystemHost": {"start": "Disabled", "stop": True, "comment": "Диагностика"},
        "WdiServiceHost": {"start": "Disabled", "stop": True, "comment": "Диагностика"},
        "MapsBroker": {"start": "Disabled", "stop": True, "comment": "Карты"},
        "SysMain": {"start": "Disabled", "stop": True,
                    "comment": "Superfetch — часто мешает на SSD"},
        "WSearch": {"start": "Manual", "stop": True,
                    "comment": "Индексация поиска (снижает нагрузку)"},
        "Fax": {"start": "Disabled", "stop": True, "comment": "Факс"},
    },
    "Максимальная производительность": {
        "DiagTrack": {"start": "Disabled", "stop": True, "comment": "Телеметрия"},
        "dmwappushservice": {"start": "Disabled", "stop": True, "comment": "Телеметрия"},
        "RetailDemo": {"start": "Disabled", "stop": True, "comment": "Демо-режим"},
        "WdiSystemHost": {"start": "Disabled", "stop": True, "comment": "Диагностика"},
        "WdiServiceHost": {"start": "Disabled", "stop": True, "comment": "Диагностика"},
        "MapsBroker": {"start": "Disabled", "stop": True, "comment": "Карты"},
        "SysMain": {"start": "Disabled", "stop": True, "comment": "Superfetch"},
        "WSearch": {"start": "Disabled", "stop": True, "comment": "Индексация поиска"},
        "wuauserv": {"start": "Disabled", "stop": True,
                     "comment": "Центр обновления Windows ⚠ обновления не придут"},
        "BITS": {"start": "Disabled", "stop": True,
                 "comment": "Фоновая передача ⚠ влияет на обновления"},
        "Spooler": {"start": "Disabled", "stop": True,
                    "comment": "Служба печати ⚠ печать перестанет работать"},
        " Fax": {"start": "Disabled", "stop": True, "comment": "Факс"},
        "wbengine": {"start": "Manual", "stop": True,
                     "comment": "Резервное копирование (по требованию)"},
    },
}

# Приводим ключи к «чистому» виду (защита от опечаток с пробелами)
for _profile in PROFILES.values():
    for _key in list(_profile):
        _clean = _key.strip()
        if _clean != _key:
            _profile[_clean] = _profile.pop(_key)


@dataclass
class ServiceInfo:
    name: str
    display_name: str
    status: str = "Остановлена"
    start_type: str = "Unknown"

    def to_row(self) -> list[str]:
        return [self.display_name, self.name, self.status, self.start_type]


@dataclass
class ChangeItem:
    """Одна строка плана изменений."""
    name: str
    display_name: str
    current_status: str
    current_start_type: str
    target_start_type: str
    stop: bool
    comment: str = ""
    dependents: list[str] = field(default_factory=list)
    blocked: bool = False
    reason: str = ""


@dataclass
class ChangeResult:
    name: str
    ok: bool
    message: str


def _run(args: list[str], timeout: int = 30, encoding: str | None = None) -> str:
    """Безопасный запуск системной команды. Ошибки не пробрасываются наружу."""
    try:
        kwargs = {
            "capture_output": True, "text": True, "timeout": timeout,
            "check": False, "errors": "replace",
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        }
        if encoding:
            kwargs["encoding"] = encoding
        completed = subprocess.run(args, **kwargs)
        return (completed.stdout or "") + (completed.stderr or "")
    except Exception as exc:
        return f"__ERROR__: {exc}"


def _win32_available() -> bool:
    try:
        import win32service  # noqa: F401
        return True
    except Exception:
        return False


def _open_scm():
    try:
        import win32service
        return win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
    except Exception:
        return None


def _close_handle(handle) -> None:
    try:
        import win32service
        if handle is not None:
            win32service.CloseServiceHandle(handle)
    except Exception:
        pass


def normalize_start_type(value) -> str:
    """Приводит разные представления типа запуска к Auto/Manual/Disabled."""
    if isinstance(value, int):
        return {0: "Boot", 1: "System", 2: "Auto", 3: "Manual", 4: "Disabled"}.get(
            value, "Unknown"
        )
    text = str(value or "").lower().replace("_", " ")
    if "disabled" in text or text == "4":
        return "Disabled"
    if "manual" in text or "demand" in text or "trigger" in text or text == "3":
        return "Manual"
    if "auto" in text or text == "2":
        return "Auto"
    if "boot" in text or text == "0":
        return "Boot"
    if "system" in text or text == "1":
        return "System"
    return "Unknown"


class ServiceManager:
    """Инкапсулирует все операции со службами."""

    def list_services(self) -> list[ServiceInfo]:
        services = self._list_via_powershell()
        if not services:
            services = self._list_via_win32()
        if not services:
            services = self._list_via_sc()
        return sorted(services, key=lambda s: s.name.lower())

    # --- чтение ---
    def _list_via_powershell(self) -> list[ServiceInfo]:
        ps = (
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            "Get-Service | Select-Object Name,DisplayName,Status,StartType "
            "| ConvertTo-Json -Compress"
        )
        out = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                   40, encoding="utf-8")
        if out.startswith("__ERROR__") or not out.strip():
            return []
        try:
            import json
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            result = []
            for item in data:
                try:
                    result.append(ServiceInfo(
                        name=str(item.get("Name", "")),
                        display_name=str(item.get("DisplayName", "")),
                        status="Запущена" if str(item.get("Status", "")).lower() == "running"
                               else "Остановлена",
                        start_type=normalize_start_type(item.get("StartType")),
                    ))
                except Exception:
                    continue
            return result
        except Exception:
            return []

    def _list_via_win32(self) -> list[ServiceInfo]:
        if not _win32_available():
            return []
        try:
            import win32service
            scm = _open_scm()
            if scm is None:
                return []
            raw = win32service.EnumServicesStatus(
                scm, win32service.SERVICE_WIN32, win32service.SERVICE_STATE_ALL
            )
            result = []
            for name, display, status in raw:
                try:
                    svc = win32service.OpenService(scm, name, win32service.SERVICE_QUERY_CONFIG)
                    cfg = win32service.QueryServiceConfig(svc)
                    _close_handle(svc)
                    state = status.get("CurrentState", 1) if isinstance(status, dict) else 1
                    result.append(ServiceInfo(
                        name=name, display_name=display,
                        status="Запущена" if state == win32service.SERVICE_RUNNING
                               else "Остановлена",
                        start_type=normalize_start_type(cfg[1]),
                    ))
                except Exception:
                    result.append(ServiceInfo(name=name, display_name=display))
            _close_handle(scm)
            return result
        except Exception:
            return []

    def _list_via_sc(self) -> list[ServiceInfo]:
        out = _run(["sc.exe", "query", "state=", "all"], 60)
        result: list[ServiceInfo] = []
        if out.startswith("__ERROR__"):
            return result
        blocks = re.split(r"\n(?=SERVICE_NAME:)", out)
        for block in blocks:
            m_name = re.search(r"SERVICE_NAME:\s*(\S+)", block)
            if not m_name:
                continue
            m_display = re.search(r"DISPLAY_NAME:\s*(.+)", block)
            m_state = re.search(
                r"\b(RUNNING|STOPPED|PAUSED|START_PENDING|STOP_PENDING)\b", block,
                re.IGNORECASE,
            )
            state_word = m_state.group(1).upper() if m_state else ""
            name = m_name.group(1)
            result.append(ServiceInfo(
                name=name,
                display_name=(m_display.group(1).strip() if m_display else name),
                status="Запущена" if state_word == "RUNNING" else "Остановлена",
                start_type=self.get_start_type(name),
            ))
        return result

    def _ps_service_info(self, name: str) -> dict | None:
        """Данные одной службы через PowerShell (не зависят от локали системы)."""
        safe = name.replace("'", "''")
        ps = (
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            f"Get-Service -Name '{safe}' -ErrorAction SilentlyContinue "
            "| Select-Object Name,DisplayName,Status,StartType | ConvertTo-Json -Compress"
        )
        out = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                   20, encoding="utf-8")
        if out.startswith("__ERROR__") or not out.strip():
            return None
        try:
            import json
            data = json.loads(out)
            if isinstance(data, list):
                data = data[0] if data else None
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def get_start_type(self, name: str) -> str:
        """Тип запуска конкретной службы."""
        if _win32_available():
            try:
                import win32service
                scm = _open_scm()
                if scm:
                    svc = win32service.OpenService(scm, name, win32service.SERVICE_QUERY_CONFIG)
                    cfg = win32service.QueryServiceConfig(svc)
                    _close_handle(svc)
                    _close_handle(scm)
                    return normalize_start_type(cfg[1])
            except Exception:
                pass
        info = self._ps_service_info(name)
        if info:
            return normalize_start_type(info.get("StartType"))
        # sc.exe на русской системе печатает локализованные заголовки,
        # поэтому ищем англоязычный токен: DISABLED / AUTO_START / DEMAND_START.
        out = _run(["sc.exe", "qc", name], 15)
        match = re.search(
            r"\b(?:AUTO_START|DEMAND_START|DISABLED|BOOT_START|SYSTEM_START)\b", out,
            re.IGNORECASE,
        )
        return normalize_start_type(match.group(0) if match else "Unknown")

    def get_status(self, name: str) -> str:
        if _win32_available():
            try:
                import win32service
                scm = _open_scm()
                if scm:
                    svc = win32service.OpenService(scm, name, win32service.SERVICE_QUERY_STATUS)
                    st = win32service.QueryServiceStatusEx(svc)
                    _close_handle(svc)
                    _close_handle(scm)
                    return "Запущена" if st.get("CurrentState") == win32service.SERVICE_RUNNING \
                        else "Остановлена"
            except Exception:
                pass
        info = self._ps_service_info(name)
        if info:
            return "Запущена" if str(info.get("Status", "")).lower() == "running" \
                else "Остановлена"
        out = _run(["sc.exe", "query", name], 15)
        match = re.search(r"\b(RUNNING|STOPPED|PAUSED|START_PENDING|STOP_PENDING)\b", out,
                          re.IGNORECASE)
        return "Запущена" if (match and match.group(1).upper() == "RUNNING") \
            else "Остановлена"

    def get_dependents(self, name: str) -> list[str]:
        """Список реально зависимых служб. Пустой список = можно отключать."""
        dependents: set[str] = set()
        if _win32_available():
            try:
                import win32service
                scm = _open_scm()
                if scm:
                    svc = win32service.OpenService(scm, name, win32service.SERVICE_QUERY_STATUS)
                    items = win32service.EnumDependentServices(
                        svc, win32service.SERVICE_ACTIVE
                    )
                    for item in items:
                        try:
                            dependents.add(str(item[0]))
                        except Exception:
                            continue
                    _close_handle(svc)
                    _close_handle(scm)
                    return sorted(dependents)
            except Exception:
                pass
        out = _run(["sc.exe", "enumdepend", name], 15)
        for match in re.finditer(r"SERVICE_NAME:\s*(\S+)", out):
            dependents.add(match.group(1))
        return sorted(dependents)

    def service_exists(self, name: str) -> bool:
        if _win32_available():
            try:
                import win32service
                scm = _open_scm()
                if scm:
                    svc = win32service.OpenService(scm, name, win32service.SERVICE_QUERY_CONFIG)
                    _close_handle(svc)
                    _close_handle(scm)
                    return True
            except Exception:
                pass
        out = _run(["sc.exe", "qc", name], 15)
        lowered = out.lower()
        if out.startswith("__ERROR__") or "failed" in lowered or "1060" in lowered:
            return False
        return bool(out.strip())

    def display_name(self, name: str) -> str:
        info = self._ps_service_info(name)
        if info and info.get("DisplayName"):
            return str(info["DisplayName"])
        return name

    # --- изменение ---
    def set_start_type(self, name: str, start_type: str) -> tuple[bool, str]:
        mapping = {"Auto": 2, "Manual": 3, "Disabled": 4}
        target = mapping.get(start_type)
        if target is None:
            return False, f"Неизвестный тип запуска: {start_type}"
        if _win32_available():
            try:
                import win32service
                scm = _open_scm()
                if scm:
                    svc = win32service.OpenService(scm, name, win32service.SERVICE_CHANGE_CONFIG)
                    win32service.ChangeServiceConfig(
                        svc,
                        win32service.SERVICE_NO_CHANGE,
                        target,
                        win32service.SERVICE_NO_CHANGE,
                        None, None, 0, None, None, None, None,
                    )
                    _close_handle(svc)
                    _close_handle(scm)
                    return True, f"Тип запуска изменён на {start_type}"
            except Exception as exc:
                return False, f"win32service: {exc}. Требуются права администратора."
        out = _run(["sc.exe", "config", name, "start=", start_type.lower()], 20)
        lowered = out.lower()
        if out.startswith("__ERROR__") or "failed" in lowered or "error:" in lowered \
                or "ошибка" in lowered:
            return False, out.strip() or "Ошибка sc config (нужны права администратора)"
        return True, f"Тип запуска изменён на {start_type}"

    def stop(self, name: str) -> tuple[bool, str]:
        if _win32_available():
            try:
                import win32service
                scm = _open_scm()
                if scm:
                    svc = win32service.OpenService(scm, name, win32service.SERVICE_STOP)
                    win32service.ControlService(svc, win32service.SERVICE_CONTROL_STOP)
                    _close_handle(svc)
                    _close_handle(scm)
                    return True, "Служба остановлена"
            except Exception as exc:
                return False, f"win32service: {exc}"
        out = _run(["net", "stop", name, "/y"], 30)
        if "FAILED" in out.upper() or "не найден" in out.lower().replace("not found", ""):
            return False, out.strip() or "Ошибка net stop"
        return True, "Служба остановлена"

    def start(self, name: str) -> tuple[bool, str]:
        if _win32_available():
            try:
                import win32service
                scm = _open_scm()
                if scm:
                    svc = win32service.OpenService(scm, name, win32service.SERVICE_START)
                    win32service.StartService(svc)
                    _close_handle(svc)
                    _close_handle(scm)
                    return True, "Служба запущена"
            except Exception as exc:
                return False, f"win32service: {exc}"
        out = _run(["net", "start", name], 30)
        if "FAILED" in out.upper():
            return False, out.strip() or "Ошибка net start"
        return True, "Служба запущена"

    # --- профили ---
    def build_plan(self, profile_name: str) -> list[ChangeItem]:
        """Формирует план без внесения изменений."""
        profile = PROFILES.get(profile_name, {})
        plan: list[ChangeItem] = []
        # Один вызов PowerShell вместо десятков — быстрее и надёжнее
        known = {svc.name.lower(): svc for svc in self.list_services()}
        for name, cfg in profile.items():
            try:
                found = known.get(name.lower())
                item = ChangeItem(
                    name=name,
                    display_name=found.display_name if found else self.display_name(name),
                    current_status=found.status if found else self.get_status(name),
                    current_start_type=found.start_type if found else self.get_start_type(name),
                    target_start_type=cfg["start"],
                    stop=bool(cfg.get("stop")),
                    comment=cfg.get("comment", ""),
                )
                # Проверяем, не входит ли служба в список критических
                if name.strip().lower() in CRITICAL_SERVICES:
                    item.blocked = True
                    item.reason = "Критически важная служба — изменение запрещено"
                if not self.service_exists(name):
                    item.blocked = True
                    item.reason = "Служба не найдена на этом ПК"
                if not item.blocked:
                    deps = self.get_dependents(name)
                    item.dependents = deps
                    if deps:
                        item.blocked = True
                        item.reason = f"Есть зависимые службы: {', '.join(deps)}"
                plan.append(item)
            except Exception as exc:
                plan.append(ChangeItem(
                    name=name, display_name=name, current_status="?",
                    current_start_type="?", target_start_type=cfg["start"],
                    stop=cfg.get("stop", False), blocked=True,
                    reason=f"Ошибка проверки: {exc}",
                ))
        return plan

    def apply_plan(self, plan: list[ChangeItem]) -> list[ChangeResult]:
        """Применяет подтверждённый план. Пропускает заблокированные строки."""
        results: list[ChangeResult] = []
        backup: dict[str, dict] = {}
        try:
            if BACKUP_FILE.exists():
                backup = json.loads(BACKUP_FILE.read_text(encoding="utf-8"))
        except Exception:
            backup = {}

        for item in plan:
            if item.blocked:
                results.append(ChangeResult(item.name, False, f"Пропущено: {item.reason}"))
                continue
            try:
                backup[item.name] = {
                    "display_name": item.display_name,
                    "status": item.current_status,
                    "start_type": item.current_start_type,
                }
                if item.stop and item.current_status == "Запущена":
                    ok, msg = self.stop(item.name)
                    if not ok:
                        results.append(ChangeResult(item.name, False, f"Остановка: {msg}"))
                        continue
                ok, msg = self.set_start_type(item.name, item.target_start_type)
                results.append(ChangeResult(item.name, ok, msg))
            except Exception as exc:
                results.append(ChangeResult(item.name, False, f"Исключение: {exc}"))

        try:
            BACKUP_FILE.write_text(json.dumps(backup, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except Exception:
            pass
        return results

    def restore_backup(self) -> list[ChangeResult]:
        """Восстанавливает исходные типы запуска из резервной копии."""
        results: list[ChangeResult] = []
        try:
            if not BACKUP_FILE.exists():
                return [ChangeResult("", False, "Резервная копия не найдена")]
            data = json.loads(BACKUP_FILE.read_text(encoding="utf-8"))
            for name, info in data.items():
                try:
                    ok, msg = self.set_start_type(name, info.get("start_type", "Manual"))
                    results.append(ChangeResult(name, ok, msg))
                except Exception as exc:
                    results.append(ChangeResult(name, False, str(exc)))
        except Exception as exc:
            results.append(ChangeResult("", False, f"Ошибка чтения backup: {exc}"))
        return results


# --- потоки ---
class ServiceScanWorker(QThread):
    log = Signal(str)
    progress = Signal(int)
    finished_with_result = Signal(object)

    def __init__(self, manager: ServiceManager, parent=None):
        super().__init__(parent)
        self.manager = manager

    def run(self) -> None:
        try:
            self.log.emit("Сканирование служб Windows…")
            services = self.manager.list_services()
            self.log.emit(f"Найдено служб: {len(services)}")
            self.finished_with_result.emit(services)
        except Exception as exc:
            self.log.emit(f"Ошибка сканирования служб: {exc}")
            self.finished_with_result.emit([])
        self.progress.emit(100)


class ServicePlanWorker(QThread):
    log = Signal(str)
    finished_with_plan = Signal(object)

    def __init__(self, manager: ServiceManager, profile: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.profile = profile

    def run(self) -> None:
        try:
            plan = self.manager.build_plan(self.profile)
            self.finished_with_plan.emit(plan)
        except Exception as exc:
            self.log.emit(f"Ошибка построения плана: {exc}")
            self.finished_with_plan.emit([])


class ServiceApplyWorker(QThread):
    log = Signal(str)
    progress = Signal(int)
    finished_with_results = Signal(object)

    def __init__(self, manager: ServiceManager, plan: list[ChangeItem], parent=None):
        super().__init__(parent)
        self.manager = manager
        self.plan = plan

    def run(self) -> None:
        total = max(1, len(self.plan))
        for i, item in enumerate(self.plan, start=1):
            self.log.emit(f"[{item.name}] {item.target_start_type} …")
            self.progress.emit(int(i / total * 100))
        try:
            results = self.manager.apply_plan(self.plan)
            for r in results:
                self.log.emit(f"  {r.name}: {'OK' if r.ok else 'ОШИБКА'} — {r.message}")
            self.finished_with_results.emit(results)
        except Exception as exc:
            self.log.emit(f"Критическая ошибка применения: {exc}")
            self.finished_with_results.emit([])
        self.progress.emit(100)


class ServiceRestoreWorker(QThread):
    """Восстановление исходных типов запуска из резервной копии."""
    log = Signal(str)
    finished_with_results = Signal(object)

    def __init__(self, manager: ServiceManager, parent=None):
        super().__init__(parent)
        self.manager = manager

    def run(self) -> None:
        try:
            results = self.manager.restore_backup()
            for r in results:
                self.log.emit(f"  {r.name}: {'OK' if r.ok else 'ОШИБКА'} — {r.message}")
            self.finished_with_results.emit(results)
        except Exception as exc:
            self.log.emit(f"Ошибка восстановления: {exc}")
            self.finished_with_results.emit([])


class ServiceControlWorker(QThread):
    log = Signal(str)
    finished_with_result = Signal(bool, str)

    def __init__(self, manager: ServiceManager, name: str, action: str,
                 start_type: str | None = None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.name = name
        self.action = action
        self.start_type = start_type

    def run(self) -> None:
        try:
            if self.action == "stop":
                deps = self.manager.get_dependents(self.name)
                if deps:
                    self.finished_with_result.emit(
                        False, f"Есть зависимые службы: {', '.join(deps)}"
                    )
                    return
                ok, msg = self.manager.stop(self.name)
            elif self.action == "start":
                ok, msg = self.manager.start(self.name)
            elif self.action == "type" and self.start_type:
                ok, msg = self.manager.set_start_type(self.name, self.start_type)
            else:
                ok, msg = False, "Неизвестное действие"
            self.finished_with_result.emit(ok, msg)
        except Exception as exc:
            self.finished_with_result.emit(False, f"Исключение: {exc}")
