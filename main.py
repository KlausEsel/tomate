"""Tomatenplan – Wochenstundenplan aus Outlook als Tomaten auf dem Desktop.

Start:  pythonw main.py          (mit Outlook)
        python main.py --demo    (Beispieldaten, ohne Outlook)
"""
from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtCore import QLockFile, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import config
import desktop_win
from ui import ScheduleWidget, SettingsDialog, tomato_icon

log = logging.getLogger("tomatenplan")


class Bridge(QObject):
    """Überträgt Ergebnisse aus dem Worker-Thread sicher in den UI-Thread (Queued Connection)."""
    events = pyqtSignal(object, object)
    status = pyqtSignal(str, bool)


class App:
    def __init__(self, demo: bool) -> None:
        self.qapp = QApplication(sys.argv)
        self.qapp.setQuitOnLastWindowClosed(False)
        self.cfg = config.load()

        self.widget = ScheduleWidget(self.cfg)
        self.widget.setWindowIcon(QIcon(tomato_icon()))
        self._restore_geometry()

        self.bridge = Bridge()
        self.bridge.events.connect(self.widget.set_events)
        self.bridge.status.connect(self.widget.set_status)
        if demo:
            from demo import DemoSource
            self.source = DemoSource(self.bridge.events.emit, self.bridge.status.emit)
        else:
            from outlook_reader import OutlookWorker
            self.source = OutlookWorker(lambda: dict(self.cfg), self.bridge.events.emit, self.bridge.status.emit)
        self.widget.open_requested.connect(self.source.request_open)
        self.widget.geometry_committed.connect(self._save_geometry)

        self._build_tray()
        self.widget.show()
        self._pin()
        self.source.start()

        # Wochenwechsel um Mitternacht sofort übernehmen (sonst spätestens beim nächsten Intervall).
        self._day = None
        self._daycheck = QTimer()
        self._daycheck.timeout.connect(self._check_day)
        self._daycheck.start(60_000)

    # --- Fenster -----------------------------------------------------------------
    def _restore_geometry(self) -> None:
        geo = self.cfg["geometry"]
        if geo:
            self.widget.setGeometry(*geo)
            return
        screen = QGuiApplication.primaryScreen().availableGeometry()
        w, h = min(1100, int(screen.width() * 0.7)), min(760, int(screen.height() * 0.85))
        self.widget.setGeometry(screen.right() - w - 20, screen.top() + 20, w, h)

    def _save_geometry(self, geo: list) -> None:
        self.cfg["geometry"] = geo
        config.save(self.cfg)

    def _pin(self) -> None:
        hwnd = int(self.widget.winId())
        if self.cfg["desktop_mode"] == "workerw" and desktop_win.attach_to_workerw(hwnd):
            return
        desktop_win.pin_to_bottom(hwnd)

    def _check_day(self) -> None:
        from datetime import date
        today = date.today()
        if self._day is not None and today != self._day:
            self.source.request_refresh()
        self._day = today

    # --- Tray --------------------------------------------------------------------
    def _build_tray(self) -> None:
        de = self.cfg["language"] == "de"
        self.tray = QSystemTrayIcon(QIcon(tomato_icon()))
        self.tray.setToolTip("Tomatenplan")
        menu = QMenu()

        def add(text_de: str, text_en: str, slot, checkable=False, checked=False) -> QAction:
            act = QAction(text_de if de else text_en, menu, checkable=checkable)
            act.setChecked(checked)
            act.triggered.connect(slot)
            menu.addAction(act)
            return act

        add("Anzeigen/Verbergen", "Show/Hide", self._toggle_visible)
        add("Jetzt aktualisieren", "Refresh now", self.source_refresh)
        self.edit_action = add("Position und Größe anpassen", "Adjust position and size",
                               self._toggle_edit, checkable=True)
        add("Einstellungen …", "Settings …", self._settings)
        if desktop_win.IS_WINDOWS:
            add("Autostart", "Start with Windows", self._toggle_autostart,
                checkable=True, checked=desktop_win.autostart_enabled())
        menu.addSeparator()
        add("Beenden", "Quit", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._toggle_visible() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()
        self._menu = menu  # Referenz halten

    def source_refresh(self) -> None:
        self.source.request_refresh()

    def _toggle_visible(self) -> None:
        if self.widget.isVisible():
            self.widget.hide()
        else:
            self.widget.show()
            self._pin()

    def _toggle_edit(self, on: bool) -> None:
        self.widget.set_edit_mode(on)

    def _toggle_autostart(self, on: bool) -> None:
        try:
            desktop_win.set_autostart(on)
        except OSError:
            log.exception("Autostart konnte nicht geändert werden")

    def _settings(self) -> None:
        dlg = SettingsDialog(self.cfg)
        if dlg.exec():
            self.cfg = config.validate(dlg.result_config())
            config.save(self.cfg)
            self.widget.apply_config(self.cfg)
            self.source.request_refresh()

    def quit(self) -> None:
        self.source.stop()
        self.source.join(timeout=3)
        self.tray.hide()
        self.qapp.quit()

    def run(self) -> int:
        return self.qapp.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="Tomatenplan")
    parser.add_argument("--demo", action="store_true", help="Beispieldaten statt Outlook")
    args = parser.parse_args()

    # Protokolliert nur technische Fehler, nie Termininhalte.
    logging.basicConfig(filename=str(config.config_path().with_name("tomatenplan.log")),
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    lock = QLockFile(str(config.config_path().with_name("tomatenplan.lock")))
    if not lock.tryLock(100):
        print("Tomatenplan läuft bereits.")
        return 0
    return App(args.demo).run()


if __name__ == "__main__":
    sys.exit(main())
