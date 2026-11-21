"""
ui/theme.py — тема WinBoost Pro в стиле BoosterX.

Официальная палитра бренда: глубокий тёмно-синий фон, ярко-синий акцент
с фиолетовым градиентом, жирный Montserrat, мягкие скруглённые карточки.
Все эффекты и qtawesome защищены try-except.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QPen, QPixmap, QPainter
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QGraphicsDropShadowEffect,
    QLabel, QLineEdit, QListView, QPushButton, QStyle, QTableWidget,
    QTextEdit, QTreeView, QWidget,
)

try:
    import qtawesome as qta  # type: ignore
except Exception:
    qta = None  # type: ignore

# Акценты бренда
ACCENT_BLUE = "#4A7DFF"
ACCENT_VIOLET = "#8B5CF6"
ACCENT_BLUE_LIGHT = "#3B66E0"

# Современные версии qtawesome больше не принимают префикс "fa" (Font Awesome 4),
# поэтому старые имена прозрачно переводим в fa5s.
_ICON_ALIASES = {
    "fa.home": "fa5s.home",
    "fa.paint_brush": "fa5s.paint-brush",
    "fa.gear": "fa5s.cog",
    "fa.trash": "fa5s.trash",
    "fa.star": "fa5s.star",
    "fa.sun": "fa5s.sun",
    "fa.moon": "fa5s.moon",
    "fa.ellipsis-h": "fa5s.ellipsis-h",
    "fa.refresh": "fa5s.sync",
    "fa.undo": "fa5s.undo",
    "fa.plus": "fa5s.plus",
    "fa.sliders-h": "fa5s.sliders-h",
    "fa.tools": "fa5s.tools",
}

_FALLBACK_ICONS = {
    "fa.home": QStyle.SP_ComputerIcon,
    "fa.paint_brush": QStyle.SP_DesktopIcon,
    "fa.gear": QStyle.SP_FileDialogDetailedView,
    "fa.trash": QStyle.SP_TrashIcon,
    "fa.star": QStyle.SP_FileDialogListView,
    "fa.sun": QStyle.SP_BrowserReload,
    "fa.moon": QStyle.SP_BrowserReload,
    "fa5s.box": QStyle.SP_FileIcon,
    "fa.ellipsis-h": QStyle.SP_ToolBarHorizontalExtensionButton,
    "fa.plus": QStyle.SP_FileDialogNewFolder,
    "fa.refresh": QStyle.SP_BrowserReload,
    "fa.undo": QStyle.SP_ArrowBack,
}


def icon(name: str, color: str | None = None, scale: float = 1.0) -> QIcon:
    """Иконка qtawesome или запасная иконка Qt."""
    if qta is not None:
        try:
            kwargs = {"scale": scale}
            if color:
                kwargs["color"] = color
            qta_name = _ICON_ALIASES.get(name, name)
            return qta.icon(qta_name, **kwargs)  # type: ignore[arg-type]
        except Exception:
            pass
    try:
        app = QApplication.instance()
        if app:
            return app.style().standardIcon(_FALLBACK_ICONS.get(name, QStyle.SP_FileIcon))
    except Exception:
        pass
    return QIcon()


def add_shadow(widget, blur: int = 15, dx: int = 0, dy: int = 3,
               color: str = "#000000", alpha: int = 90) -> None:
    """QGraphicsDropShadowEffect для карточек: размытие 15, смещение (0, 3)."""
    try:
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur)
        effect.setOffset(dx, dy)
        base = QColor(color)
        effect.setColor(QColor(base.red(), base.green(), base.blue(), alpha))
        widget.setGraphicsEffect(effect)
    except Exception:
        pass


def make_palette(theme: str) -> QPalette:
    """Полная пересборка QPalette под тёмную/светлую тему бренда."""
    palette = QPalette()
    dark = theme == "dark"
    if dark:
        window = QColor("#0B0E14")
        base = QColor("#121826")
        alt = QColor("#161D2E")
        text = QColor("#F2F5FF")
        disabled = QColor("#66708A")
    else:
        window = QColor("#F3F6FC")
        base = QColor("#FFFFFF")
        alt = QColor("#EAF0FB")
        text = QColor("#121826")
        disabled = QColor("#9AA3B5")

    for role in (
        QPalette.Window, QPalette.Base, QPalette.AlternateBase, QPalette.Button,
        QPalette.ButtonText, QPalette.Text, QPalette.BrightText, QPalette.Highlight,
        QPalette.HighlightedText, QPalette.ToolTipBase, QPalette.ToolTipText,
        QPalette.Link,
    ):
        palette.setColor(role, text)
    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, alt)
    palette.setColor(QPalette.Button, base)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, QColor("#FFFFFF") if dark else QColor("#000000"))
    palette.setColor(QPalette.Highlight, QColor(ACCENT_BLUE))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.Disabled, QPalette.Text, disabled)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled)
    palette.setColor(QPalette.ToolTipBase, base)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Link, QColor(ACCENT_BLUE))
    return palette


def style_sheet(theme: str) -> str:
    return _STYLE_DARK if theme == "dark" else _STYLE_LIGHT


def apply_theme(app: QApplication | None, theme: str) -> None:
    if not app:
        return
    try:
        app.setPalette(make_palette(theme))
    except Exception:
        pass
    try:
        app.setStyleSheet(style_sheet(theme))
    except Exception:
        pass


def _base_style(dark: bool) -> str:
    if dark:
        c = dict(
            bg="#0B0E14", sidebar="#0D1220", topbar="#0E1424",
            card1="#171E2F", card2="#111726", border="#26314B",
            text="#F2F5FF", sub="#8A96B2", accent=ACCENT_BLUE,
            violet=ACCENT_VIOLET, hover="#1C2540", field="#101624",
            danger="#FF5C7A", ok="#4ADE80", shadow="#000000",
        )
        hero = ("qradialgradient(cx:0.85, cy:0.05, radius:1.3, fx:0.85, fy:0.05, "
                "stop:0 #1C2F63, stop:0.45 #141C36, stop:1 #111726)")
    else:
        c = dict(
            bg="#F3F6FC", sidebar="#FFFFFF", topbar="#FFFFFF",
            card1="#FFFFFF", card2="#F7F9FE", border="#DAE2F2",
            text="#121826", sub="#667085", accent=ACCENT_BLUE_LIGHT,
            violet=ACCENT_VIOLET, hover="#EEF3FD", field="#FFFFFF",
            danger="#E5484D", ok="#0E9F6E", shadow="#9AA6C0",
        )
        hero = ("qradialgradient(cx:0.85, cy:0.05, radius:1.3, fx:0.85, fy:0.05, "
                "stop:0 #DCE8FF, stop:0.5 #F1F5FF, stop:1 #FFFFFF)")

    # Montserrat используется брендом, но может отсутствовать в системе —
    # поэтому basic-шрифт Segoe UI даёт гарантированно корректный рендеринг.
    font = "'Segoe UI Variable', 'Segoe UI', sans-serif"
    return f"""
    QWidget {{ background: {c['bg']}; color: {c['text']};
               font-family: {font}; font-size: 10pt; }}
    QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
    QMainWindow {{ background: {c['bg']}; }}
    QFrame#card {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                     stop:0 {c['card1']}, stop:1 {c['card2']});
                   border: 1px solid {c['border']}; border-radius: 16px; }}
    QFrame#hero {{ background: {hero}; border: 1px solid {c['border']};
                   border-radius: 22px; }}
    QFrame#sidebar {{ background: {c['sidebar']};
                      border-right: 1px solid {c['border']}; }}
    QFrame#topbar {{ background: {c['topbar']};
                     border-bottom: 1px solid {c['border']}; }}
    QLabel#subtitle {{ color: {c['sub']}; }}
    QLabel#brand {{ font-size: 18pt; font-weight: 700; }}
    QLabel#logoMark {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 {c['accent']}, stop:1 {c['violet']});
        color: #ffffff; border-radius: 13px; font-size: 15pt; font-weight: 700; }}
    QLabel#heroTitle {{ font-size: 23pt; font-weight: 700; }}
    QLabel#sectionTitle {{ font-size: 11pt; font-weight: 700;
                           color: {c['accent']}; }}
    QLabel#badgeRunning {{ color: {c['ok']}; font-weight: 700; }}
    QLabel#badgeStopped {{ color: {c['sub']}; font-weight: 700; }}

    QPushButton {{ background: {c['hover']}; color: {c['text']};
                   border: 1px solid transparent; border-radius: 12px;
                   padding: 10px 18px; font-weight: 700; }}
    QPushButton:hover {{ background: {c['border']}; }}
    QPushButton:disabled {{ background: {c['card2']}; color: {c['sub']}; }}
    QPushButton#accent {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                            stop:0 {c['accent']}, stop:1 {c['violet']});
                          color: #ffffff; border: none; border-radius: 12px; }}
    QPushButton#accent:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                            stop:0 #5E8DFF, stop:1 #9B70FF); }}
    QPushButton#accent:disabled {{ background: {c['border']}; color: {c['sub']}; }}
    QPushButton#quickClean {{ border-radius: 92px; color: #ffffff;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {c['accent']}, stop:1 {c['violet']});
        border: 9px solid {c['card2']}; font-size: 13pt; font-weight: 700; }}
    QPushButton[nav="true"] {{ background: transparent; border: none;
        border-left: 3px solid transparent; border-radius: 10px; color: {c['sub']};
        font-size: 8pt; font-weight: 700; }}
    QPushButton[nav="true"][active="true"] {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {c['accent']}, stop:1 {c['violet']});
        border-left: 3px solid #ffffff; color: #ffffff; }}
    QPushButton[nav="true"]:hover {{ background: {c['hover']}; }}
    QPushButton#iconBtn {{ background: transparent; border: none; padding: 4px; }}
    QPushButton#themeToggle {{ background: {c['card1']};
                               border: 1px solid {c['border']}; border-radius: 23px; }}

    QLineEdit {{ background: {c['field']}; border: 1px solid {c['border']};
                 border-radius: 12px; padding: 9px 14px; color: {c['text']}; }}
    QComboBox {{ background: {c['field']}; border: 1px solid {c['border']};
                 border-radius: 12px; padding: 7px 12px; color: {c['text']}; }}
    QCheckBox {{ color: {c['text']}; spacing: 8px; font-weight: 600; }}
    QCheckBox#toggleSwitch {{ min-height: 30px; }}
    QCheckBox#toggleSwitch::indicator {{ width: 48px; height: 26px;
        border-radius: 13px; background: {c['border']}; border: 1px solid {c['border']}; }}
    QCheckBox#toggleSwitch::indicator:checked {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {c['accent']}, stop:1 {c['violet']});
        border-color: {c['accent']}; }}
    QTextEdit {{ background: {c['field']}; border: 1px solid {c['border']};
                 border-radius: 14px; color: {c['text']}; padding: 10px; }}
    QProgressBar {{ border: 1px solid {c['border']}; border-radius: 9px;
                    text-align: center; background: {c['field']}; min-height: 20px; }}
    QProgressBar::chunk {{ border-radius: 8px;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {c['accent']}, stop:1 {c['violet']}); }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QListView, QListWidget {{ background: {c['field']}; border: 1px solid {c['border']};
                              border-radius: 14px; padding: 4px; }}
    QMenuBar, QMenu {{ background: {c['topbar']}; color: {c['text']}; }}
    QStatusBar {{ background: {c['topbar']}; color: {c['sub']};
                  border-top: 1px solid {c['border']}; }}
    QToolTip {{ background: {c['card1']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 8px; }}
    """


_TEXT_WIDGETS = (
    QLabel, QPushButton, QCheckBox, QLineEdit, QComboBox, QTextEdit,
    QTreeView, QListView, QTableWidget,
)


def apply_text_fonts(root: QWidget | None, family: str = "Segoe UI",
                     point_size: int = 10) -> None:
    """
    Явно задаёт кириллический шрифт всем текстовым виджетам.
    Размер, заданный в QSS (heroTitle, brand и т.д.), сохраняется —
    меняется только семейство шрифта.
    """
    app = QApplication.instance()
    if app:
        try:
            app.setFont(QFont(family, point_size))
        except Exception:
            pass
    if root is None:
        return
    try:
        widgets = [root] + list(root.findChildren(QWidget))
        for widget in widgets:
            if not isinstance(widget, _TEXT_WIDGETS):
                continue
            try:
                font = QFont(widget.font())
                font.setFamily(family)
                if font.pointSize() < 8:
                    font.setPointSize(point_size)
                widget.setFont(font)
                # многострочные QLabel не должны обрезаться
                if isinstance(widget, QLabel) and widget.wordWrap():
                    minimum = widget.minimumHeight()
                    needed = widget.sizeHint().height()
                    if needed > minimum:
                        widget.setMinimumHeight(needed)
            except Exception:
                continue
    except Exception:
        pass


_STYLE_DARK = _base_style(True)
_STYLE_LIGHT = _base_style(False)


def sun_moon_pixmap(dark: bool, size: int = 28) -> QPixmap:
    """Аварийная иконка солнца/луны без qtawesome."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    try:
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        if dark:
            painter.setBrush(QColor("#F2F5FF"))
            painter.drawEllipse(3, 3, size - 6, size - 6)
            painter.setBrush(QColor("#0B0E14"))
            painter.drawEllipse(size - 14, 2, size - 8, size - 8)
        else:
            painter.setBrush(QColor("#4A7DFF"))
            painter.drawEllipse(7, 7, size - 14, size - 14)
            painter.setPen(QPen(QColor("#4A7DFF"), 2))
            for i in range(8):
                angle = i * math.pi / 4
                x1 = size / 2 + math.cos(angle) * (size / 2 - 4)
                y1 = size / 2 + math.sin(angle) * (size / 2 - 4)
                x2 = size / 2 + math.cos(angle) * (size / 2 - 1)
                y2 = size / 2 + math.sin(angle) * (size / 2 - 1)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        painter.end()
    except Exception:
        pass
    return pix
