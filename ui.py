"""Oberfläche: Wochenraster, Tomaten, Einstellungsdialog.

Alles wird in einem einzigen paintEvent gezeichnet (keine Widgets pro Termin).
Das verhindert Flackern und Speicherzuwachs bei häufigen Aktualisierungen.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF, QRadialGradient)
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                             QHBoxLayout, QLineEdit, QSlider, QSpinBox, QToolTip, QWidget)

import desktop_win
import tomato
from schedule import AllDayPlacement, Event, Placement, place_events

# --- Texte ---------------------------------------------------------------------

TEXTS = {
    "de": {
        "days": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
        "earlier": "früher", "later": "später",
        "ok": "Aktualisiert {time}",
        "not_running": "Outlook läuft nicht. Neuer Versuch in {retry} s.",
        "unreachable": "Outlook ist gerade nicht erreichbar. Neuer Versuch in {retry} s.",
        "calendar_missing": "Kalender „{calendar}“ nicht gefunden. Neuer Versuch in {retry} s.",
        "open_failed": "Termin konnte nicht in Outlook geöffnet werden.",
        "loading": "Verbinde mit Outlook …",
        "progress": "Fortschritt", "edit": "Verschieben: ziehen · Größe: Ecke unten rechts · fertig über das Tray-Menü",
        "all_day": "ganztägig",
        "settings": "Einstellungen", "start_hour": "Beginn (Uhr)", "end_hour": "Ende (Uhr)",
        "weekdays": "Wochentage", "refresh": "Aktualisierung (s)", "calendar": "Kalender (leer = Hauptkalender)",
        "theme": "Darstellung", "themes": {"system": "wie Windows", "light": "hell", "dark": "dunkel"},
        "hide_private": "Private Termine nur als „Belegt“ zeigen", "language": "Sprache",
        "opacity": "Deckkraft", "desktop_mode": "Desktop-Modus (Neustart nötig)",
        "modes": {"bottom": "hinter allen Fenstern", "workerw": "in der Desktop-Ebene (experimentell)"},
        "click_open": "Klick öffnet den Termin in Outlook",
    },
    "en": {
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "earlier": "earlier", "later": "later",
        "ok": "Updated {time}",
        "not_running": "Outlook is not running. Retrying in {retry} s.",
        "unreachable": "Outlook is not reachable right now. Retrying in {retry} s.",
        "calendar_missing": "Calendar “{calendar}” not found. Retrying in {retry} s.",
        "open_failed": "Could not open the appointment in Outlook.",
        "loading": "Connecting to Outlook …",
        "progress": "Progress", "edit": "Move: drag · Resize: bottom-right corner · finish via tray menu",
        "all_day": "all day",
        "settings": "Settings", "start_hour": "Start (hour)", "end_hour": "End (hour)",
        "weekdays": "Weekdays", "refresh": "Refresh (s)", "calendar": "Calendar (empty = main calendar)",
        "theme": "Theme", "themes": {"system": "like Windows", "light": "light", "dark": "dark"},
        "hide_private": "Show private appointments as “Busy” only", "language": "Language",
        "opacity": "Opacity", "desktop_mode": "Desktop mode (restart required)",
        "modes": {"bottom": "behind all windows", "workerw": "desktop layer (experimental)"},
        "click_open": "Click opens the appointment in Outlook",
    },
}


def tr(cfg: dict, key: str):
    return TEXTS[cfg["language"]][key]


# --- Farben (Kontraste nach WCAG AA geprüft: Text ≥ 4,5:1 auf Blockhintergrund) ---

@dataclass(frozen=True)
class Theme:
    bg: QColor
    today: QColor
    grid: QColor
    text: QColor
    text2: QColor
    block: QColor
    block_past: QColor
    block_border: QColor
    now: QColor
    allday: QColor


LIGHT = Theme(QColor("#FAFAF7"), QColor("#FFF6E0"), QColor("#DADAD4"), QColor("#1B1B1B"), QColor("#4A4A4A"),
              QColor("#E8EEF5"), QColor("#EFEFEC"), QColor("#7D97B3"), QColor("#C62828"), QColor("#DCE8DC"))
DARK = Theme(QColor("#1E1F22"), QColor("#2B2A22"), QColor("#3A3B40"), QColor("#EDEDED"), QColor("#C3C7CD"),
             QColor("#2B3540"), QColor("#26282C"), QColor("#56708C"), QColor("#FF6B6B"), QColor("#24362A"))


def resolve_theme(cfg: dict) -> Theme:
    mode = cfg["theme"]
    if mode == "system":
        mode = "dark" if desktop_win.system_uses_dark_mode() else "light"
    return DARK if mode == "dark" else LIGHT


# --- Tomate zeichnen -------------------------------------------------------------

def paint_tomato(painter: QPainter, center: QPointF, size: float, p: float, st: str) -> None:
    """Zeichnet eine Tomate mit QPainter. size = Durchmesser in Pixeln."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    body = QColor(*tomato.ripeness_color(p))
    if st == "past":
        body = body.darker(125)

    w, h = size, size * 0.88
    rect = QRectF(center.x() - w / 2, center.y() - h / 2 + size * 0.06, w, h)
    grad = QRadialGradient(rect.center() - QPointF(w * 0.18, h * 0.2), w * 0.75)
    grad.setColorAt(0.0, body.lighter(135))
    grad.setColorAt(1.0, body.darker(108))
    painter.setPen(QPen(body.darker(140), max(1.0, size * 0.04)))
    painter.setBrush(QBrush(grad))
    painter.drawEllipse(rect)

    # Glanzlicht
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 90))
    painter.drawEllipse(QRectF(rect.left() + w * 0.2, rect.top() + h * 0.22, w * 0.18, h * 0.12))

    # Kelch (5 Zacken) und Stiel: bleiben immer frisch grün
    green = QColor(46, 125, 50)
    calyx = QPointF(center.x(), rect.top() + h * 0.1)
    star = QPolygonF()
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        r = size * (0.27 if i % 2 == 0 else 0.08)
        star.append(QPointF(calyx.x() + r * math.cos(angle), calyx.y() + r * 0.7 * math.sin(angle)))
    painter.setBrush(green)
    painter.drawPolygon(star)
    pen = QPen(green.darker(115), max(1.5, size * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(calyx, calyx + QPointF(size * 0.07, -size * 0.17))

    if st == "past":  # Häkchen
        pen = QPen(QColor(255, 255, 255, 230), max(1.5, size * 0.1))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        c = rect.center()
        painter.drawPolyline(QPolygonF([c + QPointF(-w * 0.2, 0), c + QPointF(-w * 0.04, h * 0.17),
                                        c + QPointF(w * 0.22, -h * 0.17)]))
    painter.restore()


def tomato_icon(px: int = 64) -> QPixmap:
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    paint_tomato(painter, QPointF(px / 2, px / 2 + px * 0.04), px * 0.86, 1.0, "running")
    painter.end()
    return pm


# --- Wochenraster ----------------------------------------------------------------

class ScheduleWidget(QWidget):
    open_requested = pyqtSignal(object)        # Event
    geometry_committed = pyqtSignal(list)      # [x, y, w, h]

    MARGIN, HEADER_H, TIMECOL_W, STATUS_H, ALLDAY_ROW_H = 10, 30, 54, 26, 24

    def __init__(self, cfg: dict, now_fn: Callable[[], datetime] = datetime.now) -> None:
        super().__init__()
        self.cfg = cfg
        self.now_fn = now_fn
        self.week_start: date | None = None
        self.events: list[Event] = []
        self.timed: list[Placement] = []
        self.all_day: list[AllDayPlacement] = []
        self.status = tr(cfg, "loading")
        self.edit_mode = False
        self._hits: list[tuple[QRectF, Event, Placement | None]] = []
        self._outside_hits: list[tuple[QRectF, str]] = []
        self._drag: tuple[str, QPoint, QRect] | None = None
        self._native_failed = False

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                            | Qt.WindowType.WindowStaysOnBottomHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setMinimumSize(420, 300)
        self.apply_config(cfg)

        # Nur neu zeichnen (Tomaten reifen, Uhrzeitlinie wandert); Outlook fragt der Worker ab.
        self._tick = QTimer(self)
        self._tick.timeout.connect(self.update)
        self._tick.start(15_000)

    # --- Daten -------------------------------------------------------------------
    def apply_config(self, cfg: dict) -> None:
        self.cfg = cfg
        self.theme = resolve_theme(cfg)
        self.setWindowOpacity(cfg["opacity"] / 100)
        self._relayout()
        self.update()

    def set_events(self, week_start: date, events: list) -> None:
        self.week_start, self.events = week_start, events
        self._relayout()
        self.update()

    def set_status(self, key: str, ok: bool) -> None:
        if ok:
            self.status = tr(self.cfg, "ok").format(time=self.now_fn().strftime("%H:%M"))
        else:
            self.status = tr(self.cfg, key).format(retry=self.cfg["retry_seconds"], calendar=self.cfg["calendar"])
        self.update()

    def _relayout(self) -> None:
        if self.week_start is None:
            return
        c = self.cfg
        self.timed, self.all_day = place_events(self.events, self.week_start, c["days"], c["start_hour"], c["end_hour"])

    # --- Geometrie ------------------------------------------------------------------
    def _font(self, bold: bool = False, pt: int = 12) -> QFont:
        f = QFont(self.font())
        f.setPointSize(pt)  # mindestens 12 pt
        f.setBold(bold)
        return f

    def _grid_rect(self) -> QRectF:
        rows = (max(a.row for a in self.all_day) + 1) if self.all_day else 0
        top = self.MARGIN + self.HEADER_H + rows * self.ALLDAY_ROW_H + (6 if rows else 0)
        left = self.MARGIN + self.TIMECOL_W
        return QRectF(left, top, self.width() - left - self.MARGIN,
                      self.height() - top - self.MARGIN - self.STATUS_H)

    def _span(self) -> int:
        return (self.cfg["end_hour"] - self.cfg["start_hour"]) * 60

    # --- Zeichnen -------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        t, cfg, now = self.theme, self.cfg, self.now_fn()
        self._hits, self._outside_hits = [], []

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.bg)
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)

        g = self._grid_rect()
        days = cfg["days"]
        col_w = g.width() / len(days)
        ppm = g.height() / self._span()  # Pixel pro Minute
        dates = [self.week_start + timedelta(days=d) for d in days] if self.week_start else []
        today_col = dates.index(now.date()) if now.date() in dates else -1

        # Heute hervorheben
        if today_col >= 0:
            p.setBrush(t.today)
            p.drawRect(QRectF(g.left() + today_col * col_w, self.MARGIN, col_w,
                              g.bottom() - self.MARGIN))

        # Stundenlinien und Beschriftung
        p.setFont(self._font())
        fm = QFontMetrics(p.font())
        for i in range(cfg["end_hour"] - cfg["start_hour"] + 1):
            y = g.top() + i * 60 * ppm
            p.setPen(QPen(t.grid, 1))
            p.drawLine(QPointF(g.left(), y), QPointF(g.right(), y))
            p.setPen(t.text2)
            p.drawText(QRectF(self.MARGIN, y - fm.height() / 2, self.TIMECOL_W - 8, fm.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{cfg['start_hour'] + i}:00")
        for c in range(len(days) + 1):
            x = g.left() + c * col_w
            p.setPen(QPen(t.grid, 1))
            p.drawLine(QPointF(x, g.top()), QPointF(x, g.bottom()))

        # Kopfzeile mit Wochentag, Datum und Hinweis auf Termine außerhalb
        names = tr(cfg, "days")
        for c, d in enumerate(dates):
            r = QRectF(g.left() + c * col_w + 6, self.MARGIN, col_w - 12, self.HEADER_H)
            p.setFont(self._font(bold=(c == today_col)))
            p.setPen(t.text)
            p.drawText(r, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"{names[d.weekday()]} {d.day:02d}.{d.month:02d}.")
            before = sum(1 for x in self.timed if x.day == c and x.outside == "before")
            after = sum(1 for x in self.timed if x.day == c and x.outside == "after")
            marks = " ".join(s for s in (f"▲{before}" if before else "", f"▼{after}" if after else "") if s)
            if marks:
                p.setFont(self._font())
                p.setPen(t.text2)
                p.drawText(r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, marks)
                tip = []
                for x in self.timed:
                    if x.day == c and x.outside:
                        arrow = "▲" if x.outside == "before" else "▼"
                        tip.append(f"{arrow} {_fmt_range(x.event)}  {x.event.subject}")
                self._outside_hits.append((r, "\n".join(tip)))

        # Ganztägige Termine
        top0 = self.MARGIN + self.HEADER_H
        for a in self.all_day:
            r = QRectF(g.left() + a.first * col_w + 3, top0 + a.row * self.ALLDAY_ROW_H + 2,
                       (a.last - a.first + 1) * col_w - 6, self.ALLDAY_ROW_H - 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.allday)
            p.drawRoundedRect(r, 5, 5)
            p.setPen(t.text)
            p.setFont(self._font())
            p.drawText(r.adjusted(8, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(a.event.subject, Qt.TextElideMode.ElideRight,
                                                         int(r.width() - 14)))
            self._hits.append((r, a.event, None))

        # Termine
        p.setClipRect(g.adjusted(0, 0, 1, 1))
        for pl in self.timed:
            if not pl.outside:
                self._paint_block(p, pl, g, col_w, ppm, now)
        p.setClipping(False)

        # Aktuelle Uhrzeit
        if today_col >= 0:
            minutes = (now.hour - cfg["start_hour"]) * 60 + now.minute + now.second / 60
            if 0 <= minutes <= self._span():
                y = g.top() + minutes * ppm
                p.setPen(QPen(t.now, 1.5))
                x0 = g.left() + today_col * col_w
                p.drawLine(QPointF(x0, y), QPointF(x0 + col_w, y))
                p.setPen(QPen(t.now, 1, Qt.PenStyle.DotLine))
                p.drawLine(QPointF(g.left(), y), QPointF(x0, y))
                p.drawLine(QPointF(x0 + col_w, y), QPointF(g.right(), y))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.now)
                p.drawEllipse(QPointF(x0, y), 4, 4)

        # Statuszeile
        p.setFont(self._font())
        p.setPen(t.text2)
        status = tr(cfg, "edit") if self.edit_mode else self.status
        p.drawText(QRectF(self.MARGIN, self.height() - self.MARGIN - self.STATUS_H + 4,
                          self.width() - 2 * self.MARGIN, self.STATUS_H),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, status)

        if self.edit_mode:
            p.setPen(QPen(t.now, 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)
            p.setBrush(t.now)
            p.drawRect(QRectF(self.width() - 16, self.height() - 16, 14, 14))
        p.end()

    def _paint_block(self, p: QPainter, pl: Placement, g: QRectF, col_w: float, ppm: float, now: datetime) -> None:
        t, ev = self.theme, pl.event
        lane_w = col_w / pl.lanes
        x = g.left() + pl.day * col_w + pl.lane * lane_w + 2
        y = g.top() + pl.top * ppm + 1
        h = max((pl.bottom - pl.top) * ppm - 2, min(22.0, 20 * ppm))
        r = QRectF(x, y, lane_w - 4, h)

        st = tomato.state(now, ev.start, ev.end)
        prog = tomato.progress(now, ev.start, ev.end)
        p.setPen(QPen(t.block_border, 1))
        p.setBrush(t.block_past if st == "past" else t.block)
        p.drawRoundedRect(r, 6, 6)
        if st == "running":  # dezenter Rahmen in Reifefarbe
            p.setPen(QPen(QColor(*tomato.ripeness_color(prog)), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5, 5)

        # Tomate links im Block
        # Laufend: größer und wachsend (70–100 %); Zukunft: klein; Vergangenheit: volle Größe, abgedunkelt.
        base = min(26.0 if st == "running" else 20.0, max(10.0, h - 6))
        size = base * {"future": tomato.MIN_SCALE, "past": 1.0}.get(st, tomato.tomato_scale(prog))
        icon_w = (32 if st == "running" else 26)
        cy = r.top() + min(h / 2, 16)
        paint_tomato(p, QPointF(r.left() + icon_w / 2 + 2, cy), size, prog, st)

        # Text
        p.setFont(self._font(bold=True))
        fm = QFontMetrics(p.font())
        lh = fm.height()
        tx = r.left() + icon_w + 4
        tw = int(r.width() - icon_w - 10)
        rng = _fmt_range(ev)
        if st == "running":  # Restzeit zuerst, damit sie bei schmalen Blöcken sichtbar bleibt
            rng = tomato.remaining_text(now, ev.end, self.cfg["language"]) + " · " + rng
        max_lines = max(1, int((h - 6) // lh))
        if max_lines == 1:
            prefix = "" if pl.cut_top else f"{ev.start:%H:%M} "  # Fortsetzung vom Vortag: keine alte Startzeit
            lines = [(prefix + ev.subject, True)]
        else:
            lines = [(ev.subject, True), (rng, False)]
            if ev.location:
                lines.append((ev.location, False))
        ty = r.top() + 3
        for text, bold in lines[:max_lines]:
            p.setFont(self._font(bold=bold))
            p.setPen(t.text if bold and st != "past" else t.text2)
            p.drawText(QRectF(tx, ty, tw, lh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(text, Qt.TextElideMode.ElideRight, tw))
            ty += lh

        # Fortschrittsbalken beim laufenden Termin
        if st == "running" and h > 14:
            bar = QRectF(r.left() + 6, r.bottom() - 6, r.width() - 12, 3)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.grid)
            p.drawRoundedRect(bar, 1.5, 1.5)
            p.setBrush(QColor(*tomato.ripeness_color(prog)))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * prog, bar.height()), 1.5, 1.5)

        # Pfeile, wenn der Termin am Rasterrand abgeschnitten ist
        p.setFont(self._font())
        p.setPen(t.text2)
        if pl.cut_top:
            p.drawText(QRectF(r.right() - 20, r.top(), 18, lh), Qt.AlignmentFlag.AlignCenter, "▲")
        if pl.cut_bottom:
            p.drawText(QRectF(r.right() - 20, r.bottom() - lh, 18, lh), Qt.AlignmentFlag.AlignCenter, "▼")

        self._hits.append((r, ev, pl))

    # --- Maus --------------------------------------------------------------------
    def _hit(self, pos: QPointF) -> Event | None:
        for r, ev, _ in reversed(self._hits):
            if r.contains(pos):
                return ev
        return None

    def event(self, e) -> bool:
        if e.type() == e.Type.ToolTip:
            pos = QPointF(e.pos())
            ev = self._hit(pos)
            if ev is not None:
                QToolTip.showText(e.globalPos(), self._tooltip(ev), self)
                return True
            for r, text in self._outside_hits:
                if r.contains(pos):
                    QToolTip.showText(e.globalPos(), text, self)
                    return True
            QToolTip.hideText()
            e.ignore()
            return True
        return super().event(e)

    def _tooltip(self, ev: Event) -> str:
        now = self.now_fn()
        lines = [ev.subject, _fmt_range(ev) if not ev.all_day else tr(self.cfg, "all_day")]
        if ev.location:
            lines.append(ev.location)
        if not ev.all_day:
            prog = tomato.progress(now, ev.start, ev.end)
            lines.append(f"{tr(self.cfg, 'progress')}: {tomato.percent_text(prog)}")
            if tomato.state(now, ev.start, ev.end) == "running":
                lines.append(tomato.remaining_text(now, ev.end, self.cfg["language"]))
        return "\n".join(lines)

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.edit_mode:
            grip = QRectF(self.width() - 20, self.height() - 20, 20, 20).contains(e.position())
            self._drag = ("resize" if grip else "move", e.globalPosition().toPoint(), self.geometry())
            return
        ev = self._hit(e.position())
        if ev is not None and self.cfg["click_opens_in_outlook"] and ev.entry_id:
            self.open_requested.emit(ev)

    def mouseMoveEvent(self, e) -> None:
        if not self._drag:
            return
        kind, start, geo = self._drag
        d = e.globalPosition().toPoint() - start
        if kind == "move":
            self.move(geo.topLeft() + d)
        else:
            self.resize(max(self.minimumWidth(), geo.width() + d.x()),
                        max(self.minimumHeight(), geo.height() + d.y()))

    def mouseReleaseEvent(self, _e) -> None:
        if self._drag:
            self._drag = None
            g = self.geometry()
            self.geometry_committed.emit([g.x(), g.y(), g.width(), g.height()])

    def set_edit_mode(self, on: bool) -> None:
        self.edit_mode = on
        self.update()

    def nativeEvent(self, event_type, message):
        if desktop_win.IS_WINDOWS and self.cfg["desktop_mode"] == "bottom" and not self._native_failed:
            try:
                if bytes(event_type) == b"windows_generic_MSG":
                    desktop_win.keep_bottom_from_message(int(message))
            except Exception:  # nie wegen der Z-Order abstürzen; dann bleibt nur pin_to_bottom aktiv
                self._native_failed = True
                logging.getLogger(__name__).exception("nativeEvent deaktiviert")
        return super().nativeEvent(event_type, message)


def _fmt_range(ev: Event) -> str:
    if ev.start.date() == ev.end.date():
        return f"{ev.start:%H:%M}–{ev.end:%H:%M}"
    return f"{ev.start:%d.%m. %H:%M}–{ev.end:%d.%m. %H:%M}"


# --- Einstellungen --------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self.cfg = dict(cfg)
        T = TEXTS[cfg["language"]]
        self.setWindowTitle(T["settings"])
        form = QFormLayout(self)

        self.start = QSpinBox(minimum=0, maximum=23, value=cfg["start_hour"])
        self.end = QSpinBox(minimum=1, maximum=24, value=cfg["end_hour"])
        form.addRow(T["start_hour"], self.start)
        form.addRow(T["end_hour"], self.end)

        row = QHBoxLayout()
        self.day_boxes = []
        for i, name in enumerate(T["days"]):
            box = QCheckBox(name)
            box.setChecked(i in cfg["days"])
            self.day_boxes.append(box)
            row.addWidget(box)
        form.addRow(T["weekdays"], row)

        self.refresh = QSpinBox(minimum=15, maximum=3600, value=cfg["refresh_seconds"])
        form.addRow(T["refresh"], self.refresh)
        self.calendar = QLineEdit(cfg["calendar"])
        form.addRow(T["calendar"], self.calendar)

        self.theme = QComboBox()
        for key, label in T["themes"].items():
            self.theme.addItem(label, key)
        self.theme.setCurrentIndex(self.theme.findData(cfg["theme"]))
        form.addRow(T["theme"], self.theme)

        self.hide_private = QCheckBox(T["hide_private"])
        self.hide_private.setChecked(cfg["hide_private"])
        form.addRow("", self.hide_private)
        self.click_open = QCheckBox(T["click_open"])
        self.click_open.setChecked(cfg["click_opens_in_outlook"])
        form.addRow("", self.click_open)

        self.language = QComboBox()
        self.language.addItem("Deutsch", "de")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(self.language.findData(cfg["language"]))
        form.addRow(T["language"], self.language)

        self.opacity = QSlider(Qt.Orientation.Horizontal, minimum=10, maximum=100, value=cfg["opacity"])
        form.addRow(T["opacity"], self.opacity)

        self.mode = QComboBox()
        for key, label in T["modes"].items():
            self.mode.addItem(label, key)
        self.mode.setCurrentIndex(self.mode.findData(cfg["desktop_mode"]))
        form.addRow(T["desktop_mode"], self.mode)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_config(self) -> dict:
        c = dict(self.cfg)
        c.update(
            start_hour=self.start.value(), end_hour=self.end.value(),
            days=[i for i, b in enumerate(self.day_boxes) if b.isChecked()],
            refresh_seconds=self.refresh.value(), calendar=self.calendar.text().strip(),
            theme=self.theme.currentData(), hide_private=self.hide_private.isChecked(),
            click_opens_in_outlook=self.click_open.isChecked(), language=self.language.currentData(),
            opacity=self.opacity.value(), desktop_mode=self.mode.currentData(),
        )
        return c
