"""
ui/programs_screen.py — экран «Программы».

QListView + QStandardItemModel, живой поиск, поиск .ico файлов,
скрытая кнопка «...» с fadeIn при наведении (реализована в ProgramListView).
"""
from __future__ import annotations

import glob
import os
import re
from pathlib import Path

try:
    import winreg
except Exception:  # pragma: no cover
    winreg = None  # type: ignore

from PySide6.QtCore import QModelIndex, Qt, QUrl
from PySide6.QtGui import (
    QDesktopServices, QIcon, QStandardItem, QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMenu, QMessageBox, QProgressBar, QTextEdit, QVBoxLayout, QWidget,
)

from . import strings as S
from .theme import icon as theme_icon
from .widgets import AnimatedButton, ProgramListView

from uninstaller import InstalledApp
from cache import human_size


def find_app_icon(app: InstalledApp) -> QIcon:
    """Ищет .ico в папке программы; иначе иконка «коробка»."""
    candidates: list[Path] = []
    try:
        location = (app.install_location or "").strip().strip('"')
        if location:
            from PySide6.QtGui import QFileIconProvider
            target = Path(os.path.expandvars(location))
            if target.is_file() and target.suffix.lower() == ".exe":
                file_icon = QFileIconProvider().icon(target)
                if not file_icon.isNull():
                    return file_icon
            candidates.append(target)
            # реестр иногда хранит путь к exe, а не к папке
            if candidates[-1].suffix.lower() == ".exe":
                candidates[-1] = candidates[-1].parent
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ):
            if base:
                candidates.append(Path(base) / app.name[:40])
    except Exception:
        pass

    for folder in candidates:
        try:
            if not folder or not folder.exists():
                continue
            files = glob.glob(str(folder / "*.ico")) + glob.glob(str(folder / "**" / "*.ico"))
            for path in files[:5]:
                result = QIcon(path)
                if not result.isNull():
                    return result
        except Exception:
            continue
    return theme_icon("fa5s.box", color="#0067c0")


def _exe_from(value: str) -> str:
    """Достаёт путь к exe/dll/ico из строки вида '"C:\\Program\\app.exe",0'."""
    pattern = r'\.(?:exe|dll|ico)'
    match = re.search(r'"([^"]+' + pattern + r')"', value or "", re.IGNORECASE)
    if not match:
        match = re.search(r'([A-Za-z]:\\[^\s",]+' + pattern + r')',
                          value or "", re.IGNORECASE)
    return os.path.expandvars(match.group(1)) if match else ""


def app_path(app: InstalledApp) -> str:
    """Путь программы: InstallLocation → UninstallString → DisplayIcon из реестра."""
    location = (app.install_location or "").strip().strip('"')
    if location:
        return os.path.expandvars(location)

    command = (app.quiet_uninstall_string or app.uninstall_string or "").strip()
    found = _exe_from(command)
    if found:
        return found

    # Многие записи не имеют InstallLocation, но содержат DisplayIcon
    if winreg is not None and app.key_name:
        try:
            root = (winreg.HKEY_LOCAL_MACHINE if app.root == "HKLM"
                    else winreg.HKEY_CURRENT_USER)
            view = winreg.KEY_WOW64_32KEY if app.view == "32-bit" else 0
            reg_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{app.key_name}"
            with winreg.OpenKey(root, reg_path, 0, winreg.KEY_READ | view) as key:
                try:
                    icon = str(winreg.QueryValueEx(key, "DisplayIcon")[0])
                except OSError:
                    icon = ""
            found = _exe_from(icon)
            if found:
                return found
        except Exception:
            pass
    return "—"


def extra_tool_apps() -> list[InstalledApp]:
    """Служебные утилиты, которые должны быть всегда видны в списке."""
    tools = [
        ("Display Driver Uninstaller (DDU)",
         r"C:\Program Files\Display Driver Uninstaller"),
        ("NVCleanstall 1.19.0",
         r"C:\Users\ASUS\Downloads\NVCleanstall_1.19.0.exe"),
    ]
    result: list[InstalledApp] = []
    for name, path in tools:
        if not os.path.exists(path):
            continue
        result.append(InstalledApp(
            name=name,
            version="",
            publisher=S.TOOL_PUBLISHER,
            install_location=path,
            uninstall_string="",
            quiet_uninstall_string="",
            key_name="",
            root="HKCU",
            view="64-bit",
        ))
    return result


class ProgramsScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self._apps: list[InstalledApp] = []
        self._tool_names: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel(S.PROGRAMS_TITLE)
        title.setObjectName("heroTitle")
        subtitle = QLabel(S.PROGRAMS_SUBTITLE)
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(S.SEARCH_PLACEHOLDER)
        self.search.textChanged.connect(self._filter)
        search_row.addWidget(self.search)
        self.refresh_btn = AnimatedButton(S.BTN_REFRESH)
        self.refresh_btn.clicked.connect(self.main.scan_apps)
        search_row.addWidget(self.refresh_btn)
        layout.addLayout(search_row)

        self.model = QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels([
            S.COL_NAME if hasattr(S, "COL_NAME") else "Название",
            "Версия", "Издатель", "Размер", S.COL_PATH,
        ])
        self.view = ProgramListView()
        self.view.setModel(self.model)
        self.view.setRootIsDecorated(False)
        self.view.setAlternatingRowColors(True)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setUniformRowHeights(True)

        header = self.view.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        self.view.menu_requested.connect(self._show_row_menu)
        layout.addWidget(self.view, stretch=1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        self.run_btn = AnimatedButton(S.BTN_RUN_TOOL)
        self.run_btn.setObjectName("accent")
        self.run_btn.clicked.connect(self._run_selected_tool)
        self.uninstall_btn = AnimatedButton(S.BTN_UNINSTALL)
        self.uninstall_btn.clicked.connect(self._uninstall_selected)
        self.leftovers_btn = AnimatedButton(S.BTN_CLEAN_LEFTOVERS)
        self.leftovers_btn.clicked.connect(self._cleanup_selected)
        buttons.addWidget(self.run_btn)
        buttons.addWidget(self.uninstall_btn)
        buttons.addWidget(self.leftovers_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        layout.addWidget(self.log)

        try:
            self.main.apps_log.connect(self.log.append)
            self.main.apps_progress.connect(self.progress.setValue)
            self.main.apps_ready.connect(self._set_apps)
            self.main.apps_state.connect(self._set_busy)
            self.main.leftovers_ready.connect(self._show_leftovers)
        except Exception:
            pass

    def _set_busy(self, busy: bool) -> None:
        self.refresh_btn.setEnabled(not busy)
        self.uninstall_btn.setEnabled(not busy)
        self.leftovers_btn.setEnabled(not busy)

    def _set_apps(self, apps: list[InstalledApp]) -> None:
        tools = extra_tool_apps()
        self._tool_names = {tool.name for tool in tools}
        self._apps = apps + tools
        self._filter()

    def _filter(self) -> None:
        query = self.search.text().strip().lower()
        self.model.removeRows(0, self.model.rowCount())
        for app in self._apps:
            path = app_path(app)
            haystack = f"{app.name} {app.publisher} {path}".lower()
            if query and query not in haystack:
                continue
            name_item = QStandardItem(find_app_icon(app), app.name)
            name_item.setData(app, Qt.UserRole)
            path_item = QStandardItem(path)
            path_item.setToolTip(path)
            self.model.appendRow([
                name_item,
                QStandardItem(app.version),
                QStandardItem(app.publisher),
                QStandardItem(human_size(app.estimated_size) if app.estimated_size else "—"),
                path_item,
            ])

    def _app_at(self, index: QModelIndex) -> InstalledApp | None:
        if not index.isValid():
            return None
        # данные хранятся в 0-й колонке, клик может быть в любой
        item = self.model.item(index.row(), 0)
        return item.data(Qt.UserRole) if item else None

    def _selected_app(self) -> InstalledApp | None:
        return self._app_at(self.view.currentIndex())

    def _is_tool(self, app: InstalledApp | None) -> bool:
        return bool(app and app.name in self._tool_names)

    def _run_tool(self, app: InstalledApp) -> None:
        path = app_path(app)
        if path == "—":
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.expandvars(path)))
        except Exception:
            pass

    def _run_selected_tool(self) -> None:
        app = self._selected_app()
        if self._is_tool(app):
            self._run_tool(app)

    def _show_row_menu(self, index: QModelIndex) -> None:
        app = self._app_at(index)
        if not app:
            return
        menu = QMenu(self)
        act_open = menu.addAction(theme_icon("fa5s.folder-open", color="#0067c0"),
                                  S.BTN_OPEN_FOLDER)
        if self._is_tool(app):
            act_run = menu.addAction(theme_icon("fa5s.play", color="#4ADE80"),
                                     S.BTN_RUN_TOOL)
        else:
            act_run = None
            act_uninstall = menu.addAction(theme_icon("fa.trash", color="#d13438"),
                                           S.BTN_UNINSTALL)
            act_leftovers = menu.addAction(theme_icon("fa.star", color="#0067c0"),
                                           S.MENU_FIND_LEFTOVERS)
        action = menu.exec(self.view.mapToGlobal(self.view.visualRect(index).topLeft()))
        if action == act_open:
            self._open_folder(app)
        elif act_run is not None and action == act_run:
            self._run_tool(app)
        elif not self._is_tool(app):
            if action == act_uninstall:
                self.main.uninstall_app(app)
            elif action == act_leftovers:
                self.main.find_leftovers(app)

    @staticmethod
    def _open_folder(app: InstalledApp) -> None:
        path = app_path(app)
        if path == "—":
            return
        folder = Path(os.path.expandvars(path))
        if folder.suffix:
            folder = folder.parent
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _uninstall_selected(self) -> None:
        app = self._selected_app()
        if app and not self._is_tool(app):
            self.main.uninstall_app(app)

    def _cleanup_selected(self) -> None:
        app = self._selected_app()
        if app and not self._is_tool(app):
            self.main.find_leftovers(app)

    def _show_leftovers(self, app: InstalledApp, dirs: list, registry: list) -> None:
        if not dirs and not registry:
            QMessageBox.information(self, S.APP_BRAND, S.NO_LEFTOVERS)
            return
        lines = [f"Папки ({len(dirs)}):"] + [f"  • {path}" for path in dirs[:20]]
        lines += [f"Записи реестра ({len(registry)}):"] + [f"  • {key}" for key in registry[:20]]
        dialog = QMessageBox(self)
        dialog.setWindowTitle(S.LEFTOVERS_TITLE)
        dialog.setText(S.LEFTOVERS_TEXT.format(lines="\n".join(lines[:45])))
        dialog.setInformativeText("Реестр будет экспортирован в .reg. Продолжить?")
        dialog.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        if dialog.exec() == QMessageBox.Ok:
            self.main.cleanup_leftovers(dirs, registry)
