"""
ui/autostart_screen.py — вкладка «Автозагрузка» (полный рефакторинг).

Без графика: QTreeView + кастомная модель QStandardItemModel с иконками,
путями, аргументами, источником и статусом. Управление: Отключить / Включить /
Удалить запись / Удалить битую ссылку. Путь кликабелен — открывает папку.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QFileInfo, QThread, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QFileIconProvider, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QTreeView, QVBoxLayout, QWidget,
)

from startup import (
    SOURCE_FOLDER, SOURCE_LABELS, SOURCE_REG_HKCU, SOURCE_REG_HKLM,
    SOURCE_TASK, StartupEntry, collect_startup_entries,
)
from . import strings as S
from .theme import icon
from .widgets import AnimatedButton

BROKEN_COLOR = QColor("#FF5C7A")
DISABLED_COLOR = QColor("#8A96B2")
LINK_COLOR = QColor("#4A7DFF")
TEXT_COLOR = QColor("#F2F5FF")


class StartupModel(QStandardItemModel):
    """Кастомная модель записей автозагрузки."""

    COLUMNS = [S.COL_NAME, S.COL_PATH, S.COL_ARGS, S.COL_SOURCE, S.COL_STATUS]

    def __init__(self, parent=None):
        super().__init__(0, len(self.COLUMNS), parent)
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self._provider = QFileIconProvider()

    def set_entries(self, entries: list[StartupEntry]) -> None:
        self.removeRows(0, self.rowCount())
        for entry in entries:
            row = []
            status = S.STATUS_DISABLED if not entry.enabled else S.STATUS_ENABLED
            if entry.broken:
                status = S.STATUS_ENABLED + S.BROKEN_MARK
            name_item = QStandardItem(entry.name)
            path_item = QStandardItem(entry.path or entry.command)
            args_item = QStandardItem(entry.arguments or "—")
            source_item = QStandardItem(entry.source_label or SOURCE_LABELS.get(
                entry.source, "—"))
            status_item = QStandardItem(status)
            row = [name_item, path_item, args_item, source_item, status_item]

            try:
                target = entry.path or entry.command.strip('"')
                name_item.setIcon(self._provider.icon(QFileInfo(target)))
            except Exception:
                pass

            brush = None
            if entry.broken:
                brush = QBrush(BROKEN_COLOR)
            elif not entry.enabled:
                brush = QBrush(DISABLED_COLOR)
            if brush is not None:
                for item in row:
                    item.setForeground(brush)
            else:
                path_font = QFont("Segoe UI", 10)
                path_font.setUnderline(True)
                path_item.setFont(path_font)
                path_item.setForeground(QBrush(LINK_COLOR))

            for item in row:
                item.setEditable(False)
            name_item.setData(entry, Qt.UserRole)
            self.appendRow(row)

    def entry(self, index) -> StartupEntry | None:
        if not index.isValid():
            return None
        item = self.item(index.row(), 0)
        return item.data(Qt.UserRole) if item else None

    def set_entry_enabled(self, entry: StartupEntry, enabled: bool) -> None:
        """Меняет статус конкретной записи через setForeground."""
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            current = item.data(Qt.UserRole) if item else None
            if current is None or current.identity() != entry.identity():
                continue
            current.enabled = enabled
            self.item(row, 4).setText(
                S.STATUS_ENABLED if enabled else S.STATUS_DISABLED
            )
            brush = QBrush(DISABLED_COLOR if not enabled else TEXT_COLOR)
            for column in range(self.columnCount()):
                self.item(row, column).setForeground(brush)
            item.setData(current, Qt.UserRole)
            break


class StartupScanWorker(QThread):
    log = Signal(str)
    finished_with_entries = Signal(object)

    def run(self) -> None:
        try:
            entries = collect_startup_entries()
            self.log.emit(f"Найдено записей автозагрузки: {len(entries)}")
            self.finished_with_entries.emit(entries)
        except Exception as exc:
            self.log.emit(S.STARTUP_SCAN_ERROR.format(error=exc))
            self.finished_with_entries.emit([])


class StartupActionWorker(QThread):
    """Выполняет Отключить / Включить / Удалить в фоне."""

    finished_with_result = Signal(object, bool, str)

    def __init__(self, entry: StartupEntry, action: str, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.action = action

    def run(self) -> None:
        from startup import delete_entry, disable_entry, enable_entry
        actions = {
            "disable": disable_entry,
            "enable": enable_entry,
            "delete": delete_entry,
            "delete_broken": delete_entry,
        }
        try:
            ok, msg = actions[self.action](self.entry)
        except Exception as exc:
            ok, msg = False, str(exc)
        self.finished_with_result.emit(self.entry, ok, msg)


class AutostartScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.worker = None
        self._last_action = "disable"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel(S.STARTUP_TITLE)
        title.setObjectName("heroTitle")
        subtitle = QLabel(S.STARTUP_SUBTITLE)
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        buttons = QHBoxLayout()
        self.disable_btn = AnimatedButton(S.BTN_DISABLE)
        self.enable_btn = AnimatedButton(S.BTN_ENABLE)
        self.delete_btn = AnimatedButton(S.BTN_DELETE)
        self.delete_broken_btn = AnimatedButton(S.BTN_DELETE_BROKEN)
        self.delete_broken_btn.setObjectName("accent")
        self.refresh_btn = AnimatedButton(S.BTN_REFRESH)
        for button in (self.disable_btn, self.enable_btn, self.delete_btn,
                       self.delete_broken_btn, self.refresh_btn):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.disable_btn.clicked.connect(lambda: self._act("disable"))
        self.enable_btn.clicked.connect(lambda: self._act("enable"))
        self.delete_btn.clicked.connect(lambda: self._act("delete"))
        self.delete_broken_btn.clicked.connect(lambda: self._act("delete_broken"))
        self.refresh_btn.clicked.connect(self.refresh)

        self.model = StartupModel(self)
        self.view = QTreeView()
        self.view.setModel(self.model)
        self.view.setRootIsDecorated(False)
        self.view.setAlternatingRowColors(True)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setUniformRowHeights(True)
        header = self.view.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(2, 230)
        header.resizeSection(3, 150)
        header.resizeSection(4, 130)
        self.view.clicked.connect(self._on_clicked)
        layout.addWidget(self.view, stretch=1)

        self.log = QLabel("")
        self.log.setObjectName("subtitle")
        self.log.setMinimumHeight(24)
        self.log.setWordWrap(True)
        layout.addWidget(self.log)

        self.main.startup_ready.connect(self._on_entries)
        self.main.startup_action_done.connect(self._on_action_done)
        self.main.startup_log.connect(self._append_log)

    # ---------------------------------------------------------------- helpers
    def _append_log(self, text: str) -> None:
        try:
            self.log.setText(text)
        except Exception:
            pass

    def _selected_entry(self) -> StartupEntry | None:
        return self.model.entry(self.view.currentIndex())

    def refresh(self) -> None:
        self.main.scan_startup()

    def _on_entries(self, entries) -> None:
        self.model.set_entries(entries)

    def _on_clicked(self, index) -> None:
        entry = self.model.entry(index)
        if entry is None:
            return
        if index.column() == 1:
            self._open_folder(entry)
        else:
            self.view.setCurrentIndex(index)

    @staticmethod
    def _open_folder(entry: StartupEntry) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        target = entry.path or entry.command.strip('"')
        folder = Path(os.path.expandvars(target)).parent
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ---------------------------------------------------------------- actions
    def _act(self, action: str) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(self, S.STARTUP_TITLE, S.STARTUP_SELECT)
            return
        templates = {
            "disable": S.STARTUP_CONFIRM_DISABLE,
            "enable": S.STARTUP_CONFIRM_ENABLE,
            "delete": S.STARTUP_CONFIRM_DELETE,
            "delete_broken": S.STARTUP_CONFIRM_DELETE,
        }
        if QMessageBox.question(
            self, S.STARTUP_CONFIRM_TITLE,
            templates[action].format(name=entry.name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        # отключение требует резервной копии — MainWindow спросит об этом
        if not self.main.confirm_backup("startup:" + action):
            return
        self._last_action = action
        self.main.apply_startup_action(entry, action)

    def _on_action_done(self, entry: StartupEntry, ok: bool, msg: str) -> None:
        action_label = {
            "disable": S.ACTION_DISABLED,
            "enable": S.ACTION_ENABLED,
            "delete": S.ACTION_DELETED,
            "delete_broken": S.ACTION_BROKEN_DELETED,
        }
        self._append_log(S.STARTUP_DONE.format(
            action=action_label.get(self._last_action, S.ACTION_DELETED),
            name=entry.name, msg=msg,
        ))
        if ok:
            self.refresh()
