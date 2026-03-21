"""
DelugeHub — Toast Notification Widget

Usage (from any QWidget in the app):
    from app.widgets.toast import Toast
    Toast.show(parent_widget, "Datei gespeichert!", kind="success")
"""
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QApplication
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint


_KIND_OBJECT_NAMES = {
    "success": "ToastSuccess",
    "error":   "ToastError",
    "info":    "ToastInfo",
    "warning": "ToastWarning",
}

_KIND_ICONS = {
    "success": "✅",
    "error":   "❌",
    "info":    "ℹ",
    "warning": "⚠",
}


class _ToastWidget(QFrame):
    """Internal: a single toast notification frame."""

    def __init__(self, message: str, kind: str, parent):
        super().__init__(parent)
        self.setObjectName(_KIND_OBJECT_NAMES.get(kind, "ToastInfo"))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 16, 8)
        layout.setSpacing(8)

        icon = QLabel(_KIND_ICONS.get(kind, "ℹ"))
        icon.setObjectName("ToastLabel")
        icon.setFixedWidth(20)
        icon.setAlignment(Qt.AlignCenter)

        lbl = QLabel(message)
        lbl.setObjectName("ToastLabel")
        lbl.setWordWrap(True)

        layout.addWidget(icon)
        layout.addWidget(lbl, 1)

        self.adjustSize()

    def _position(self):
        """Place the toast at the bottom-right of the parent widget."""
        parent = self.parent()
        if parent is None:
            return
        margin = 16
        pos = parent.mapToGlobal(QPoint(
            parent.width() - self.width() - margin,
            parent.height() - self.height() - margin
        ))
        # Convert back to parent-relative for child widgets
        if hasattr(parent, 'mapFromGlobal'):
            pos = parent.mapFromGlobal(pos)
        self.move(pos)

    def show_animated(self, duration_ms: int = 3000):
        self._position()
        self.show()
        self.raise_()

        # Fade-out after duration
        QTimer.singleShot(duration_ms, self._start_fade_out)

    def _start_fade_out(self):
        # Slide down + delete
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(300)
        anim.setStartValue(self.pos())
        anim.setEndValue(self.pos() + QPoint(0, 24))
        anim.setEasingCurve(QEasingCurve.InQuad)
        anim.finished.connect(self.deleteLater)
        anim.start(QPropertyAnimation.DeleteWhenStopped)


class Toast:
    """
    Static helper — call Toast.show() from anywhere.

    :param anchor: a QWidget whose bottom-right corner is used as the anchor.
    :param message: text to display.
    :param kind: "success" | "error" | "info" | "warning"
    :param duration: milliseconds before the toast auto-dismisses (default 3 s).
    """

    @staticmethod
    def show(anchor, message: str, kind: str = "info", duration: int = 3000):
        # Find the top-level window to parent the toast to
        root = anchor
        while root.parent() is not None and not isinstance(root.parent(), type(None)):
            candidate = root.parent()
            if not hasattr(candidate, 'width'):
                break
            root = candidate

        toast = _ToastWidget(message, kind, root)
        toast.setMinimumWidth(280)
        toast.setMaximumWidth(480)
        toast.adjustSize()
        toast.show_animated(duration)
