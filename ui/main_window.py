"""
ui/main_window.py — главное окно WinBoost Pro.

Сайдбар (70px) + QStackedWidget из 5 экранов, переключатель тем с вращением
иконки, вся координация фоновых потоков (логика осталась в ядре).
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
    QMenu, QMessageBox, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from backup import create_backup, list_backups, restore_backup
from startup import StartupEntry

from cache import (
    APP_NAME, APP_VERSION, CacheCleanWorker, CacheScanWorker, human_size,
)
from services import (
    ServiceApplyWorker, ServiceControlWorker, ServiceManager, ServicePlanWorker,
    ServiceRestoreWorker, ServiceScanWorker,
)
from uninstaller import (
    CleanupWorker, InstalledApp, LeftoverScanWorker, UninstallScanWorker,
    UninstallWorker, Uninstaller,
)

from . import strings as S
from .theme import apply_theme, apply_text_fonts, icon
from .widgets import (
    AnimatedButton, CircularProgress, NavButton, RotatingThemeButton,
)
from .dashboard import DashboardScreen
from .clean_screen import CleanScreen
from .services_screen import ServicesScreen
from .programs_screen import ProgramsScreen
from .autostart_screen import AutostartScreen, StartupActionWorker, StartupScanWorker
from .settings_screen import SettingsScreen
from .tweaks_tab import TweaksTab
from .system_info import (
    cpu_name, free_ram_gb, gpu_name, is_admin, windows_version,
)

SETTINGS_FILE = Path.home() / ".winboost_pro_settings.json"


def _load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    # BoosterX-подобный интерфейс по умолчанию тёмный
    return {"theme": "dark"}


def _save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


class MainWindow(QMainWindow):
    # сигналы, к которым подключаются экраны
    clean_progress = Signal(int)
    clean_log = Signal(str)
    clean_state = Signal(bool)
    scan_result = Signal(int)

    service_progress = Signal(int)
    service_log = Signal(str)
    service_state = Signal(bool)
    services_ready = Signal(object)
    plan_ready = Signal(object)

    apps_progress = Signal(int)
    apps_log = Signal(str)
    apps_state = Signal(bool)
    apps_ready = Signal(object)
    leftovers_ready = Signal(object, object)

    startup_ready = Signal(object)
    startup_log = Signal(str)
    startup_action_done = Signal(object, bool, str)
    backup_status = Signal(str)

    NAV_ITEMS = [
        ("fa.home", S.NAV_HOME),
        ("fa.paint_brush", S.NAV_CLEAN),
        ("fa.gear", S.NAV_SERVICES),
        ("fa.trash", S.NAV_PROGRAMS),
        ("fa.star", S.NAV_STARTUP),
        ("fa5s.microchip", S.NAV_TWEAKS),
        ("fa.sliders-h", S.NAV_SETTINGS),
    ]

    def __init__(self):
        super().__init__()
        self.settings = _load_settings()
        self.service_manager = ServiceManager()
        self.uninstaller = Uninstaller()

        self.clean_worker = None
        self.service_worker = None
        self.plan_worker = None
        self.apply_worker = None
        self.control_worker = None
        self.apps_worker = None
        self.uninstall_worker = None
        self.leftover_worker = None
        self.cleanup_worker = None
        self.startup_worker = None
        self.startup_action_worker = None
        self._services_loaded_once = False
        self._apps_loaded_once = False
        self._startup_loaded_once = False

        self.setWindowTitle(f"{APP_NAME} Pro v{APP_VERSION}")
        try:
            self.setWindowIcon(icon("fa.gear", color="#0067c0"))
        except Exception:
            pass
        self.setMinimumSize(1120, 760)

        apply_theme(QApplication.instance(), self.settings.get("theme", "light"))
        self._build_menu()
        self._build_shell()
        self._build_tray()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_statusbar)
        self.status_timer.start(30000)
        self._refresh_statusbar()

        self.service_log.emit(
            f"{APP_NAME} Pro v{APP_VERSION} готов. "
            f"Права администратора: {'да' if is_admin() else 'нет'}"
        )
        if not is_admin():
            self.service_log.emit(
                "Для управления службами запустите приложение от имени администратора."
            )

    # ---------------------------------------------------------------- каркас
    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu(S.MENU_FILE)
        toggle = QAction(S.MENU_TOGGLE_THEME, self)
        toggle.triggered.connect(self.toggle_theme)
        file_menu.addAction(toggle)
        exit_action = QAction(S.MENU_EXIT, self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = bar.addMenu(S.MENU_HELP)
        about = QAction(S.MENU_ABOUT, self)
        about.triggered.connect(self.show_about)
        help_menu.addAction(about)

    def _build_shell(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # верхняя панель с переключателем темы в правом верхнем углу
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(64)
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(24, 8, 20, 8)
        logo = QLabel("W")
        logo.setObjectName("logoMark")
        logo.setFixedSize(36, 36)
        logo.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(logo)

        brand = QLabel(S.APP_BRAND)
        brand.setObjectName("brand")
        brand_version = QLabel(f"v{APP_VERSION} · {S.APP_DESCRIPTION}")
        brand_version.setObjectName("subtitle")
        top_layout.addWidget(brand)
        top_layout.addWidget(brand_version)
        top_layout.addStretch()

        self.theme_btn = RotatingThemeButton()
        self.theme_btn.set_icon_for_theme(self.settings.get("theme") == "dark")
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_layout.addWidget(self.theme_btn)
        root.addWidget(topbar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # боковая панель 70px
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(76)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(8, 12, 8, 12)
        side_layout.setSpacing(6)

        side_logo = QLabel("W")
        side_logo.setObjectName("logoMark")
        side_logo.setFixedSize(40, 40)
        side_logo.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(side_logo, alignment=Qt.AlignCenter)
        side_layout.addSpacing(8)

        self.nav_buttons: list[NavButton] = []
        for index, (icon_name, label) in enumerate(self.NAV_ITEMS):
            btn = NavButton(icon_name, label)
            btn.setObjectName("navBtn")
            btn.setProperty("active", index == 0)
            btn.setChecked(index == 0)
            btn.set_icon(icon_name, "#ffffff" if index == 0 else None)
            btn.clicked.connect(lambda _checked=False, i=index: self.switch_to(i))
            side_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        side_layout.addStretch()
        body.addWidget(self.sidebar)

        # экраны
        self.stack = QStackedWidget()
        self.screens = [
            DashboardScreen(self),
            CleanScreen(self),
            ServicesScreen(self),
            ProgramsScreen(self),
            AutostartScreen(self),
            TweaksTab(self),
            SettingsScreen(self),
        ]
        for screen in self.screens:
            self.stack.addWidget(screen)
        # кириллический шрифт для всех текстовых виджетов
        apply_text_fonts(self)
        body.addWidget(self.stack, stretch=1)
        root.addLayout(body)

        self.statusBar().showMessage("Готово")
        self.lbl_win = QLabel()
        self.lbl_cpu = QLabel()
        self.lbl_gpu = QLabel()
        self.lbl_ram = QLabel()
        self.lbl_win.setMaximumWidth(260)
        self.lbl_cpu.setMaximumWidth(320)
        self.lbl_gpu.setMaximumWidth(260)
        self.lbl_ram.setMaximumWidth(190)
        for label in (self.lbl_win, self.lbl_cpu, self.lbl_gpu, self.lbl_ram):
            label.setToolTip(label.text())
            self.statusBar().addPermanentWidget(label)

    def switch_to(self, index: int) -> None:
        try:
            self.stack.setCurrentIndex(index)
            # ленивая загрузка тяжёлых списков — при первом открытии вкладки
            if index == 2 and not self._services_loaded_once:
                self.scan_services()
            if index == 3 and not self._apps_loaded_once:
                self.scan_apps()
            if index == 4 and not self._startup_loaded_once:
                self.scan_startup()
            if index == 6:
                try:
                    self.screens[6].refresh()
                except Exception:
                    pass
            for i, btn in enumerate(self.nav_buttons):
                active = i == index
                btn.setChecked(active)
                btn.setProperty("active", active)
                btn.set_icon(self.NAV_ITEMS[i][0], "#ffffff" if active else None)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        except Exception:
            pass

    def _refresh_statusbar(self) -> None:
        try:
            self.lbl_win.setText(f"OC: {windows_version()}")
            self.lbl_cpu.setText(f"CPU: {cpu_name()[:40]}")
            self.lbl_gpu.setText(f"GPU: {gpu_name()[:34]}")
            self.lbl_ram.setText(f"{S.FREE_RAM_PREFIX}{free_ram_gb():.1f} ГБ")
        except Exception:
            pass

    # ---------------------------------------------------------------- тема
    def toggle_theme(self) -> None:
        try:
            theme = "dark" if self.settings.get("theme", "light") == "light" else "light"
            self.settings["theme"] = theme
            apply_theme(QApplication.instance(), theme)
            self.theme_btn.spin(theme == "dark")
            self._update_accent_colors(theme)
            _save_settings(self.settings)
            self.service_log.emit(f"Тема оформления: {theme}")
        except Exception as exc:
            self.service_log.emit(f"Ошибка смены темы: {exc}")

    def _update_accent_colors(self, theme: str) -> None:
        accent, track = ("#3b93ff", "#3a3c41") if theme == "dark" \
            else ("#0067c0", "#dfe4ec")
        try:
            for widget in self.findChildren(CircularProgress):
                widget.set_colors(accent, track)
            for widget in self.findChildren(QWidget):
                try:
                    self.style().unpolish(widget)
                    self.style().polish(widget)
                except Exception:
                    continue
        except Exception:
            pass

    def show_about(self) -> None:
        QMessageBox.about(
            self, S.MENU_ABOUT,
            f"<b>WinBoost Pro</b> — {S.APP_DESCRIPTION}<br>Версия {APP_VERSION}<br><br>"
            "Очистка кэша, управление службами, деинсталлятор и мониторинг "
            "автозагрузки.<br>Построено на PySide6 (Qt).",
        )

    # ---------------------------------------------------------------- backup
    def create_backup_auto(self, reason: str = "") -> tuple:
        """Бекап без диалога — используется пакетным применением твиков."""
        path, message = create_backup(self.service_manager, reason)
        self.service_log.emit(message)
        self.backup_status.emit(message)
        if path is not None:
            try:
                self.screens[6].refresh()
            except Exception:
                pass
        return path, message

    def confirm_backup(self, reason: str = "") -> bool:
        """
        Общий диалог перед любой оптимизацией.
        Возвращает False только если копия была запрошена, но не создалась.
        """
        answer = QMessageBox.question(
            self, S.BACKUP_TITLE, S.BACKUP_QUESTION,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return True
        path, message = create_backup(self.service_manager, reason)
        self.service_log.emit(message)
        self.backup_status.emit(message)
        if path is None:
            QMessageBox.warning(self, S.ERROR, message)
            return False
        if reason.startswith("startup:"):
            self.screens[5].refresh()
        return True

    def restore_backup(self, path) -> None:
        messages = restore_backup(path, self.service_manager)
        ok = sum(1 for line in messages if line.endswith("OK") or "OK —" in line)
        summary = S.BACKUP_RESTORED.format(ok=ok, total=len(messages))
        self.backup_status.emit(summary)
        self.service_log.emit(summary)
        for line in messages:
            self.service_log.emit(line)
        self.scan_services()
        self.scan_startup()

    # ---------------------------------------------------------------- трей
    def _build_tray(self) -> None:
        try:
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip(S.APP_BRAND)
            menu = QMenu()
            show = menu.addAction(S.TRAY_SHOW)
            show.triggered.connect(self.showNormal)
            quit_action = menu.addAction(S.MENU_EXIT)
            quit_action.triggered.connect(self.close)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(
                lambda reason: self.showNormal()
                if reason == QSystemTrayIcon.DoubleClick else None
            )
            self.tray.show()
        except Exception:
            self.tray = None

    def notify(self, title: str, text: str) -> None:
        try:
            if self.tray and self.tray.supportsMessages():
                self.tray.showMessage(title, text, QSystemTrayIcon.Information, 5000)
        except Exception:
            pass

    # ---------------------------------------------------------------- очистка
    def start_scan(self, keys: list[str]) -> None:
        if self.clean_worker and self.clean_worker.isRunning():
            return
        try:
            self.clean_state.emit(True)
            self.clean_progress.emit(0)
            self.clean_log.emit("--- Сканирование ---")
            worker = CacheScanWorker(keys, self)
            worker.progress.connect(self.clean_progress)
            worker.error.connect(self.clean_log)
            worker.finished_with_result.connect(self._on_scan_result)
            self.clean_worker = worker
            worker.start()
        except Exception as exc:
            self.clean_state.emit(False)
            self.clean_log.emit(f"Ошибка запуска сканирования: {exc}")

    def _on_scan_result(self, result) -> None:
        self.clean_state.emit(False)
        self.clean_progress.emit(100)
        try:
            self.clean_log.emit(f"Доступно к очистке: {human_size(result.total)}")
            for key, size in result.sizes.items():
                self.clean_log.emit(f"  • {key}: {human_size(size)}")
            self.scan_result.emit(result.total)
            if result.blocked:
                lines = [f"{key}: {', '.join(procs)}"
                         for key, procs in result.blocked.items()]
                QMessageBox.warning(
                    self, S.CLOSE_BROWSERS_TITLE,
                    "Процессы мешают очистке:\n\n" + "\n".join(lines)
                    + "\n\nЗакройте их и повторите.",
                )
        except Exception as exc:
            self.clean_log.emit(f"Ошибка обработки результата: {exc}")

    def start_clean(self, keys: list[str]) -> None:
        if self.clean_worker and self.clean_worker.isRunning():
            return
        try:
            self.clean_state.emit(True)
            self.clean_log.emit("--- Проверка запущенных процессов ---")
            worker = CacheScanWorker(keys, self)
            worker.finished_with_result.connect(
                lambda result: self._on_preclean_check(result, keys)
            )
            self.clean_worker = worker
            worker.start()
        except Exception as exc:
            self.clean_state.emit(False)
            self.clean_log.emit(f"Ошибка проверки процессов: {exc}")

    def _on_preclean_check(self, result, keys: list[str]) -> None:
        try:
            if result.blocked:
                lines = [f"{key}: {', '.join(procs)}"
                         for key, procs in result.blocked.items()]
                answer = QMessageBox.warning(
                    self, S.BROWSER_RUNNING_TITLE,
                    "Закройте процессы:\n\n" + "\n".join(lines)
                    + "\n\nПосле закрытия нажмите «Повторить».",
                    QMessageBox.Retry | QMessageBox.Cancel, QMessageBox.Retry,
                )
                if answer == QMessageBox.Retry:
                    worker = CacheScanWorker(keys, self)
                    worker.finished_with_result.connect(
                        lambda res: self._on_preclean_check(res, keys)
                    )
                    self.clean_worker = worker
                    worker.start()
                    return
                self.clean_state.emit(False)
                self.clean_log.emit("Очистка отменена.")
                return
        except Exception as exc:
            self.clean_log.emit(f"Ошибка проверки: {exc}")

        if QMessageBox.question(
            self, S.CONFIRM_CLEAN_TITLE, S.CONFIRM_CLEAN_TEXT,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            self.clean_state.emit(False)
            return

        if not self.confirm_backup("clean"):
            self.clean_state.emit(False)
            return

        try:
            self.clean_state.emit(True)
            self.clean_progress.emit(0)
            self.clean_log.emit("--- Очистка ---")
            worker = CacheCleanWorker(keys, self)
            worker.log.connect(self.clean_log)
            worker.progress.connect(self.clean_progress)
            worker.file_removed.connect(
                lambda _path, size: self.clean_log.emit(
                    f"    освобождено {human_size(size)}"
                )
            )
            worker.finished_with_stats.connect(self._on_clean_done)
            self.clean_worker = worker
            worker.start()
        except Exception as exc:
            self.clean_state.emit(False)
            self.clean_log.emit(f"Ошибка запуска очистки: {exc}")

    def _on_clean_done(self, dirs: int, files: int, freed: int) -> None:
        self.clean_state.emit(False)
        self.clean_progress.emit(100)
        self.clean_log.emit(
            f"Удалено папок: {dirs}, файлов: {files}. Освобождено: {human_size(freed)}"
        )
        self.notify(S.APP_BRAND, f"Очистка завершена: {human_size(freed)}")

    # ---------------------------------------------------------------- службы
    def scan_services(self) -> None:
        if self.service_worker and self.service_worker.isRunning():
            return
        try:
            self.service_state.emit(True)
            self.service_log.emit("--- Обновление списка служб ---")
            worker = ServiceScanWorker(self.service_manager, self)
            worker.log.connect(self.service_log)
            worker.finished_with_result.connect(self._on_services_loaded)
            self.service_worker = worker
            worker.start()
        except Exception as exc:
            self.service_state.emit(False)
            self.service_log.emit(f"Ошибка сканирования служб: {exc}")

    def _on_services_loaded(self, services) -> None:
        self.service_state.emit(False)
        self._services_loaded_once = True
        self.services_ready.emit(services)

    def plan_profile(self, profile: str) -> None:
        if not is_admin():
            QMessageBox.warning(self, S.ERROR, S.ADMIN_REQUIRED)
            return
        if profile == "Максимальная производительность":
            if QMessageBox.warning(
                self, S.WARNING,
                S.PROFILE_MAX_WARNING,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return
        if not self.confirm_backup("profile:" + profile):
            return
        try:
            self.service_state.emit(True)
            self.service_log.emit(f"--- План профиля «{profile}» ---")
            worker = ServicePlanWorker(self.service_manager, profile, self)
            worker.log.connect(self.service_log)
            worker.finished_with_plan.connect(self._on_plan_ready)
            self.plan_worker = worker
            worker.start()
        except Exception as exc:
            self.service_state.emit(False)
            self.service_log.emit(f"Ошибка построения плана: {exc}")

    def _on_plan_ready(self, plan) -> None:
        self.service_state.emit(False)
        self.plan_ready.emit(plan)

    def apply_plan(self, plan) -> None:
        try:
            self.service_state.emit(True)
            worker = ServiceApplyWorker(self.service_manager, plan, self)
            worker.log.connect(self.service_log)
            worker.finished_with_results.connect(self._on_plan_applied)
            self.apply_worker = worker
            worker.start()
        except Exception as exc:
            self.service_state.emit(False)
            self.service_log.emit(f"Ошибка применения плана: {exc}")

    def _on_plan_applied(self, results) -> None:
        self.service_state.emit(False)
        ok = sum(1 for item in results if item.ok)
        self.service_log.emit(f"Применено: {ok} из {len(results)}")
        self.notify(S.APP_BRAND, f"Профиль применён: {ok}/{len(results)}")
        self.scan_services()

    def control_service(self, name: str, action: str) -> None:
        if not is_admin():
            QMessageBox.warning(self, S.ERROR, S.ADMIN_REQUIRED)
            return
        start_type = None
        if action == "type":
            current = self.service_manager.get_start_type(name)
            choices = ["Auto", "Manual", "Disabled"]
            value, accepted = QInputDialog.getItem(
                self, S.BTN_CHANGE_TYPE, f"Служба: {name}\nСейчас: {current}",
                choices, choices.index(current) if current in choices else 1, False,
            )
            if not accepted:
                return
            start_type = value
        try:
            self.service_state.emit(True)
            worker = ServiceControlWorker(
                self.service_manager, name, action, start_type, self
            )
            worker.log.connect(self.service_log)
            worker.finished_with_result.connect(self._on_service_control_done)
            self.control_worker = worker
            worker.start()
        except Exception as exc:
            self.service_state.emit(False)
            self.service_log.emit(f"Ошибка управления службой: {exc}")

    def _on_service_control_done(self, ok: bool, msg: str) -> None:
        self.service_state.emit(False)
        self.service_log.emit(f"{'OK' if ok else 'ОШИБКА'}: {msg}")
        self.scan_services()

    def restore_services(self) -> None:
        if not is_admin():
            QMessageBox.warning(self, S.ERROR, S.ADMIN_REQUIRED)
            return
        if QMessageBox.question(
            self, S.RESTORE_TITLE, "Восстановить исходные типы запуска?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            self.service_state.emit(True)
            worker = ServiceRestoreWorker(self.service_manager, self)
            worker.log.connect(self.service_log)
            worker.finished_with_results.connect(self._on_plan_applied)
            self.control_worker = worker
            worker.start()
        except Exception as exc:
            self.service_state.emit(False)
            self.service_log.emit(f"Ошибка восстановления: {exc}")

    # ---------------------------------------------------------------- автозагрузка
    def scan_startup(self) -> None:
        if self.startup_worker and self.startup_worker.isRunning():
            return
        try:
            self.startup_log.emit("Сканирование автозагрузки…")
            worker = StartupScanWorker(self)
            worker.log.connect(self.startup_log)
            worker.finished_with_entries.connect(self._on_startup_entries)
            self.startup_worker = worker
            worker.start()
        except Exception as exc:
            self.startup_log.emit(S.STARTUP_SCAN_ERROR.format(error=exc))

    def _on_startup_entries(self, entries) -> None:
        self._startup_loaded_once = True
        self.startup_ready.emit(entries)

    def apply_startup_action(self, entry: StartupEntry, action: str) -> None:
        if self.startup_action_worker and self.startup_action_worker.isRunning():
            return
        try:
            worker = StartupActionWorker(entry, action, self)
            worker.finished_with_result.connect(self.startup_action_done)
            self.startup_action_worker = worker
            worker.start()
        except Exception as exc:
            self.startup_log.emit(S.STARTUP_SCAN_ERROR.format(error=exc))

    # ---------------------------------------------------------------- программы
    def scan_apps(self) -> None:
        if self.apps_worker and self.apps_worker.isRunning():
            return
        try:
            self.apps_state.emit(True)
            self.apps_log.emit("--- Чтение реестра Uninstall ---")
            worker = UninstallScanWorker(self)
            worker.log.connect(self.apps_log)
            worker.finished_with_apps.connect(self._on_apps_loaded)
            self.apps_worker = worker
            worker.start()
        except Exception as exc:
            self.apps_state.emit(False)
            self.apps_log.emit(f"Ошибка сканирования программ: {exc}")

    def _on_apps_loaded(self, apps) -> None:
        self.apps_state.emit(False)
        self._apps_loaded_once = True
        self.apps_ready.emit(apps)

    def uninstall_app(self, app: InstalledApp) -> None:
        remove_registry = not app.has_uninstaller
        if remove_registry:
            accepted = QMessageBox.question(
                self, "Нет деинсталлятора",
                f"У «{app.name}» нет команды удаления.\nУдалить запись реестра "
                "с резервной копией?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
        else:
            accepted = QMessageBox.question(
                self, S.CONFIRM_CLEAN_TITLE, f"Запустить деинсталлятор «{app.name}»?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
        if accepted != QMessageBox.Yes:
            return
        try:
            self.apps_state.emit(True)
            worker = UninstallWorker(
                self.uninstaller, app, remove_registry=remove_registry, parent=self
            )
            worker.log.connect(self.apps_log)
            worker.finished_with_result.connect(
                lambda ok, msg: self._on_uninstall_done(app, ok, msg)
            )
            self.uninstall_worker = worker
            worker.start()
        except Exception as exc:
            self.apps_state.emit(False)
            self.apps_log.emit(f"Ошибка удаления: {exc}")

    def _on_uninstall_done(self, app: InstalledApp, ok: bool, msg: str) -> None:
        self.apps_state.emit(False)
        self.apps_log.emit(f"{'OK' if ok else 'ОШИБКА'}: {app.name} — {msg}")
        if ok and QMessageBox.question(
            self, "Очистка остатков", "Просканировать остатки программы?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        ) == QMessageBox.Yes:
            self.find_leftovers(app)
        self.scan_apps()

    def find_leftovers(self, app: InstalledApp) -> None:
        try:
            self.apps_state.emit(True)
            self.apps_log.emit(f"--- Поиск остатков: {app.name} ---")
            worker = LeftoverScanWorker(self.uninstaller, app, self)
            worker.log.connect(self.apps_log)
            worker.finished_with_leftovers.connect(
                lambda dirs, registry: self._on_leftovers_found(app, dirs, registry)
            )
            self.leftover_worker = worker
            worker.start()
        except Exception as exc:
            self.apps_state.emit(False)
            self.apps_log.emit(f"Ошибка поиска остатков: {exc}")

    def _on_leftovers_found(self, app, dirs, registry) -> None:
        self.apps_state.emit(False)
        self.leftovers_ready.emit(app, dirs, registry)

    def cleanup_leftovers(self, dirs, registry) -> None:
        try:
            self.apps_state.emit(True)
            worker = CleanupWorker(self.uninstaller, dirs, registry, self)
            worker.log.connect(self.apps_log)
            worker.finished_with_results.connect(self._on_cleanup_done)
            self.cleanup_worker = worker
            worker.start()
        except Exception as exc:
            self.apps_state.emit(False)
            self.apps_log.emit(f"Ошибка очистки остатков: {exc}")

    def _on_cleanup_done(self, results) -> None:
        self.apps_state.emit(False)
        ok = sum(1 for item in results if item[1])
        self.apps_log.emit(f"Удалено остатков: {ok} из {len(results)}")
        self.notify(S.APP_BRAND, f"Очистка остатков: {ok}/{len(results)}")

    # ---------------------------------------------------------------- закрытие
    def closeEvent(self, event: QCloseEvent) -> None:
        workers = [
            self.clean_worker, self.service_worker, self.plan_worker,
            self.apply_worker, self.control_worker, self.apps_worker,
            self.uninstall_worker, self.leftover_worker, self.cleanup_worker,
            self.startup_worker, self.startup_action_worker,
        ]
        for worker in workers:
            try:
                if worker and worker.isRunning():
                    worker.wait(1500)
            except Exception:
                pass
        _save_settings(self.settings)
        event.accept()
