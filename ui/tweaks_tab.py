"""
ui/tweaks_tab.py — вкладка «Продвинутые твики» (переписанная логика).

ИСПРАВЛЕНИЯ:
  * bcdedit после успеха вызывает диалог перезагрузки;
  * powercfg -duplicatescheme → парсится GUID → powercfg /setactive <GUID>;
  * powercfg -h off тоже требует перезагрузки/выхода;
  * реестр пишется через winreg, а не через reg add / os.system;
  * чекбокс DEBUG показывает stdout И stderr subprocess.run();
  * для диагностики ловим «Access is denied» и «The boot configuration
    data store could not be opened».

Все тяжёлые команды выполняются в QThread скрытым терминалом
(CREATE_NO_WINDOW) — чёрное окно CMD не появляется.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

try:
    import winreg
except Exception:  # pragma: no cover
    winreg = None  # type: ignore

from . import strings as S
from .system_info import elevate, is_admin

GREEN = "#4ADE80"
GRAY = "#8A96B2"
RED = "#FF5C7A"

POWER_GUID = "e9a42b02-d5df-448d-9267-d2519fac11e1"
REG_SYSTEM_PROFILE = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
REG_GAME_STORE = r"System\GameConfigStore"

ERROR_MARKERS = (
    "access is denied",
    "the boot configuration data store could not be opened",
    "отказано в доступе",
    "не удалось открыть хранилище данных конфигурации загрузки",
)


@dataclass
class Tweak:
    """Одна команда оптимизации."""
    key: str
    title: str
    description: str
    command: list[str] | str
    kind: str = "cmd"
    reboot: bool = False
    shell: bool = False
    status_hint: str = ""


TWEAKS: list[Tweak] = [
    Tweak("dynamic_tick", "Отключение Dynamic Tick",
          "(Снижает микрофризы и задержки питания процессора)",
          ["bcdedit", "/set", "disabledynamictick", "yes"],
          kind="bcdedit", reboot=True, status_hint="disabledynamictick"),
    Tweak("hpet", "Отключение HPET",
          "(Таймер высокой точности. Снижает DPC Latency и Input Lag в шутерах)",
          ["bcdedit", "/deletevalue", "useplatformclock"],
          kind="bcdedit", reboot=True, status_hint="useplatformclock"),
    Tweak("tsc", "Использование аппаратного таймера (TSC)",
          "(Синхронизирует кадры ровнее)",
          ["bcdedit", "/set", "useplatformtick", "yes"],
          kind="bcdedit", reboot=True, status_hint="useplatformtick"),
    Tweak("power_scheme", "Включение схемы «Максимальная производительность»",
          "(Разблокирует скрытую схему питания Windows)",
          ["powercfg", "-duplicatescheme", POWER_GUID],
          kind="power_scheme", status_hint="ActiveScheme"),
    Tweak("hibernate", "Отключение гибернации",
          "(Освобождает от 2 до 10 ГБ на SSD и убирает фоновую запись дампа памяти)",
          ["powercfg", "-h", "off"],
          kind="power", reboot=True, status_hint="Hiberboot"),
    Tweak("network_throttling", "Снятие лимита пропускной способности сети",
          "(Помогает с регистрацией попаданий и пингом)",
          ["reg", "add", r"HKLM\...\SystemProfile", "/v",
           "NetworkThrottlingIndex", "/t", "REG_DWORD", "/d", "4294967295", "/f"],
          kind="reg", reboot=True, status_hint="NetworkThrottlingIndex"),
    Tweak("system_responsiveness", "Максимальный приоритет для игр (System Responsiveness)",
          "(Заставляет Windows отдавать 100% ресурсов активному приложению)",
          ["reg", "add", r"HKLM\...\SystemProfile", "/v",
           "SystemResponsiveness", "/t", "REG_DWORD", "/d", "0", "/f"],
          kind="reg", reboot=True, status_hint="SystemResponsiveness"),
    Tweak("game_dvr", "Отключение GameDVR / Xbox Game Bar",
          "(Убивает встроенный оверлей Windows, который часто режет FPS)",
          ["reg", "add", r"HKCU\System\GameConfigStore", "/v",
           "GameDVR_Enabled", "/t", "REG_DWORD", "/d", "0", "/f"],
          kind="reg", status_hint="GameDVR_Enabled"),
    Tweak("dns_flush", "Очистка кэша DNS",
          "(Стабилизирует соединение с серверами)",
          ["ipconfig", "/flushdns"], kind="dns"),
    Tweak("temp_cleanup", "Жёсткая очистка временных файлов (Темп)",
          "(Удаляет мусор, который может тормозить работу диска)",
          "cmd /c del /s /f /q %temp%\\*.*",
          kind="temp", shell=True),
]


# --------------------------------------------------------------------- запуск
def _decode_output(data: bytes | None) -> str:
    """
    Консольные утилиты Windows (powercfg, bcdedit, reg) выводят текст
    в OEM-кодировке системы (на русской Windows — cp866), а не в UTF-8.
    Декодируем bytes последовательно и берём первый корректный вариант,
    чтобы в диалоге не было «кракозябр».
    """
    if not data:
        return ""
    for encoding in ("utf-8", "cp866", "cp1251"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return data.decode("cp866", errors="replace").strip()


def _run(command, shell: bool = False, timeout: int = 120) -> dict:
    """
    Скрытый запуск команды (CREATE_NO_WINDOW).
    Возвращает stdout, stderr, returncode и флаг ошибки.
    """
    result = {"stdout": "", "stderr": "", "code": -1, "ok": False}
    try:
        kwargs = {
            "capture_output": True, "timeout": timeout, "check": False,
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        }
        if shell:
            completed = subprocess.run(command, shell=True, **kwargs)
        else:
            completed = subprocess.run(command, **kwargs)
        result["stdout"] = _decode_output(completed.stdout)
        result["stderr"] = _decode_output(completed.stderr)
        result["code"] = completed.returncode
        combined = (result["stdout"] + "\n" + result["stderr"]).lower()
        has_error = any(marker in combined for marker in ERROR_MARKERS)
        result["ok"] = completed.returncode == 0 and not has_error
    except Exception as exc:
        result["stderr"] = str(exc)
    return result


def _format_output(result: dict, debug: bool) -> str:
    """В DEBUG показываем и stdout, и stderr, включая Access denied."""
    if debug:
        return (
            f"STDOUT:\n{result['stdout'] or '(пусто)'}\n"
            f"STDERR:\n{result['stderr'] or '(пусто)'}\n"
            f"Код возврата: {result['code']}"
        )
    return (result["stderr"] or result["stdout"] or "Команда выполнена")[:600]


# --------------------------------------------------------------------- реестр
def _write_registry(tweak: Tweak) -> dict:
    """Пишет DWORD через winreg (вместо os.system / reg add)."""
    result = {"stdout": "", "stderr": "", "code": 0, "ok": False}
    if winreg is None:
        result["stderr"] = "Модуль winreg недоступен"
        return result
    try:
        if tweak.key == "network_throttling":
            root, path, name, value = (
                winreg.HKEY_LOCAL_MACHINE, REG_SYSTEM_PROFILE,
                "NetworkThrottlingIndex", 0xFFFFFFFF,
            )
        elif tweak.key == "system_responsiveness":
            root, path, name, value = (
                winreg.HKEY_LOCAL_MACHINE, REG_SYSTEM_PROFILE,
                "SystemResponsiveness", 0,
            )
        elif tweak.key == "game_dvr":
            root, path, name, value = (
                winreg.HKEY_CURRENT_USER, REG_GAME_STORE, "GameDVR_Enabled", 0
            )
        else:
            result["stderr"] = "Неизвестный твик реестра"
            return result

        view = winreg.KEY_WOW64_64KEY  # явный 64-bit view
        key = winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE | view)
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
        finally:
            winreg.CloseKey(key)
        result["ok"] = True
        result["stdout"] = f"{name} = {value} (REG_DWORD)"
    except PermissionError:
        result["stderr"] = "Access is denied — нужны права администратора"
    except Exception as exc:
        result["stderr"] = str(exc)
    return result


def _apply_tweak(tweak: Tweak) -> dict:
    """
    Выполняет один твик и возвращает result:
    ok / output / need_reboot. Используется и одиночным, и пакетным воркером.
    """
    need_reboot = False
    try:
        if tweak.kind == "reg":
            result = _write_registry(tweak)
            need_reboot = bool(tweak.reboot and result["ok"])
        elif tweak.kind == "power_scheme":
            # 1) дублируем скрытую схему
            result = _run(tweak.command)
            # 2) выхватываем GUID из stdout и активируем дубликат
            new_guid = ""
            if result["ok"]:
                match = re.search(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                    r"[0-9a-f]{4}-[0-9a-f]{12}",
                    result["stdout"], re.IGNORECASE,
                )
                if match:
                    new_guid = match.group(0)
            if new_guid:
                activation = _run(["powercfg", "/setactive", new_guid])
                result["stdout"] += (
                    f"\nАктивация схемы {new_guid}: {activation['stdout']}"
                )
                result["stderr"] += ("\n" + activation["stderr"]).strip("\n")
                result["ok"] = result["ok"] and activation["ok"]
                result["code"] = activation["code"]
            elif result["ok"]:
                result["ok"] = False
                result["stderr"] = "GUID новой схемы не найден в выводе powercfg"
        else:
            result = _run(tweak.command, shell=tweak.shell)
            # bcdedit и powercfg -h off требуют перезагрузки
            need_reboot = bool(tweak.reboot and result["ok"])
    except Exception as exc:
        result = {"stdout": "", "stderr": str(exc), "code": -1, "ok": False}
    return {
        "ok": bool(result["ok"]),
        "output": _format_output(result, _DEBUG_HOLDER["debug"]),
        "need_reboot": need_reboot,
    }


# флаг DEBUG выставляется перед запуском воркера из вкладки
_DEBUG_HOLDER = {"debug": False}


# --------------------------------------------------------------------- потоки
class TweakApplyWorker(QThread):
    """Применяет твик и возвращает полный вывод для DEBUG."""
    finished_with_result = Signal(object, bool, str, bool)  # tweak, ok, output, reboot

    def __init__(self, tweak: Tweak, debug: bool = False, parent=None):
        super().__init__(parent)
        self.tweak = tweak
        self.debug = debug

    def run(self) -> None:
        _DEBUG_HOLDER["debug"] = self.debug
        result = _apply_tweak(self.tweak)
        self.finished_with_result.emit(
            self.tweak, result["ok"], result["output"], result["need_reboot"]
        )


class TweakBatchApplyWorker(QThread):
    """Последовательно применяет выбранные твики."""
    item_done = Signal(object, bool, str, bool)   # tweak, ok, output, reboot
    finished_with_summary = Signal(int, int)     # ok, total

    def __init__(self, tweaks: list[Tweak], debug: bool = False, parent=None):
        super().__init__(parent)
        self.tweaks = tweaks
        self.debug = debug

    def run(self) -> None:
        _DEBUG_HOLDER["debug"] = self.debug
        ok_count = 0
        for tweak in self.tweaks:
            try:
                result = _apply_tweak(tweak)
                ok = result["ok"]
                output = result["output"]
                reboot = result["need_reboot"]
            except Exception as exc:
                ok, output, reboot = False, str(exc), False
            if ok:
                ok_count += 1
            self.item_done.emit(tweak, ok, output, reboot)
        self.finished_with_summary.emit(ok_count, len(self.tweaks))


class TweakStatusWorker(QThread):
    """Проверяет текущее значение через bcdedit / winreg / powercfg."""
    finished_with_status = Signal(object, str)

    def __init__(self, tweak: Tweak, debug: bool = False, parent=None):
        super().__init__(parent)
        self.tweak = tweak
        self.debug = debug

    def run(self) -> None:
        tweak = self.tweak
        try:
            if tweak.kind == "bcdedit":
                res = _run(["bcdedit", "/enum"], timeout=40)
                lines = [line.strip() for line in res["stdout"].splitlines()
                         if tweak.status_hint.lower() in line.lower()]
                text = "\n".join(lines[:8]) or "Параметр не найден в bcdedit /enum"
                if self.debug:
                    text += "\n" + _format_output(res, True)
            elif tweak.kind == "reg":
                if winreg is None:
                    text = "winreg недоступен"
                else:
                    root, path = (
                        (winreg.HKEY_LOCAL_MACHINE, REG_SYSTEM_PROFILE)
                        if tweak.key != "game_dvr"
                        else (winreg.HKEY_CURRENT_USER, REG_GAME_STORE)
                    )
                    key = winreg.OpenKey(
                        root, path, 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                    )
                    try:
                        value, _type = winreg.QueryValueEx(key, tweak.status_hint)
                        text = f"{tweak.status_hint} = {value}"
                    finally:
                        winreg.CloseKey(key)
            elif tweak.kind == "power_scheme":
                text = _run(["powercfg", "/getactivescheme"])["stdout"]
            elif tweak.kind == "temp":
                folder = Path(os.environ.get("TEMP", ""))
                count = size = 0
                if folder.exists():
                    for path in folder.rglob("*"):
                        try:
                            if path.is_file():
                                count += 1
                                size += path.stat().st_size
                        except Exception:
                            continue
                text = f"Файлов во Temp: {count}; размер {size / (1024*1024):.1f} МБ"
            else:
                text = "Команда не имеет постоянного состояния (выполняется каждый раз)."
        except Exception as exc:
            text = f"Ошибка проверки: {exc}"
        self.finished_with_status.emit(tweak, text[:1500])


# --------------------------------------------------------------------- строка
class TweakRow(QWidget):
    """Строка: чекбокс + описание + статус + кнопка проверки."""
    toggled_by_user = Signal(object, bool)
    check_requested = Signal(object)

    def __init__(self, tweak: Tweak, parent=None):
        super().__init__(parent)
        self.tweak = tweak
        self._programmatic = False

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(10)

        self.checkbox = QCheckBox()
        self.checkbox.setToolTip(tweak.title)
        self.checkbox.stateChanged.connect(self._on_state_changed)

        text = f"{tweak.title} {tweak.description}"
        if tweak.reboot:
            text += S.REBOOT_NOTE
        self.title_label = QLabel(text)
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumHeight(34)

        self.status_label = QLabel("")
        self.status_label.setObjectName("subtitle")
        self.status_label.setMinimumWidth(120)

        self.check_btn = QPushButton(S.BTN_CHECK_STATUS)
        self.check_btn.clicked.connect(lambda: self.check_requested.emit(self.tweak))

        row.addWidget(self.checkbox)
        row.addWidget(self.title_label, stretch=1)
        row.addWidget(self.status_label)
        row.addWidget(self.check_btn)

    def _on_state_changed(self, state) -> None:
        if not self._programmatic:
            self.toggled_by_user.emit(self.tweak, state == Qt.Checked)

    def set_checked(self, checked: bool) -> None:
        self._programmatic = True
        try:
            self.checkbox.setChecked(checked)
        finally:
            self._programmatic = False

    def mark_applied(self, reboot: bool) -> None:
        self.set_checked(True)
        color = GRAY if reboot else GREEN
        self.checkbox.setStyleSheet(f"QCheckBox {{ color: {color}; font-weight: 700; }}")
        self.title_label.setStyleSheet(f"color: {color};")
        self.status_label.setText("Применено · перезагрузка" if reboot else "Применено")
        self.status_label.setStyleSheet(f"color: {color};")

    def mark_failed(self) -> None:
        self.set_checked(False)
        self.status_label.setText("Ошибка")
        self.status_label.setStyleSheet(f"color: {RED};")


# --------------------------------------------------------------------- вкладка
class TweaksTab(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.apply_worker = None
        self.batch_worker = None
        self.status_worker = None
        self.rows: dict[str, TweakRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title = QLabel(S.TWEAKS_TITLE)
        title.setObjectName("heroTitle")
        subtitle = QLabel(S.TWEAKS_SUBTITLE)
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        banner = QLabel(S.TWEAK_BSOD_WARNING.split(".")[0] + ".")
        banner.setObjectName("sectionTitle")
        banner.setWordWrap(True)
        banner.setMinimumHeight(30)
        layout.addWidget(banner)

        # Пакетное управление: выбрать → Начать. Бекап создаётся автоматически.
        batch_row = QHBoxLayout()
        self.select_all_btn = QPushButton(S.BTN_SELECT_ALL)
        self.clear_btn = QPushButton(S.BTN_CLEAR_SELECTION)
        self.start_btn = QPushButton(S.BTN_START_TWEAKS)
        self.start_btn.setObjectName("accent")
        self.select_all_btn.clicked.connect(self._select_all)
        self.clear_btn.clicked.connect(self._clear_selection)
        self.start_btn.clicked.connect(self._start_batch)
        batch_row.addWidget(self.select_all_btn)
        batch_row.addWidget(self.clear_btn)
        batch_row.addWidget(self.start_btn)
        batch_row.addStretch()
        layout.addLayout(batch_row)

        # ЧЕКБОКС ДИАГНОСТИКИ: показывает stdout и stderr команд
        self.debug_check = QCheckBox(S.DEBUG_CHECKBOX)
        layout.addWidget(self.debug_check)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.list_widget, stretch=1)

        self.log = QLabel("")
        self.log.setObjectName("subtitle")
        self.log.setWordWrap(True)
        self.log.setMinimumHeight(28)
        layout.addWidget(self.log)

        for tweak in TWEAKS:
            row = TweakRow(tweak)
            row.toggled_by_user.connect(self._on_toggle)
            row.check_requested.connect(self._check_status)
            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(row.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)
            self.rows[tweak.key] = row

    @staticmethod
    def _is_laptop() -> bool:
        """
        ПРОВЕРКА НА НОУТБУК:
        psutil.sensors_battery() либо Intel в platform.processor().
        """
        try:
            import psutil
            if psutil.sensors_battery() is not None:
                return True
        except Exception:
            pass
        try:
            return "intel" in (platform.processor() or "").lower()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # чекбокс теперь ТОЛЬКО выбирает твик; выполнение — по кнопке «Начать»
    def _on_toggle(self, tweak: Tweak, checked: bool) -> None:
        selected = self._selected_tweaks()
        self.log.setText(S.TWEAK_SELECTED_COUNT.format(count=len(selected)))

    def _selected_tweaks(self) -> list[Tweak]:
        return [tweak for tweak in TWEAKS
                if self.rows[tweak.key].checkbox.isChecked()]

    def _select_all(self) -> None:
        for row in self.rows.values():
            row.set_checked(True)
        self.log.setText(S.TWEAK_SELECTED_COUNT.format(count=len(TWEAKS)))

    def _clear_selection(self) -> None:
        for row in self.rows.values():
            row.set_checked(False)
        self.log.setText(S.TWEAK_SELECTED_COUNT.format(count=0))

    def _start_batch(self) -> None:
        selected = self._selected_tweaks()
        if not selected:
            QMessageBox.information(self, S.TWEAKS_TITLE, S.TWEAK_NOTHING_SELECTED)
            return

        # ГАРАНТИРОВАННЫЕ ПРАВА: если их нет — перезапуск через UAC
        if not is_admin():
            if QMessageBox.question(
                self, S.WARNING, S.TWEAK_NO_ADMIN,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) == QMessageBox.Yes:
                elevate()
            return

        # АВТОМАТИЧЕСКИЙ БЕКАП без диалога
        path, message = self.main.create_backup_auto("tweaks:" + ",".join(
            tweak.key for tweak in selected
        ))
        if path is None:
            QMessageBox.warning(self, S.ERROR, message)
            return
        self.log.setText(S.TWEAK_BACKUP_DONE.format(name=path.name))

        names = ", ".join(tweak.title for tweak in selected)
        warning = S.TWEAK_BSOD_WARNING.format(name=names)
        # ПРОВЕРКА НОУТБУКА → дополнительный абзац про звук и микрофон
        if self._is_laptop():
            warning += "\n\n" + S.TWEAK_LAPTOP_WARNING
        warning += "\n\n" + S.TWEAK_AUTO_BACKUP_NOTE

        # ПРЕДУПРЕЖДЕНИЕ О BSOD до применения ЛЮБОЙ команды
        dialog = QMessageBox(self)
        dialog.setWindowTitle(S.WARNING)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setText(warning)
        cancel_button = dialog.addButton(QMessageBox.Cancel)
        cancel_button.setText(S.CANCEL)
        apply_button = dialog.addButton(QMessageBox.Apply)
        apply_button.setText(S.BTN_APPLY)
        dialog.setDefaultButton(QMessageBox.Cancel)
        dialog.exec()
        if dialog.clickedButton() is not apply_button:
            return

        # «Жёсткая очистка Temp» — отдельное подтверждение перед удалением
        if any(tweak.key == "temp_cleanup" for tweak in selected):
            if QMessageBox.question(
                self, S.WARNING, S.TWEAK_TEMP_CONFIRM,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return

        if self.batch_worker and self.batch_worker.isRunning():
            self.log.setText("Уже выполняется пакет твиков.")
            return

        self.start_btn.setEnabled(False)
        self.log.setText(f"Применение {len(selected)} твиков …")
        worker = TweakBatchApplyWorker(
            selected, self.debug_check.isChecked(), self
        )
        worker.item_done.connect(self._on_batch_item)
        worker.finished_with_summary.connect(self._on_batch_done)
        self.batch_worker = worker
        worker.start()

    def _on_batch_item(self, tweak: Tweak, ok: bool, output: str,
                       need_reboot: bool) -> None:
        row = self.rows[tweak.key]
        if ok:
            row.mark_applied(tweak.reboot)
            text = S.TWEAK_REBOOT_REQUIRED.format(name=tweak.title) \
                if tweak.reboot else S.TWEAK_DONE.format(name=tweak.title)
            self.log.setText(f"{text}\n{output[:600]}")
        else:
            row.mark_failed()
            self.log.setText(S.TWEAK_FAILED.format(name=tweak.title, error=output[:600]))
        self.main.service_log.emit(
            f"[Твик] {tweak.title}: {'OK' if ok else 'ОШИБКА'} — {output[:300]}"
        )
        if ok and need_reboot:
            self._pending_reboot = True

    def _on_batch_done(self, ok: int, total: int) -> None:
        self.start_btn.setEnabled(True)
        self.log.setText(S.TWEAK_BATCH_DONE.format(ok=ok, total=total))
        if getattr(self, "_pending_reboot", False):
            self._pending_reboot = False
            self._ask_reboot()

    def _ask_reboot(self) -> None:
        """Точное предупреждение после bcdedit / гибернации."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle(S.WARNING)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setText(S.TWEAK_REBOOT_QUESTION)
        reboot_button = dialog.addButton(S.BTN_REBOOT_NOW, QMessageBox.AcceptRole)
        dialog.addButton(S.BTN_LATER, QMessageBox.RejectRole)
        dialog.setDefaultButton(reboot_button)
        dialog.exec()
        if dialog.clickedButton() is reboot_button:
            _run(["shutdown", "/r", "/t", "5"])

    def _check_status(self, tweak: Tweak) -> None:
        if self.status_worker and self.status_worker.isRunning():
            return
        self.log.setText(f"Проверка статуса: {tweak.title} …")
        worker = TweakStatusWorker(tweak, self.debug_check.isChecked(), self)
        worker.finished_with_status.connect(self._on_status)
        self.status_worker = worker
        worker.start()

    def _on_status(self, tweak: Tweak, text: str) -> None:
        self.log.setText(f"{tweak.title}: {text[:300]}")
        QMessageBox.information(
            self, S.TWEAK_STATUS_TITLE,
            f"<b>{tweak.title}</b><br><pre>{text}</pre>",
        )
