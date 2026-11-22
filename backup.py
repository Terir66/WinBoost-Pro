"""
backup.py — системное резервирование состояния служб и автозагрузки.

Создаёт JSON-копию перед оптимизацией и восстанавливает её из вкладки
«Настройки». Логику очистки кэша и служб не изменяет: использует публичные
методы уже существующего ServiceManager.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from cache import app_data_dir
from startup import collect_startup_entries, restore_startup_entries


def app_directory() -> Path:
    """Каталог приложения (для onefile — папка exe, а не временная _MEIPASS)."""
    try:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
    except Exception:
        pass
    return Path(__file__).resolve().parent


def ensure_backup_dir() -> Path:
    """
    Папка бекапов рядом с приложением. Если каталог только для чтения
    (например, Program Files) — откатываемся в %LOCALAPPDATA%\\WinBoost.
    """
    primary = app_directory() / "backups"
    try:
        primary.mkdir(parents=True, exist_ok=True)
        # проверяем, что туда действительно можно писать
        probe = primary / ".write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return primary
    except Exception:
        fallback = app_data_dir() / "backups"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return fallback


def collect_services_state(manager) -> list[dict]:
    """Список служб с типами запуска (предпочтительно через win32service)."""
    services: list[dict] = []
    try:
        import win32service  # type: ignore
        scm = win32service.OpenSCManager(
            None, None, win32service.SC_MANAGER_ALL_ACCESS
        )
        try:
            raw = win32service.EnumServicesStatus(
                scm, win32service.SERVICE_WIN32, win32service.SERVICE_STATE_ALL
            )
            for name, display, status in raw:
                try:
                    handle = win32service.OpenService(
                        scm, name, win32service.SERVICE_QUERY_CONFIG
                    )
                    config = win32service.QueryServiceConfig(handle)
                    win32service.CloseServiceHandle(handle)
                    start_type = {0: "Boot", 1: "System", 2: "Auto",
                                  3: "Manual", 4: "Disabled"}.get(config[1], "Unknown")
                except Exception:
                    start_type = "Unknown"
                state = status.get("CurrentState", 1) if isinstance(status, dict) else 1
                services.append({
                    "name": name,
                    "display_name": display,
                    "start_type": start_type,
                    "status": "Запущена" if state == win32service.SERVICE_RUNNING
                    else "Остановлена",
                })
        finally:
            try:
                win32service.CloseServiceHandle(scm)
            except Exception:
                pass
    except Exception:
        # резервный путь через уже существующий ServiceManager
        try:
            services = [
                {
                    "name": item.name,
                    "display_name": item.display_name,
                    "start_type": item.start_type,
                    "status": item.status,
                }
                for item in manager.list_services()
            ]
        except Exception:
            services = []
    return services


def create_backup(manager, reason: str = "") -> tuple[Path | None, str]:
    """Создаёт backup_ГГГГ-ММ-ДД_ЧЧ-ММ-СС.json и возвращает путь к нему."""
    folder = ensure_backup_dir()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = folder / f"backup_{stamp}.json"
    payload = {
        "version": 1,
        "created": datetime.now().isoformat(timespec="seconds"),
        "reason": reason,
        "services": collect_services_state(manager),
        "startup": [entry.to_dict() for entry in collect_startup_entries()],
    }
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path, (f"Резервная копия создана: {path.name} "
                      f"({len(payload['services'])} служб, "
                      f"{len(payload['startup'])} записей автозагрузки)")
    except Exception as exc:
        return None, f"Не удалось создать резервную копию: {exc}"


def list_backups() -> list[dict]:
    """Список копий: имя, дата, время, размер, путь."""
    result: list[dict] = []
    folder = ensure_backup_dir()
    try:
        for path in sorted(folder.glob("backup_*.json"), reverse=True):
            stamp = path.stem.replace("backup_", "")
            try:
                date, time_part = stamp.split("_", 1)
            except Exception:
                date, time_part = stamp, ""
            result.append({
                "name": path.name,
                "path": path,
                "date": date,
                "time": time_part.replace("-", ":"),
                "size": path.stat().st_size,
            })
    except Exception:
        pass
    return result


def read_backup(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def restore_backup(path: Path, manager) -> list[str]:
    """Возвращает службам и автозагрузке значения из копии."""
    messages: list[str] = []
    try:
        data = read_backup(path)
    except Exception as exc:
        return [f"Не удалось прочитать копию: {exc}"]

    for service in data.get("services", []):
        name = service.get("name", "")
        target = service.get("start_type", "Manual")
        try:
            if not manager.service_exists(name):
                messages.append(f"{name}: служба не найдена — пропущено")
                continue
            ok, msg = manager.set_start_type(name, target)
            messages.append(f"{name}: {'OK' if ok else 'ОШИБКА'} — {msg}")
        except Exception as exc:
            messages.append(f"{name}: ошибка — {exc}")

    try:
        results = restore_startup_entries(data.get("startup", []))
        messages.extend(
            f"{name}: {'OK' if ok else 'ОШИБКА'} — {msg}" for name, ok, msg in results
        )
    except Exception as exc:
        messages.append(f"Ошибка восстановления автозагрузки: {exc}")
    return messages
