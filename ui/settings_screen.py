"""
ui/settings_screen.py — вкладка «Настройки».

Блок «Восстановление»: список резервных копий (дата, время, размер)
и кнопка «Восстановить».
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from backup import list_backups
from . import strings as S
from .theme import add_shadow
from .widgets import AnimatedButton


class SettingsScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel(S.SETTINGS_TITLE)
        title.setObjectName("heroTitle")
        subtitle = QLabel(S.SETTINGS_SUBTITLE)
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        section = QLabel(S.BACKUP_RESTORE_BLOCK.upper())
        section.setObjectName("sectionTitle")
        card_layout.addWidget(section)
        hint = QLabel(S.BACKUP_LIST_HINT)
        hint.setObjectName("subtitle")
        card_layout.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([S.COL_DATE, S.COL_TIME, S.COL_SIZE])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        card_layout.addWidget(self.tree, stretch=1)

        buttons = QHBoxLayout()
        self.restore_btn = AnimatedButton(S.BTN_RESTORE)
        self.restore_btn.setObjectName("accent")
        self.refresh_btn = AnimatedButton(S.BTN_REFRESH_BACKUPS)
        self.restore_btn.clicked.connect(self._restore)
        self.refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.restore_btn)
        buttons.addWidget(self.refresh_btn)
        buttons.addStretch()
        card_layout.addLayout(buttons)
        layout.addWidget(card, stretch=1)

        self.status = QLabel("")
        self.status.setObjectName("subtitle")
        self.status.setMinimumHeight(24)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.main.backup_status.connect(self._set_status)
        self.refresh()

    def _set_status(self, text: str) -> None:
        try:
            self.status.setText(text)
        except Exception:
            pass

    def refresh(self) -> None:
        self.tree.clear()
        self._backups = list_backups()
        for item in self._backups:
            row = QTreeWidgetItem([
                item["date"], item["time"], f"{item['size'] / 1024:.1f} КБ"
            ])
            row.setData(0, Qt.UserRole, item["path"])
            row.setToolTip(0, item["name"])
            self.tree.addTopLevelItem(row)
        if not self._backups:
            self.status.setText(S.NO_BACKUPS)
        else:
            self.status.setText("")

    def _restore(self) -> None:
        current = self.tree.currentItem()
        if current is None:
            QMessageBox.information(self, S.SETTINGS_TITLE, S.NO_BACKUPS)
            return
        path = Path(current.data(0, Qt.UserRole))
        name = current.toolTip(0) or path.name
        if QMessageBox.question(
            self, S.BACKUP_TITLE,
            S.BACKUP_CONFIRM_RESTORE.format(name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.main.restore_backup(path)
