"""
PyQt6/QTest utilities placeholder for Option B harness.

Current GUI manager is Tkinter (`app.py:ServerManager`).
This module provides a minimal abstraction so we can later drive a PyQt6 wrapper
without changing test call sites.
"""
from dataclasses import dataclass
from typing import Optional

try:
    from PyQt6 import QtWidgets, QtCore, QtTest
except Exception:  # PyQt not strictly required for non-GUI tests
    QtWidgets = None
    QtCore = None
    QtTest = None


@dataclass
class QtHarness:
    app: Optional[object] = None

    def ensure_app(self):
        if QtWidgets is None:
            return False
        if self.app is None:
            self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        return True

    def click(self, widget):
        if QtTest is None:
            return False
        QtTest.QTest.mouseClick(widget, QtCore.Qt.MouseButton.LeftButton)
        return True

    def type_text(self, widget, text: str):
        if QtTest is None:
            return False
        widget.setFocus()
        QtTest.QTest.keyClicks(widget, text)
        return True

    def wait(self, ms: int):
        if QtTest is None:
            return False
        QtTest.QTest.qWait(ms)
        return True
