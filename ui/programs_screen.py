"""
ui/programs_screen.py — экран «Программы».

QListView + QStandardItemModel, живой поиск, поиск .ico файлов,
скрытая кнопка «...» с fadeIn при наведении (реализована в ProgramListView).
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar,
    QTextEdit, QVBoxLayout, QWidget,
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
            candidates.append(Path(location))
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


class ProgramsScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self._apps: list[InstalledApp] = []

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
        self.model.setHorizontalHeaderLabels(["Название", "Версия", "Издатель", "Размер"])
        self.view = ProgramListView()
        self.view.setModel(self.model)
        self.view.setAlternatingRowColors(True)
        self.view.setUniformItemSizes(True)
        self.view.menu_requested.connect(self._show_row_menu)
        layout.addWidget(self.view, stretch=1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        self.uninstall_btn = AnimatedButton(S.BTN_UNINSTALL)
        self.uninstall_btn.setObjectName("accent")
        self.uninstall_btn.clicked.connect(self._uninstall_selected)
        self.leftovers_btn = AnimatedButton(S.BTN_CLEAN_LEFTOVERS)
        self.leftovers_btn.clicked.connect(self._cleanup_selected)
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
        self._apps = apps
        self._filter()

    def _filter(self) -> None:
        query = self.search.text().strip().lower()
        self.model.removeRows(0, self.model.rowCount())
        for app in self._apps:
            if query and query not in app.name.lower() and query not in app.publisher.lower():
                continue
            name_item = QStandardItem(find_app_icon(app), app.name)
            name_item.setData(app, Qt.UserRole)
            self.model.appendRow([
                name_item,
                QStandardItem(app.version),
                QStandardItem(app.publisher),
                QStandardItem(human_size(app.estimated_size) if app.estimated_size else "—"),
            ])

    def _app_at(self, index: QModelIndex) -> InstalledApp | None:
        if not index.isValid():
            return None
        item = self.model.item(index.row(), 0)
        return item.data(Qt.UserRole) if item else None

    def _selected_app(self) -> InstalledApp | None:
        return self._app_at(self.view.currentIndex())

    def _show_row_menu(self, index: QModelIndex) -> None:
        app = self._app_at(index)
        if not app:
            return
        menu = QMenu(self)
        act_uninstall = menu.addAction(theme_icon("fa.trash", color="#d13438"), S.BTN_UNINSTALL)
        act_leftovers = menu.addAction(theme_icon("fa.star", color="#0067c0"), S.MENU_FIND_LEFTOVERS)
        action = menu.exec(self.view.mapToGlobal(self.view.visualRect(index).topLeft()))
        if action == act_uninstall:
            self.main.uninstall_app(app)
        elif action == act_leftovers:
            self.main.find_leftovers(app)

    def _uninstall_selected(self) -> None:
        app = self._selected_app()
        if app:
            self.main.uninstall_app(app)

    def _cleanup_selected(self) -> None:
        app = self._selected_app()
        if app:
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
