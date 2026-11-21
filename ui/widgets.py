"""
ui/widgets.py — переиспользуемые визуальные компоненты.

Все эффекты (анимации, тени, qtawesome) обёрнуты в try-except:
отсутствие дополнительных библиотек не ломает запуск приложения.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGraphicsOpacityEffect, QGraphicsPixmapItem,
    QGraphicsRotation, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QSizePolicy,
    QStackedLayout, QTreeView, QVBoxLayout,
)

from . import strings as S
from .theme import add_shadow, icon, sun_moon_pixmap


# ---------------------------------------------------------------- AnimatedButton
class AnimatedButton(QPushButton):
    """Кнопка с «пружинкой» при наведении и плавным появлением."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._base_geometry: QRect | None = None
        self._geometry_animation: QPropertyAnimation | None = None
        self._opacity_effect: QGraphicsOpacityEffect | None = None
        self._opacity_animation: QPropertyAnimation | None = None
        try:
            self._opacity_effect = QGraphicsOpacityEffect(self)
            self._opacity_effect.setOpacity(0.0)
            self.setGraphicsEffect(self._opacity_effect)
            self._opacity_animation = QPropertyAnimation(
                self._opacity_effect, b"opacity", self
            )
            self._opacity_animation.setDuration(420)
            self._opacity_animation.setStartValue(0.0)
            self._opacity_animation.setEndValue(1.0)
            self._opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        except Exception:
            self._opacity_effect = None
            self._opacity_animation = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        try:
            if (self._opacity_animation and self._opacity_effect
                    and self._opacity_effect.opacity() < 0.99):
                self._opacity_animation.start()
        except Exception:
            pass

    def _animate_geometry(self, target: QRect, duration: int = 320) -> None:
        try:
            if self._geometry_animation and self._geometry_animation.state() == \
                    QPropertyAnimation.Running:
                self._geometry_animation.stop()
            anim = QPropertyAnimation(self, b"geometry")
            anim.setDuration(duration)
            anim.setStartValue(self.geometry())
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.OutBack)
            self._geometry_animation = anim
            anim.start()
        except Exception:
            pass

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        try:
            rect = self.geometry()
            self._base_geometry = rect
            target = QRect(rect.x() - 3, rect.y() - 3,
                           rect.width() + 6, rect.height() + 6)
            self._animate_geometry(target)
        except Exception:
            pass

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        try:
            if self._base_geometry is not None:
                self._animate_geometry(self._base_geometry)
        except Exception:
            pass


# ---------------------------------------------------------------- NavButton
class NavButton(AnimatedButton):
    """Кнопка сайдбара: иконка сверху, подпись снизу (не обрезается)."""

    def __init__(self, icon_name: str, label: str, parent=None):
        super().__init__("", parent)
        self.setProperty("nav", True)
        self.setCheckable(True)
        self.setFixedSize(64, 62)
        self.setToolTip(label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 4)
        layout.setSpacing(2)
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.text_label = QLabel()
        try:
            metrics = QFontMetrics(self.text_label.font())
            self.text_label.setText(metrics.elidedText(label, Qt.ElideRight, 58))
        except Exception:
            self.text_label.setText(label)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setFont(QFont("Segoe UI", 6))
        self.text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        self.set_icon(icon_name, "#ffffff")

    def set_icon(self, icon_name: str, color: str | None = None) -> None:
        try:
            ico = icon(icon_name, color=color)
            self.icon_label.setPixmap(ico.pixmap(QSize(22, 22)))
        except Exception:
            pass


# ---------------------------------------------------------------- RotatingThemeButton
class RotatingThemeButton(AnimatedButton):
    """Кнопка темы: иконка вращается на 360° через QGraphicsRotation."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName("themeToggle")
        self.setFixedSize(46, 46)
        self.setToolTip("Сменить тему (Light / Dark)")
        self._dark = False
        self._rotation: QGraphicsRotation | None = None
        self._animation: QPropertyAnimation | None = None
        self._item: QGraphicsPixmapItem | None = None
        try:
            scene = QGraphicsScene(self)
            view = QGraphicsView(scene, self)
            view.setFixedSize(42, 42)
            view.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            view.setStyleSheet("background: transparent; border: none;")
            view.setFrameStyle(0)
            view.move(2, 2)
            view.raise_()
            self._item = QGraphicsPixmapItem()
            scene.addItem(self._item)
            self._rotation = QGraphicsRotation()  # по умолчанию ось Z
            self._item.setTransformations([self._rotation])
            self._animation = QPropertyAnimation(self._rotation, b"angle")
            self._animation.setDuration(720)
            self._animation.setEasingCurve(QEasingCurve.InOutQuad)
            self._animation.setStartValue(0)
            self._animation.setEndValue(360)
        except Exception:
            self._rotation = None
            self._animation = None
            self._item = None
        self.set_icon_for_theme(False)

    def set_icon_for_theme(self, dark: bool) -> None:
        """Меняет вид иконки (солнце / луна)."""
        self._dark = dark
        try:
            if self._item is not None:
                ico = icon("fa.moon" if dark else "fa.sun",
                           color="#e8e8ea" if dark else "#f5a623", scale=1.0)
                pix = ico.pixmap(QSize(28, 28))
                if pix.isNull():
                    pix = sun_moon_pixmap(dark)
                self._item.setPixmap(pix)
        except Exception:
            pass

    def spin(self, target_dark: bool) -> None:
        """Плавно поворачивает иконку и меняет её на середине оборота."""
        try:
            if self._animation and self._rotation:
                self._animation.stop()
                self._rotation.setAngle(0)
                self._animation.start()
                QTimer.singleShot(350, lambda: self.set_icon_for_theme(target_dark))
            else:
                self.set_icon_for_theme(target_dark)
        except Exception:
            self.set_icon_for_theme(target_dark)


# ---------------------------------------------------------------- CircularProgress
class CircularProgress(QFrame):
    """Большой круг с дугой прогресса и процентом в центре."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(196, 196)
        self._value = 0
        self._accent = QColor("#4A7DFF")
        self._track = QColor("#26314B")
        stack = QStackedLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("0%")
        self._label.setAlignment(Qt.AlignCenter)
        font = QFont("Segoe UI", 34, QFont.Bold)
        self._label.setFont(font)
        self._done = QLabel(S.DONE_LABEL)
        self._done.setAlignment(Qt.AlignCenter)
        self._done.setFont(QFont("Segoe UI", 16, QFont.Bold))
        stack.addWidget(self._label)
        stack.addWidget(self._done)
        stack.setCurrentWidget(self._label)

    def set_value(self, value: int) -> None:
        self._value = max(0, min(100, int(value)))
        try:
            self._label.setText(f"{self._value}%")
            self._label.setStyleSheet("background: transparent; border: none;")
            self._done.setStyleSheet("background: transparent; border: none;")
            self.layout().setCurrentWidget(self._done if self._value >= 100 else self._label)
        except Exception:
            pass
        self.update()

    def set_colors(self, accent: str, track: str) -> None:
        self._accent = QColor(accent)
        self._track = QColor(track)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            rect = self.rect().adjusted(14, 14, -14, -14)
            pen = QPen(self._track, 12)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -360 * 16)
            pen = QPen(self._accent, 12)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -int(360 * 16 * self._value / 100))
        except Exception:
            pass


# ---------------------------------------------------------------- QuickCleanWidget
class QuickCleanWidget(QFrame):
    """Круглая кнопка быстрой очистки с круговым прогрессом внутри."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFixedSize(224, 224)
        add_shadow(self, blur=15, dy=3)
        stack = QStackedLayout(self)
        stack.setContentsMargins(12, 12, 12, 12)

        self.button = AnimatedButton(S.QUICK_CLEAN_BTN)
        self.button.setFixedSize(184, 184)
        self.button.setObjectName("quickClean")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.clicked.emit)

        self.progress = CircularProgress()
        stack.addWidget(self.button)
        stack.addWidget(self.progress)
        stack.setCurrentWidget(self.button)

    def set_busy(self, busy: bool) -> None:
        self.layout().setCurrentWidget(self.progress if busy else self.button)
        self.progress.set_value(0)

    def set_value(self, value: int) -> None:
        self.progress.set_value(value)


# ---------------------------------------------------------------- SystemCard
class SystemCard(QFrame):
    """Горизонтальная плашка CPU / RAM / GPU с миганием при >80%."""

    def __init__(self, title: str, accent: str = "#0067c0", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._accent = accent
        self._blink_on = False
        self._danger = "#d13438"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.title_label = QLabel(title)
        self.title_label.setMinimumWidth(52)
        self.title_label.setStyleSheet("font-weight: 600; border: none;")
        self.value_label = QLabel("0%")
        self.value_label.setMinimumWidth(52)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)

        layout.addWidget(self.title_label)
        layout.addWidget(self.bar, stretch=1)
        layout.addWidget(self.value_label)
        add_shadow(self, blur=15, dy=3)

        self._timer = QTimer(self)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._blink)

    def set_value(self, value: float, text: str | None = None) -> None:
        try:
            value = max(0, min(100, int(value)))
            self.bar.setValue(value)
            self.value_label.setText(text if text is not None else f"{value}%")
            if value > 80:
                if not self._timer.isActive():
                    self._timer.start()
            else:
                self._timer.stop()
                self._blink_on = False
                self._apply_style(self._accent)
        except Exception:
            pass

    def _blink(self) -> None:
        self._blink_on = not self._blink_on
        self._apply_style(self._danger if self._blink_on else self._accent)

    def _apply_style(self, color: str) -> None:
        try:
            self.bar.setStyleSheet(
                f"QProgressBar::chunk {{ background: {color}; border-radius: 7px; }}"
            )
            self.value_label.setStyleSheet(f"color: {color}; font-weight: 700; border: none;")
        except Exception:
            pass


# ---------------------------------------------------------------- ServiceCard
class ServiceCard(QFrame):
    """Карточка службы с раскрывающейся анимацией и тремя кнопками."""

    COLLAPSED = 96
    EXPANDED = 200

    def __init__(self, name: str, display_name: str, status: str, start_type: str,
                 callbacks: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumWidth(0)
        self.setMinimumHeight(self.COLLAPSED)
        self.setMaximumHeight(self.COLLAPSED)
        self._collapsed = True
        self._animation: QPropertyAnimation | None = None
        self.callbacks = callbacks or {}
        # Без QGraphicsEffect: у карточек с кнопками он смещает рендер детей.

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(6)

        header = QHBoxLayout()
        metrics = QFontMetrics(QFont("Segoe UI", 10, QFont.Bold))
        short_name = metrics.elidedText(display_name, Qt.ElideRight, 160)
        self.name_label = QLabel(f"<b>{short_name}</b>")
        self.name_label.setToolTip(display_name)
        self.name_label.setMinimumWidth(0)
        self.name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.name_label.setStyleSheet("border: none;")
        self.service_label = QLabel(
            QFontMetrics(QFont("Segoe UI", 9)).elidedText(name, Qt.ElideRight, 105)
        )
        self.service_label.setToolTip(name)
        self.service_label.setStyleSheet("border: none;")
        self.status_label = QLabel(status)
        self.status_label.setObjectName(
            "badgeRunning" if status == "Запущена" else "badgeStopped"
        )
        self.type_label = QLabel(start_type)
        self.type_label.setStyleSheet("border: none;")
        header.addWidget(self.name_label, stretch=1)
        header.addWidget(self.service_label)
        header.addWidget(self.status_label)
        header.addWidget(self.type_label)
        outer.addLayout(header)

        self.controls = QFrame()
        controls_layout = QHBoxLayout(self.controls)
        controls_layout.setContentsMargins(0, 6, 0, 0)
        controls_layout.setSpacing(8)
        self.stop_btn = AnimatedButton(S.BTN_STOP_SERVICE)
        self.start_btn = AnimatedButton(S.BTN_START_SERVICE)
        self.type_btn = AnimatedButton(S.BTN_CHANGE_TYPE)
        self.stop_btn.clicked.connect(lambda: self._invoke("stop"))
        self.start_btn.clicked.connect(lambda: self._invoke("start"))
        self.type_btn.clicked.connect(lambda: self._invoke("type"))
        for btn in (self.stop_btn, self.start_btn, self.type_btn):
            controls_layout.addWidget(btn)
        controls_layout.addStretch()
        self.controls.setHidden(True)
        outer.addWidget(self.controls)

        self.setCursor(Qt.PointingHandCursor)

    def _invoke(self, action: str) -> None:
        callback = self.callbacks.get(action)
        if callable(callback):
            try:
                callback()
            except Exception:
                pass

    def set_state(self, status: str, start_type: str) -> None:
        try:
            self.status_label.setText(status)
            self.status_label.setObjectName(
                "badgeRunning" if status == "Запущена" else "badgeStopped"
            )
            self.type_label.setText(start_type)
            self.style().unpolish(self.status_label)
            self.style().polish(self.status_label)
        except Exception:
            pass

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        try:
            self.toggle_expand()
        except Exception:
            pass

    def toggle_expand(self) -> None:
        """Анимирует maximumHeight и показывает/скрывает кнопки."""
        try:
            if self._animation and self._animation.state() == QPropertyAnimation.Running:
                return
            expanding = self._collapsed
            start = self.maximumHeight()
            end = self.EXPANDED if expanding else self.COLLAPSED
            if expanding:
                self.controls.setHidden(False)
            anim = QPropertyAnimation(self, b"maximumHeight")
            anim.setDuration(340)
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            if not expanding:
                anim.finished.connect(lambda: self.controls.setHidden(True))
            self._animation = anim
            self._collapsed = not expanding
            anim.start()
        except Exception:
            self.controls.setHidden(self._collapsed)


# ---------------------------------------------------------------- ToggleSwitch
class ToggleSwitch(QCheckBox):
    """Кастомный QCheckBox в стиле iOS-переключателя."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("toggleSwitch")
        self.setCursor(Qt.PointingHandCursor)

    def set_state_silent(self, checked: bool) -> None:
        self.blockSignals(True)
        self.setChecked(bool(checked))
        self.blockSignals(False)


# ---------------------------------------------------------------- ProgramListView
class ProgramListView(QTreeView):
    """
    Таблица программ с плавающей кнопкой «...».

    Важно: кнопка — ребёнок viewport(), а не самого QTreeView. События мыши
    и visualRect() тоже работают в координатах viewport. Именно из-за этого
    прежняя реализация с child-of-view не показывала кнопку при наведении.
    """

    menu_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self._current_index = None

        self._menu_button = AnimatedButton("...", self.viewport())
        self._menu_button.setObjectName("iconBtn")
        self._menu_button.setFixedSize(36, 28)
        self._menu_button.setHidden(True)
        self._menu_button.clicked.connect(self._on_menu_clicked)

        try:
            effect = QGraphicsOpacityEffect(self._menu_button)
            effect.setOpacity(0.0)
            self._menu_button.setGraphicsEffect(effect)
            self._fade = QPropertyAnimation(effect, b"opacity", self)
            self._fade.setDuration(220)
            self._fade.setEasingCurve(QEasingCurve.OutCubic)
        except Exception:
            self._fade = None

    # ------------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        try:
            if obj is self.viewport():
                if event.type() in (QEvent.MouseMove, QEvent.Enter):
                    self._update_button(event.position().toPoint())
                elif event.type() == QEvent.Leave:
                    self._fade_out()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _on_menu_clicked(self) -> None:
        if self._current_index is not None:
            try:
                self.menu_requested.emit(self._current_index)
            except Exception:
                pass

    def _update_button(self, pos) -> None:
        index = self.indexAt(pos)
        if not index.isValid():
            self._fade_out()
            return
        name_index = index.sibling(index.row(), 0)
        self._current_index = name_index
        try:
            rect = self.visualRect(index)
            self._menu_button.move(
                max(0, rect.right() - self._menu_button.width() - 4),
                max(0, rect.top() + 2),
            )
            self._menu_button.raise_()
            self._fade_in()
        except Exception:
            pass

    def _fade_in(self) -> None:
        try:
            if self._menu_button.isHidden():
                self._menu_button.show()
            if self._fade is not None:
                self._fade.stop()
                self._fade.setStartValue(
                    self._menu_button.graphicsEffect().opacity()
                )
                self._fade.setEndValue(1.0)
                self._fade.start()
        except Exception:
            self._menu_button.show()

    def _fade_out(self) -> None:
        try:
            self._current_index = None
            if self._fade is not None:
                self._fade.stop()
                self._fade.setStartValue(
                    self._menu_button.graphicsEffect().opacity()
                )
                self._fade.setEndValue(0.0)
                try:
                    self._fade.finished.disconnect()
                except Exception:
                    pass
                self._fade.finished.connect(self._menu_button.hide)
                self._fade.start()
            else:
                self._menu_button.hide()
        except Exception:
            self._menu_button.hide()
