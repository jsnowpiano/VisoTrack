import sys
import time
import numpy as np
import cv2
import requests

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QProgressBar,
    QSizePolicy, QScrollArea, QComboBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QColor, QPainter, QPen, QBrush, QFont

import mediapipe as mp
from eye_tracker import EyeTracker

# ─────────────────────────────────────────────────────────────
#  API base URL — update if Flask runs on a different host/port
# ─────────────────────────────────────────────────────────────
API_BASE = "http://127.0.0.1:5000"

# ─────────────────────────────────────────────────────────────
#  Design tokens
# ─────────────────────────────────────────────────────────────
BG         = "#EEECE8"
SIDEBAR_BG = "#FFFFFF"
HEADER_BG  = "#0D1B2A"
CARD_BG    = "#FFFFFF"
TEXT_DARK  = "#111111"
TEXT_MED   = "#555555"
TEXT_LIGHT = "#999999"
ACCENT     = "#4A6FA5"
ACCENT_DK  = "#2E4D7A"
BORDER     = "#E0DDD8"
SUCCESS    = "#3A9E6B"
WARNING    = "#D4870A"
DANGER     = "#C0392B"

STYLESHEET = f"""
* {{ font-family: 'Helvetica Neue', 'Segoe UI', sans-serif; outline: none; }}
QMainWindow, QWidget {{ background-color: {BG}; color: {TEXT_DARK}; }}

#Sidebar {{
    background-color: {SIDEBAR_BG};
    border-right: 1px solid {BORDER};
    min-width: 240px; max-width: 240px;
}}
#SidebarHeader {{
    background-color: {HEADER_BG};
    min-height: 110px; max-height: 110px;
}}
#NavSection {{
    color: {TEXT_DARK}; font-size: 13px; font-weight: 700;
    padding: 20px 28px 8px 28px;
}}
#NavLink {{
    background: transparent; color: {TEXT_MED}; border: none;
    text-align: left; padding: 9px 28px; font-size: 13px;
}}
#NavLink:hover {{ color: {ACCENT}; background: transparent; }}
#NavLink[active="true"] {{ color: {ACCENT}; font-weight: 600; }}

#Card {{
    background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 4px;
}}
#CardTitle {{ font-size: 16px; font-weight: 600; color: {TEXT_DARK}; }}
#CardSubtitle {{ font-size: 13px; color: {TEXT_MED}; }}
#CardNote {{ font-size: 12px; color: {TEXT_MED}; }}

#PrimaryBtn {{
    background-color: {ACCENT}; color: white; border: none; border-radius: 3px;
    padding: 14px 40px; font-size: 14px; font-weight: 600; min-width: 160px;
}}
#PrimaryBtn:hover {{ background-color: {ACCENT_DK}; }}
#PrimaryBtn:pressed {{ background-color: #1e3a5f; }}
#PrimaryBtn:disabled {{ background-color: #aab8cb; color: #dde5ef; }}

#GhostBtn {{
    background: transparent; color: {ACCENT}; border: 1px solid {ACCENT};
    border-radius: 3px; padding: 10px 28px; font-size: 13px;
}}
#GhostBtn:hover {{ background: #eef2f8; }}

QProgressBar {{
    background: #E8E4E0; border: none; border-radius: 2px;
    height: 6px; text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}

QScrollBar:vertical {{
    background: {BG}; width: 6px; border-radius: 3px;
}}
QScrollBar::handle:vertical {{ background: #C8C4BF; border-radius: 3px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

#BottomBar {{
    background: {SIDEBAR_BG}; border-top: 1px solid {BORDER};
    padding: 6px 20px; min-height: 32px; max-height: 32px;
    font-size: 11px; color: {TEXT_LIGHT};
}}
#MetricLabel {{ font-size: 11px; color: {TEXT_LIGHT}; letter-spacing: 1px; }}

QComboBox {{
    background: {CARD_BG}; color: {TEXT_DARK}; border: 1px solid {BORDER};
    border-radius: 3px; padding: 6px 12px; font-size: 13px; min-width: 220px;
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background: {CARD_BG}; border: 1px solid {BORDER}; color: {TEXT_DARK};
    selection-background-color: #eef2f8; selection-color: {ACCENT};
    outline: none;
}}
"""

# ─────────────────────────────────────────────────────────────
#  Calibration overlay
# ─────────────────────────────────────────────────────────────
class CalibOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._px = 0.5; self._py = 0.5; self._t = 0
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick)

    def show_point(self, px, py):
        self._px = px; self._py = py; self._t = 0
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen); self.showFullScreen(); self.raise_()
        self._timer.start(30)

    def hide_overlay(self):
        self._timer.stop(); self.hide()

    def _tick(self):
        self._t += 1; self.update()

    def paintEvent(self, e):
        import math
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 180))
        w, h = self.rect().width(), self.rect().height()
        x = int(self._px * w); y = int(self._py * h)
        pulse = 22 + 6 * math.sin(self._t * 0.15)
        p.setPen(QPen(QColor(ACCENT), 2)); p.setBrush(Qt.NoBrush)
        p.drawEllipse(int(x - pulse), int(y - pulse), int(pulse * 2), int(pulse * 2))
        p.setBrush(QBrush(QColor(ACCENT))); p.setPen(Qt.NoPen)
        p.drawEllipse(x - 7, y - 7, 14, 14)
        p.setPen(QColor(255, 255, 255, 200))
        p.setFont(QFont("Helvetica Neue", 11))
        p.drawText(x + 32, y + 5, "Look here")
        p.end()


# ─────────────────────────────────────────────────────────────
#  3×3 point grid
# ─────────────────────────────────────────────────────────────
class PointGrid(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(108, 72); self._active = -1; self._done = set()

    def reset(self):
        self._active = -1; self._done.clear(); self.update()

    def set_active(self, idx):
        if self._active >= 0: self._done.add(self._active)
        self._active = idx; self.update()

    def set_done(self):
        self._done = set(range(9)); self._active = -1; self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        cw = self.width() / 3; ch = self.height() / 3
        for i in range(9):
            row, col = divmod(i, 3)
            cx = int((col + 0.5) * cw); cy = int((row + 0.5) * ch)
            if i == self._active:    color, r = QColor(ACCENT), 7
            elif i in self._done:    color, r = QColor(SUCCESS), 5
            else:                    color, r = QColor(BORDER), 5
            p.setBrush(QBrush(color)); p.setPen(Qt.NoPen)
            p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        p.end()


# ─────────────────────────────────────────────────────────────
#  Gaze trail map
# ─────────────────────────────────────────────────────────────
class GazeMap(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(200)
        self._gx = 0.5; self._gy = 0.5; self._trail = []

    def update_gaze(self, gx, gy):
        self._gx = gx; self._gy = gy
        self._trail.append((gx, gy))
        if len(self._trail) > 100: self._trail.pop(0)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect(); w, h = r.width(), r.height()
        p.fillRect(r, QColor("#F7F5F2"))
        p.setPen(QPen(QColor(BORDER), 1))
        for i in range(1, 4):
            p.drawLine(int(w * i / 4), 0, int(w * i / 4), h)
            p.drawLine(0, int(h * i / 4), w, int(h * i / 4))
        for i, (tx, ty) in enumerate(self._trail):
            alpha = int(160 * i / max(len(self._trail), 1))
            p.setBrush(QColor(74, 111, 165, alpha)); p.setPen(Qt.NoPen)
            rad = max(2, int(5 * i / max(len(self._trail), 1)))
            p.drawEllipse(int(tx * w) - rad, int(ty * h) - rad, rad * 2, rad * 2)
        gx_px = int(self._gx * w); gy_px = int(self._gy * h)
        p.setBrush(QBrush(QColor(ACCENT))); p.setPen(QPen(QColor("white"), 2))
        p.drawEllipse(gx_px - 7, gy_px - 7, 14, 14)
        p.end()


# ─────────────────────────────────────────────────────────────
#  Card helper
# ─────────────────────────────────────────────────────────────
def make_card(margins=(32, 32, 32, 32), spacing=16):
    card = QFrame(); card.setObjectName("Card")
    lay  = QVBoxLayout(card); lay.setContentsMargins(*margins); lay.setSpacing(spacing)
    return card, lay

def hdiv():
    d = QFrame(); d.setFrameShape(QFrame.HLine)
    d.setStyleSheet(f"color:{BORDER};"); return d


# ─────────────────────────────────────────────────────────────
#  Study Screen — fullscreen black overlay with centred image
# ─────────────────────────────────────────────────────────────
class StudyScreen(QWidget):
    finished = pyqtSignal(bool, list)

    def __init__(self, image_b64: str, viewing_time: int):
        super().__init__()
        import base64 as _b64
        self._gaze_points    = []
        self._viewing_time   = max(1, viewing_time)
        self._elapsed        = 0
        self._finished_guard = False
        self._gaze_signal    = None

        self._img_x = 0; self._img_y = 0
        self._img_w = 1; self._img_h = 1

        self._pixmap = None
        if image_b64:
            try:
                data = _b64.b64decode(image_b64)
                pix  = QPixmap()
                pix.loadFromData(data)
                if not pix.isNull():
                    self._pixmap = pix
            except Exception:
                pass

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("background: #000000;")

        self._countdown_lbl = QLabel(self)
        self._countdown_lbl.setStyleSheet(
            "color: rgba(255,255,255,140); font-size: 18px; "
            "font-family: 'Helvetica Neue', sans-serif; background: transparent;"
        )
        self._countdown_lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self._countdown_lbl.resize(220, 40)

        self._hint_lbl = QLabel("Press  Esc  to cancel", self)
        self._hint_lbl.setStyleSheet(
            "color: rgba(255,255,255,60); font-size: 12px; "
            "font-family: 'Helvetica Neue', sans-serif; background: transparent;"
        )
        self._hint_lbl.setAlignment(Qt.AlignCenter)
        self._hint_lbl.resize(300, 28)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, viewing_time * 10)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(3)
        self._progress.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,30); border: none; border-radius: 0; }"
            "QProgressBar::chunk { background: rgba(74,111,165,200); border-radius: 0; }"
        )

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)

    def start(self, gaze_signal):
        self._gaze_signal = gaze_signal
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self._position_overlays()
        self._update_countdown()
        self._tick_timer.start(100)
        gaze_signal.connect(self._on_gaze)

    def _calc_image_rect(self):
        if not self._pixmap:
            self._img_x = 0; self._img_y = 0
            self._img_w = self.width(); self._img_h = self.height()
            return
        sw = self.width(); sh = self.height()
        max_w = int(sw * 0.80); max_h = int(sh * 0.80)
        scaled = self._pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._img_x = (sw - scaled.width())  // 2
        self._img_y = (sh - scaled.height()) // 2
        self._img_w = max(1, scaled.width())
        self._img_h = max(1, scaled.height())

    def _position_overlays(self):
        w = self.width(); h = self.height()
        self._countdown_lbl.move(w - 240, 20)
        self._hint_lbl.move((w - 300) // 2, h - 48)
        self._progress.setFixedWidth(w)
        self._progress.move(0, h - 3)

    def _tick(self):
        self._elapsed += 1
        self._progress.setValue(self._elapsed)
        self._update_countdown()
        if self._elapsed >= self._viewing_time * 10:
            self._finish(completed=True)

    def _update_countdown(self):
        remaining = max(0, self._viewing_time - self._elapsed // 10)
        self._countdown_lbl.setText(f"{remaining}s remaining  ")

    def _on_gaze(self, gx: float, gy: float):
        sx = gx * self.width()
        sy = gy * self.height()
        ix = (sx - self._img_x) / self._img_w
        iy = (sy - self._img_y) / self._img_h
        ix = max(0.0, min(1.0, ix))
        iy = max(0.0, min(1.0, iy))
        self._gaze_points.append([round(ix, 4), round(iy, 4)])

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._finish(completed=False)
        else:
            super().keyPressEvent(e)

    def _finish(self, completed: bool):
        if self._finished_guard:
            return
        self._finished_guard = True
        self._tick_timer.stop()
        if self._gaze_signal is not None:
            try:
                self._gaze_signal.disconnect(self._on_gaze)
            except Exception:
                pass
        self.hide()
        self.finished.emit(completed, self._gaze_points)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self._pixmap:
            sw = self.width(); sh = self.height()
            max_w = int(sw * 0.80); max_h = int(sh * 0.80)
            scaled = self._pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (sw - scaled.width())  // 2
            y = (sh - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
            self._img_x = x; self._img_y = y
            self._img_w = max(1, scaled.width()); self._img_h = max(1, scaled.height())
        else:
            p.setPen(QColor(80, 80, 80))
            p.setFont(QFont("Helvetica Neue", 16))
            p.drawText(self.rect(), Qt.AlignCenter, "No image for this study")
        p.end()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._calc_image_rect()
        self._position_overlays()


# ─────────────────────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gaze Tracker")
        self.resize(1100, 720); self.setMinimumSize(880, 580)
        self._calib_done  = False; self._tracking = False
        self._frame_count = 0
        self._pending_study  = None
        self._study_screen   = None

        self.worker = EyeTracker()
        self.worker.frame_ready.connect(self._on_frame)
        self.worker.gaze_updated.connect(self._on_gaze)
        self.worker.raw_gaze_updated.connect(self._on_raw_gaze)
        self.worker.calib_step.connect(self._on_calib_step)
        self.worker.calib_done.connect(self._on_calib_done)
        self.overlay = CalibOverlay()

        self._build_ui()
        self.setStyleSheet(STYLESHEET)

        self._fps_timer = QTimer(); self._fps_timer.timeout.connect(self._upd_fps)
        self._fps_timer.start(1000)

        self.worker.start_preview()
        self._set_nav("Assignments")

    # ── Build ────────────────────────────────────────────────
    def _build_ui(self):
        root_w = QWidget(); self.setCentralWidget(root_w)
        root   = QHBoxLayout(root_w); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        right = QWidget(); rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{BG};")
        rl.addWidget(self.stack, 1)

        self.stack.addWidget(self._page_assignments())  # 0
        self.stack.addWidget(self._page_calibration())  # 1
        self.stack.addWidget(self._page_heatmaps())     # 2
        self.stack.addWidget(self._page_camera())       # 3
        self.stack.addWidget(self._page_how_to())       # 4

        self._bottom_bar = QLabel("  Make sure your camera is connected and enabled before starting.")
        self._bottom_bar.setObjectName("BottomBar")
        rl.addWidget(self._bottom_bar)
        root.addWidget(right, 1)

    # ── Sidebar ──────────────────────────────────────────────
    def _build_sidebar(self):
        sb = QWidget(); sb.setObjectName("Sidebar")
        sl = QVBoxLayout(sb); sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(0)

        hdr = QWidget(); hdr.setObjectName("SidebarHeader"); hdr.setFixedHeight(110)
        hdr.setStyleSheet(f"background:{HEADER_BG};")
        hl  = QVBoxLayout(hdr); hl.setAlignment(Qt.AlignCenter)
        logo = QLabel("V")
        logo.setStyleSheet(f"color:{ACCENT};font-size:52px;font-weight:700;font-family:'Georgia',serif;")
        logo.setAlignment(Qt.AlignCenter)
        hl.addWidget(logo)
        sl.addWidget(hdr)
        sl.addSpacing(16)

        self._nav_btns = {}
        for label in ["Assignments", "Calibration", "Heatmaps", "Camera", "How to use"]:
            btn = QPushButton(label); btn.setObjectName("NavLink")
            btn.setCursor(Qt.PointingHandCursor); btn.setFixedHeight(34)
            btn.clicked.connect(lambda chk, l=label: self._set_nav(l))
            sl.addWidget(btn); self._nav_btns[label] = btn

        sl.addStretch()
        return sb

    # ── Pages ────────────────────────────────────────────────
    def _page_assignments(self):
        page  = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(40, 30, 40, 40); outer.setSpacing(20)

        hdr_row = QHBoxLayout()
        h = QLabel("Assignments"); h.setStyleSheet(f"font-size:20px;font-weight:700;color:{TEXT_DARK};")
        hdr_row.addWidget(h); hdr_row.addStretch()
        refresh_btn = QPushButton("↻  Refresh"); refresh_btn.setObjectName("GhostBtn")
        refresh_btn.setCursor(Qt.PointingHandCursor); refresh_btn.setFixedHeight(32)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{ACCENT}; border:1px solid {ACCENT};
                border-radius:3px; padding:4px 16px; font-size:12px; }}
            QPushButton:hover {{ background:#eef2f8; }}
        """)
        refresh_btn.clicked.connect(self._refresh_assignments)
        hdr_row.addWidget(refresh_btn)
        outer.addLayout(hdr_row)

        list_card     = QFrame(); list_card.setObjectName("Card")
        list_card_lay = QVBoxLayout(list_card); list_card_lay.setContentsMargins(0, 0, 0, 0); list_card_lay.setSpacing(0)

        card_hdr = QWidget(); card_hdr.setStyleSheet(f"background:{CARD_BG};border-radius:4px 4px 0 0;")
        card_hdr_lay = QHBoxLayout(card_hdr); card_hdr_lay.setContentsMargins(24, 16, 24, 16)
        ct = QLabel("Assignment List"); ct.setObjectName("CardTitle"); card_hdr_lay.addWidget(ct)
        card_hdr_lay.addStretch()
        self._assign_count_lbl = QLabel("0 assignments")
        self._assign_count_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_LIGHT};")
        card_hdr_lay.addWidget(self._assign_count_lbl)
        list_card_lay.addWidget(card_hdr)

        div = QFrame(); div.setFrameShape(QFrame.HLine); div.setStyleSheet(f"color:{BORDER};")
        list_card_lay.addWidget(div)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background:{CARD_BG};")
        self._assign_list_widget = QWidget(); self._assign_list_widget.setStyleSheet(f"background:{CARD_BG};")
        self._assign_list_lay    = QVBoxLayout(self._assign_list_widget)
        self._assign_list_lay.setContentsMargins(0, 0, 0, 0); self._assign_list_lay.setSpacing(0)

        self._assign_empty = self._make_empty_state()
        self._assign_list_lay.addWidget(self._assign_empty)
        self._assign_list_lay.addStretch()

        scroll.setWidget(self._assign_list_widget)
        list_card_lay.addWidget(scroll, 1)
        outer.addWidget(list_card, 1)

        self._assignments = []
        QTimer.singleShot(500, self._refresh_assignments)
        return page

    def _make_empty_state(self):
        w  = QWidget(); w.setStyleSheet(f"background:{CARD_BG};")
        el = QVBoxLayout(w); el.setAlignment(Qt.AlignCenter); el.setContentsMargins(40, 60, 40, 60)
        icon = QLabel("📋"); icon.setStyleSheet("font-size:36px;"); icon.setAlignment(Qt.AlignCenter); el.addWidget(icon)
        et = QLabel("No assignments yet")
        et.setStyleSheet(f"font-size:15px;font-weight:600;color:{TEXT_DARK};margin-top:12px;")
        et.setAlignment(Qt.AlignCenter); el.addWidget(et)
        es = QLabel("Assignments will appear here once pulled from the database.")
        es.setStyleSheet(f"font-size:12px;color:{TEXT_LIGHT};margin-top:4px;")
        es.setAlignment(Qt.AlignCenter); es.setWordWrap(True); el.addWidget(es)
        return w

    def _refresh_assignments(self):
        self._assign_count_lbl.setText("Loading…")
        self._assign_count_lbl.setStyleSheet(f"font-size:12px;color:{WARNING};")
        QApplication.processEvents()
        try:
            resp = requests.get(f"{API_BASE}/api/studies", timeout=20)
            resp.raise_for_status()
            raw = resp.json()
            if isinstance(raw, dict) and "error" in raw:
                raise RuntimeError(raw["error"])
            assignments = []
            for doc in raw:
                vt = doc.get("viewing_time", "—")
                assignments.append({
                    "name":         doc.get("study_name") or doc.get("name", "Untitled"),
                    "subject":      doc.get("company_name") or doc.get("subject", "—"),
                    "viewing_time": f"{vt}s" if isinstance(vt, int) else str(vt),
                    "status":       doc.get("status", "pending"),
                    "_raw":         doc,
                })
            self._load_assignments(assignments)
            self._assign_count_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_LIGHT};")
        except requests.exceptions.ConnectionError:
            self._assign_count_lbl.setText("Server offline")
            self._assign_count_lbl.setStyleSheet(f"font-size:12px;color:{DANGER};")
            self._bottom_bar.setText("  Could not connect to the backend — is the Flask server running?")
        except requests.exceptions.Timeout:
            self._assign_count_lbl.setText("Timeout")
            self._assign_count_lbl.setStyleSheet(f"font-size:12px;color:{DANGER};")
            self._bottom_bar.setText("  Request timed out. Check your network or server.")
        except requests.exceptions.HTTPError as e:
            self._assign_count_lbl.setText("HTTP Error")
            self._assign_count_lbl.setStyleSheet(f"font-size:12px;color:{DANGER};")
            self._bottom_bar.setText(f"  Server error {e.response.status_code}: {e.response.text[:120]}")
        except Exception as e:
            self._assign_count_lbl.setText("Error")
            self._assign_count_lbl.setStyleSheet(f"font-size:12px;color:{DANGER};")
            self._bottom_bar.setText(f"  Error loading assignments: {e}")

    def _load_assignments(self, assignments):
        self._assignments = list(assignments)
        while self._assign_list_lay.count() > 0:
            item = self._assign_list_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        count = len(self._assignments)
        self._assign_count_lbl.setText(f"{count} assignment{'s' if count != 1 else ''}")
        if count == 0:
            self._assign_list_lay.addWidget(self._make_empty_state())
        else:
            for i, a in enumerate(self._assignments):
                row = self._make_assignment_row(a, i)
                self._assign_list_lay.addWidget(row)
        self._assign_list_lay.addStretch()

    def _make_assignment_row(self, a, idx):
        row = QWidget(); row.setStyleSheet(f"background:{CARD_BG};")
        row.setFixedHeight(64)
        rl = QHBoxLayout(row); rl.setContentsMargins(24, 0, 24, 0); rl.setSpacing(16)

        status    = a.get("status", "pending")
        dot_color = {"complete": SUCCESS, "pending": WARNING, "in_progress": ACCENT}.get(status, TEXT_LIGHT)
        dot = QLabel("●"); dot.setStyleSheet(f"font-size:10px;color:{dot_color};")
        dot.setFixedWidth(14); rl.addWidget(dot)

        info = QVBoxLayout(); info.setSpacing(2)
        name = QLabel(a.get("name", "Untitled Assignment"))
        name.setStyleSheet(f"font-size:13px;font-weight:600;color:{TEXT_DARK};")
        subject = QLabel(a.get("subject", "—"))
        subject.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};")
        info.addWidget(name); info.addWidget(subject)
        rl.addLayout(info, 1)

        vt = QLabel(a.get("viewing_time", "—"))
        vt.setStyleSheet(f"font-size:12px;color:{TEXT_MED};"); vt.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        rl.addWidget(vt)

        start = QPushButton("Start")
        start.setCursor(Qt.PointingHandCursor); start.setFixedSize(64, 30)
        start.setStyleSheet(f"""
            QPushButton {{ background:{ACCENT}; color:white; border:none; border-radius:3px;
                font-size:12px; font-weight:600; }}
            QPushButton:hover {{ background:{ACCENT_DK}; }}
        """)
        start.clicked.connect(lambda chk, assignment=a: self._start_study(assignment))
        rl.addWidget(start)

        wrapper = QWidget(); wrapper.setStyleSheet(f"background:{CARD_BG};")
        wl = QVBoxLayout(wrapper); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(0)
        wl.addWidget(row)
        if idx >= 0:
            div = QFrame(); div.setFrameShape(QFrame.HLine); div.setStyleSheet(f"color:{BORDER};margin:0 24px;")
            wl.addWidget(div)
        return wrapper

    # ── Study session ────────────────────────────────────────
    def _start_study(self, assignment: dict):
        self._pending_study = assignment
        self._bottom_bar.setText(
            f"  Calibrating for '{assignment.get('name','study')}' — follow the dots with your eyes."
        )
        self._set_nav("Calibration")
        self._handle_start()

    def _launch_study_screen(self, assignment: dict):
        study_name   = assignment.get("name") or assignment.get("study_name", "")
        company      = assignment.get("subject") or assignment.get("company_name", "")
        viewing_time = assignment.get("_raw", assignment).get("viewing_time", 10)
        if isinstance(viewing_time, str):
            viewing_time = int(''.join(filter(str.isdigit, viewing_time)) or 10)

        image_b64 = None
        try:
            resp = requests.get(
                f"{API_BASE}/api/studies/{requests.utils.quote(study_name)}",
                params={"company": company},
                timeout=20
            )
            if resp.ok:
                doc       = resp.json()
                image_b64 = doc.get("image_b64")
        except Exception as ex:
            self._bottom_bar.setText(f"  Warning: could not fetch image — {ex}")

        screen = StudyScreen(image_b64, viewing_time)
        screen.finished.connect(lambda completed, pts, a=assignment:
                                self._on_study_finished(completed, pts, a))
        self._study_screen = screen
        screen.start(self.worker.gaze_updated)

    def _on_study_finished(self, completed: bool, gaze_points: list, assignment: dict):
        if not completed:
            self._bottom_bar.setText(
                f"  Study escaped — you must complete '{assignment.get('name','')}' to record results."
            )
            self._set_nav("Assignments")
            return

        study_name = assignment.get("name") or assignment.get("study_name", "")
        company    = assignment.get("subject") or assignment.get("company_name", "")

        if hasattr(self, 'gaze_map') and gaze_points:
            self.gaze_map._trail = []
            self.gaze_map._gx = gaze_points[-1][0]
            self.gaze_map._gy = gaze_points[-1][1]
            for pt in gaze_points:
                self.gaze_map._trail.append((pt[0], pt[1]))
                if len(self.gaze_map._trail) > 500:
                    self.gaze_map._trail.pop(0)
            self.gaze_map.update()

        self._heatmap_status_dot.setStyleSheet(f"font-size:10px;color:{SUCCESS};")
        self._heatmap_status_lbl.setText(f"Session complete — {len(gaze_points)} pts")
        self._heatmap_status_lbl.setStyleSheet(f"font-size:11px;color:{SUCCESS};")
        self._heatmap_stack.setCurrentIndex(1)

        if gaze_points:
            last = gaze_points[-1]
            if hasattr(self, '_m_gaze_x'):
                self._m_gaze_x.setText(f"{last[0]:.3f}")
                self._m_gaze_y.setText(f"{last[1]:.3f}")

        payload = {
            "study_name":   study_name,
            "company_name": company,
            "gaze_points":  gaze_points,
        }
        try:
            resp = requests.post(f"{API_BASE}/api/studies/session", json=payload, timeout=20)
            if resp.ok:
                self._bottom_bar.setText(
                    f"  Study '{study_name}' complete — {len(gaze_points)} gaze points saved. View in Heatmaps."
                )
            else:
                self._bottom_bar.setText(f"  Study done but failed to save: {resp.status_code}")
        except Exception as ex:
            self._bottom_bar.setText(f"  Study done but could not save results: {ex}")

        self._set_nav("Heatmaps")
        QTimer.singleShot(600, self._refresh_assignments)

    def _page_calibration(self):
        page  = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(40, 30, 40, 40); outer.setSpacing(20)

        h = QLabel("Calibration")
        h.setStyleSheet(f"font-size:20px;font-weight:700;color:{TEXT_DARK};")
        outer.addWidget(h)

        cols = QHBoxLayout(); cols.setSpacing(20)
        left_col = QVBoxLayout(); left_col.setSpacing(16)

        instr_card, instr_lay = make_card(margins=(28, 24, 28, 24), spacing=12)
        instr_title = QLabel("Instructions"); instr_title.setObjectName("CardTitle")
        instr_lay.addWidget(instr_title); instr_lay.addWidget(hdiv())
        for num, text in [
            ("1", "Position yourself ~60cm from the screen."),
            ("2", "A dot will appear at 9 screen positions."),
            ("3", "Follow each dot with your eyes — keep your head still."),
            ("4", "Hold your gaze steady for ~1.5 seconds per point."),
        ]:
            row = QHBoxLayout(); row.setSpacing(10)
            nb  = QLabel(num); nb.setFixedSize(22, 22); nb.setAlignment(Qt.AlignCenter)
            nb.setStyleSheet(f"background:{ACCENT};color:white;border-radius:11px;font-size:11px;font-weight:700;")
            tb  = QLabel(text); tb.setObjectName("CardNote"); tb.setWordWrap(True)
            row.addWidget(nb, 0, Qt.AlignTop); row.addWidget(tb, 1)
            instr_lay.addLayout(row)
        left_col.addWidget(instr_card)

        action_card, action_lay = make_card(margins=(28, 24, 28, 24), spacing=14)
        action_lay.setAlignment(Qt.AlignCenter)

        self.start_btn = QPushButton("Begin Calibration"); self.start_btn.setObjectName("PrimaryBtn")
        self.start_btn.setCursor(Qt.PointingHandCursor); self.start_btn.clicked.connect(self._handle_start)
        self.start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT}; color: white; border: none; border-radius: 3px;
                padding: 14px 40px; font-size: 14px; font-weight: 600; min-width: 180px;
            }}
            QPushButton:hover {{ background-color: {ACCENT_DK}; }}
            QPushButton:pressed {{ background-color: #1e3a5f; }}
            QPushButton:disabled {{ background-color: #aab8cb; color: #dde5ef; }}
        """)
        self.recalib_btn = QPushButton("Recalibrate"); self.recalib_btn.setObjectName("GhostBtn")
        self.recalib_btn.setCursor(Qt.PointingHandCursor); self.recalib_btn.clicked.connect(self._handle_start)
        self.recalib_btn.setVisible(False)
        btn_row = QHBoxLayout(); btn_row.setAlignment(Qt.AlignCenter); btn_row.setSpacing(12)
        btn_row.addWidget(self.start_btn); btn_row.addWidget(self.recalib_btn)
        action_lay.addLayout(btn_row)
        cam_note = QLabel("Make sure your camera is enabled and your face is visible.")
        cam_note.setObjectName("CardNote"); cam_note.setAlignment(Qt.AlignCenter)
        action_lay.addWidget(cam_note)
        left_col.addWidget(action_card)
        left_col.addStretch()
        cols.addLayout(left_col, 1)

        right_col = QVBoxLayout(); right_col.setSpacing(16)
        prog_card, prog_lay = make_card(margins=(28, 24, 28, 24), spacing=14)

        prog_header = QHBoxLayout()
        prog_title  = QLabel("Progress")
        prog_title.setStyleSheet(f"font-size:13px;font-weight:600;color:{TEXT_DARK};")
        prog_header.addWidget(prog_title); prog_header.addStretch()
        self.calib_step_lbl = QLabel("Not started"); self.calib_step_lbl.setObjectName("CardNote")
        prog_header.addWidget(self.calib_step_lbl)
        prog_lay.addLayout(prog_header)

        self.calib_bar = QProgressBar(); self.calib_bar.setRange(0, 21)
        self.calib_bar.setValue(0); self.calib_bar.setTextVisible(False)
        self.calib_bar.setFixedHeight(6); prog_lay.addWidget(self.calib_bar)

        grid_row = QHBoxLayout(); grid_row.setSpacing(20)
        self.point_grid = PointGrid(); grid_row.addWidget(self.point_grid)
        grid_row.addStretch()
        self._calib_status = QLabel("")
        self._calib_status.setObjectName("CardNote"); self._calib_status.setWordWrap(True)
        self._calib_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid_row.addWidget(self._calib_status)
        prog_lay.addLayout(grid_row)
        right_col.addWidget(prog_card)
        right_col.addStretch()
        cols.addLayout(right_col, 1)
        outer.addLayout(cols, 1)
        return page

    def _page_heatmaps(self):
        page  = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(40, 30, 40, 40); outer.setSpacing(20)

        h = QLabel("Heatmaps"); h.setStyleSheet(f"font-size:20px;font-weight:700;color:{TEXT_DARK};")
        outer.addWidget(h)

        card, cl = make_card()
        hdr_row  = QHBoxLayout()
        tl = QLabel("Gaze Map"); tl.setObjectName("CardTitle"); hdr_row.addWidget(tl)
        hdr_row.addStretch()
        self._heatmap_status_dot = QLabel("●")
        self._heatmap_status_dot.setStyleSheet(f"font-size:10px;color:{TEXT_LIGHT};")
        self._heatmap_status_lbl = QLabel("No active session")
        self._heatmap_status_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};")
        hdr_row.addWidget(self._heatmap_status_dot); hdr_row.addSpacing(4)
        hdr_row.addWidget(self._heatmap_status_lbl)
        cl.addLayout(hdr_row)
        cl.addWidget(hdiv())

        from PyQt5.QtWidgets import QStackedWidget as SW
        self._heatmap_stack = SW(); self._heatmap_stack.setStyleSheet(f"background:{CARD_BG};")

        empty_w = QWidget(); empty_w.setStyleSheet(f"background:{CARD_BG};"); empty_w.setFixedHeight(230)
        el = QVBoxLayout(empty_w); el.setAlignment(Qt.AlignCenter); el.setContentsMargins(40, 40, 40, 40)
        eicon = QLabel("👁"); eicon.setStyleSheet("font-size:40px;"); eicon.setAlignment(Qt.AlignCenter); el.addWidget(eicon)
        et = QLabel("No heatmap data yet")
        et.setStyleSheet(f"font-size:15px;font-weight:600;color:{TEXT_DARK};margin-top:10px;")
        et.setAlignment(Qt.AlignCenter); el.addWidget(et)
        es = QLabel("Complete calibration and start a tracking session to see your gaze map here.")
        es.setStyleSheet(f"font-size:12px;color:{TEXT_LIGHT};margin-top:4px;")
        es.setAlignment(Qt.AlignCenter); es.setWordWrap(True); el.addWidget(es)
        go_btn = QPushButton("Go to Calibration"); go_btn.setCursor(Qt.PointingHandCursor)
        go_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent;color:{ACCENT};border:1px solid {ACCENT};
                border-radius:3px;padding:8px 20px;font-size:12px;margin-top:10px; }}
            QPushButton:hover {{ background:#eef2f8; }}
        """)
        go_btn.clicked.connect(lambda: self._set_nav("Calibration"))
        el.addWidget(go_btn, 0, Qt.AlignCenter)
        self._heatmap_stack.addWidget(empty_w)

        live_w  = QWidget(); live_w.setStyleSheet(f"background:{CARD_BG};")
        lw_lay  = QVBoxLayout(live_w); lw_lay.setContentsMargins(0, 0, 0, 0)
        self.gaze_map = GazeMap(); lw_lay.addWidget(self.gaze_map)
        self._heatmap_stack.addWidget(live_w)

        cl.addWidget(self._heatmap_stack)
        cl.addWidget(hdiv())

        metrics_row = QHBoxLayout(); metrics_row.setSpacing(12)
        for label, attr, clr in [
            ("GAZE X", "_m_gaze_x", ACCENT), ("GAZE Y", "_m_gaze_y", ACCENT),
            ("RAW X",  "_m_raw_x",  TEXT_MED), ("RAW Y", "_m_raw_y", TEXT_MED)
        ]:
            mc, ml2 = make_card(margins=(16, 12, 16, 12), spacing=4)
            lb = QLabel(label); lb.setObjectName("MetricLabel"); ml2.addWidget(lb)
            val = QLabel("—"); val.setStyleSheet(f"font-size:22px;font-weight:300;color:{clr};")
            ml2.addWidget(val); metrics_row.addWidget(mc); setattr(self, attr, val)
        cl.addLayout(metrics_row)
        outer.addWidget(card, 1)
        return page

    def _page_camera(self):
        page  = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(40, 30, 40, 40); outer.setSpacing(20)

        h = QLabel("Camera"); h.setStyleSheet(f"font-size:20px;font-weight:700;color:{TEXT_DARK};")
        outer.addWidget(h)

        sel_card, sel_lay = make_card(margins=(24, 20, 24, 20), spacing=14)
        sel_hdr = QHBoxLayout()
        sel_title = QLabel("Select Camera"); sel_title.setObjectName("CardTitle")
        sel_hdr.addWidget(sel_title); sel_hdr.addStretch()

        self._cam_status_dot = QLabel("●")
        self._cam_status_dot.setStyleSheet(f"font-size:10px;color:{TEXT_LIGHT};")
        self._cam_status_lbl = QLabel("No camera selected")
        self._cam_status_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};")
        sel_hdr.addWidget(self._cam_status_dot); sel_hdr.addSpacing(4)
        sel_hdr.addWidget(self._cam_status_lbl)
        sel_lay.addLayout(sel_hdr)
        sel_lay.addWidget(hdiv())

        dropdown_row = QHBoxLayout(); dropdown_row.setSpacing(10)
        self._cam_dropdown = QComboBox()
        self._cam_dropdown.setPlaceholderText("Scanning for cameras…")
        self._cam_dropdown.currentIndexChanged.connect(self._on_camera_selected)
        dropdown_row.addWidget(self._cam_dropdown, 1)

        scan_btn = QPushButton("↻  Scan"); scan_btn.setCursor(Qt.PointingHandCursor)
        scan_btn.setFixedHeight(36)
        scan_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{ACCENT}; border:1px solid {ACCENT};
                border-radius:3px; padding:6px 16px; font-size:12px; }}
            QPushButton:hover {{ background:#eef2f8; }}
        """)
        scan_btn.clicked.connect(self._scan_cameras)
        dropdown_row.addWidget(scan_btn)
        sel_lay.addLayout(dropdown_row)

        info_row = QHBoxLayout(); info_row.setSpacing(24)
        self._cam_index_lbl = self._cam_info_pill("INDEX", "—")
        self._cam_res_lbl   = self._cam_info_pill("RESOLUTION", "—")
        self._cam_fps_lbl   = self._cam_info_pill("FPS", "—")
        for pill in [self._cam_index_lbl, self._cam_res_lbl, self._cam_fps_lbl]:
            info_row.addWidget(pill)
        info_row.addStretch()
        sel_lay.addLayout(info_row)
        outer.addWidget(sel_card)

        feed_card, feed_lay = make_card(margins=(0, 0, 0, 0), spacing=0)
        feed_hdr = QWidget(); feed_hdr.setStyleSheet(f"background:{CARD_BG};")
        fhl = QHBoxLayout(feed_hdr); fhl.setContentsMargins(24, 16, 24, 16)
        fhl_title = QLabel("Live Preview"); fhl_title.setObjectName("CardTitle"); fhl.addWidget(fhl_title)
        fhl.addStretch()
        self._fps_status = QLabel("—  FPS")
        self._fps_status.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};")
        fhl.addWidget(self._fps_status)
        feed_lay.addWidget(feed_hdr)
        feed_lay.addWidget(hdiv())

        self.camera_label = QLabel(); self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumHeight(340)
        self.camera_label.setText("No camera feed")
        self.camera_label.setStyleSheet("background:#111; color:#555; font-size:13px;")
        feed_lay.addWidget(self.camera_label, 1)
        outer.addWidget(feed_card, 1)

        QTimer.singleShot(200, self._scan_cameras)
        return page

    def _cam_info_pill(self, label, value):
        w  = QWidget(); w.setStyleSheet(f"background:#F7F5F2;border-radius:3px;")
        wl = QHBoxLayout(w); wl.setContentsMargins(12, 6, 12, 6); wl.setSpacing(8)
        lb  = QLabel(label); lb.setStyleSheet(f"font-size:10px;color:{TEXT_LIGHT};letter-spacing:1px;")
        val = QLabel(value); val.setStyleSheet(f"font-size:12px;font-weight:600;color:{TEXT_DARK};")
        val.setObjectName(f"pill_{label}")
        wl.addWidget(lb); wl.addWidget(val)
        return w

    def _scan_cameras(self):
        self._cam_dropdown.blockSignals(True)
        self._cam_dropdown.clear()
        self._cam_status_dot.setStyleSheet(f"font-size:10px;color:{WARNING};")
        self._cam_status_lbl.setText("Scanning…")
        self._cam_status_lbl.setStyleSheet(f"font-size:11px;color:{WARNING};")
        QApplication.processEvents()

        found = []
        for i in range(8):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = int(cap.get(cv2.CAP_PROP_FPS))
                    found.append({"index": i, "label": f"Camera {i}", "w": w, "h": h, "fps": fps})
            cap.release()

        if found:
            for cam in found:
                self._cam_dropdown.addItem(f"{cam['label']}  ({cam['w']}×{cam['h']})", userData=cam)
            self._cam_status_dot.setStyleSheet(f"font-size:10px;color:{SUCCESS};")
            self._cam_status_lbl.setText(f"{len(found)} camera{'s' if len(found) != 1 else ''} found")
            self._cam_status_lbl.setStyleSheet(f"font-size:11px;color:{SUCCESS};")
        else:
            self._cam_dropdown.addItem("No cameras detected")
            self._cam_status_dot.setStyleSheet(f"font-size:10px;color:{DANGER};")
            self._cam_status_lbl.setText("No cameras found")
            self._cam_status_lbl.setStyleSheet(f"font-size:11px;color:{DANGER};")

        self._cam_dropdown.blockSignals(False)
        if found:
            self._cam_dropdown.setCurrentIndex(0)
            self._on_camera_selected(0)

    def _on_camera_selected(self, combo_idx):
        cam = self._cam_dropdown.itemData(combo_idx)
        if not cam: return
        idx = cam["index"]

        def set_pill(widget, value):
            widget.findChildren(QLabel)[1].setText(value)

        set_pill(self._cam_index_lbl, str(idx))
        set_pill(self._cam_res_lbl,   f"{cam['w']}×{cam['h']}")
        set_pill(self._cam_fps_lbl,   f"{cam['fps']}")

        if self.worker.isRunning():
            self.worker.switch_camera(idx)
        else:
            self.worker._next_cam_index = idx
            self.worker.start_preview()

    def _page_how_to(self):
        page  = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(40, 30, 40, 40); outer.setSpacing(20)

        h = QLabel("How to use"); h.setStyleSheet(f"font-size:20px;font-weight:700;color:{TEXT_DARK};")
        outer.addWidget(h)

        card, cl = make_card()
        steps = [
            ("1  Select your camera",       "Go to the Camera tab and use the dropdown to select your webcam. Click ↻ Scan if no cameras appear. Verify the live preview shows your face clearly."),
            ("2  Run calibration",           "Go to the Calibration tab and click Begin Calibration. A dot will appear at 9 positions on your screen — follow each dot with your eyes only, keeping your head still. Hold your gaze on each dot for about 1.5 seconds."),
            ("3  Tracking starts automatically", "Once all 9 points are collected, eye tracking begins immediately. The Heatmaps tab will switch from the empty state to a live gaze trail."),
            ("4  Open an assignment",        "Go to the Assignments tab and select an assignment from the list. Click Start to begin the session — the document will be shown for the configured viewing time while your gaze is recorded."),
            ("5  View heatmaps",             "After a session, go to the Heatmaps tab to review the real-time gaze map and coordinates (Gaze X/Y and Raw X/Y values)."),
            ("6  Recalibrate if needed",     "If tracking feels inaccurate, go back to Calibration and click Recalibrate. This resets the current session and runs the 9-point calibration again."),
        ]
        for i, (title, body) in enumerate(steps):
            t = QLabel(title); t.setStyleSheet(f"font-size:13px;font-weight:600;color:{TEXT_DARK};"); cl.addWidget(t)
            b = QLabel(body);  b.setStyleSheet(f"font-size:12px;color:{TEXT_MED};padding-left:2px;")
            b.setWordWrap(True); cl.addWidget(b)
            if i < len(steps) - 1: cl.addWidget(hdiv())
        outer.addWidget(card); outer.addStretch()
        return page

    # ── Nav ──────────────────────────────────────────────────
    _page_map = {"Assignments": 0, "Calibration": 1, "Heatmaps": 2, "Camera": 3, "How to use": 4}

    def _set_nav(self, label):
        self.stack.setCurrentIndex(self._page_map.get(label, 0))
        for k, btn in self._nav_btns.items():
            btn.setProperty("active", "true" if k == label else "false")
            btn.style().unpolish(btn); btn.style().polish(btn)

    # ── Calibration ──────────────────────────────────────────
    def _handle_start(self):
        self._calib_done = False; self._tracking = False
        self.start_btn.setEnabled(False); self.start_btn.setText("Calibrating…")
        self.recalib_btn.setVisible(False)
        self.calib_step_lbl.setText("Starting…"); self.calib_bar.setValue(0)
        self.point_grid.reset(); self._calib_status.setText("")
        self._heatmap_stack.setCurrentIndex(0)
        self._heatmap_status_dot.setStyleSheet(f"font-size:10px;color:{TEXT_LIGHT};")
        self._heatmap_status_lbl.setText("No active session")
        self._heatmap_status_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};")
        self.worker.start_calibration()

    def _on_calib_step(self, idx, px, py):
        if idx < 20:
            self.calib_step_lbl.setText(f"Point {idx + 1} of 20")
            self.calib_bar.setValue(idx)
            self.point_grid.set_active(min(idx, 8))
            self._bottom_bar.setText(f"  Calibrating — point {idx + 1} of 20. Keep eyes on the dot.")
        else:
            self.calib_step_lbl.setText("Offset correction…")
            self.calib_bar.setValue(20)
            self._bottom_bar.setText("  Almost done — look at the centre dot to correct offset.")
        self.overlay.show_point(px, py)

    def _on_calib_done(self):
        self.overlay.hide_overlay(); self.calib_bar.setValue(21)
        self.calib_step_lbl.setText("Complete ✓"); self.point_grid.set_done()
        self.start_btn.setEnabled(True); self.start_btn.setText("Begin Calibration")
        self.recalib_btn.setVisible(True)
        self._calib_done = True; self._tracking = True
        self._calib_status.setText("Calibration complete. Tracking is now active.")
        self._calib_status.setStyleSheet(f"font-size:12px;color:{SUCCESS};")
        self._heatmap_stack.setCurrentIndex(1)
        self._heatmap_status_dot.setStyleSheet(f"font-size:10px;color:{SUCCESS};")
        self._heatmap_status_lbl.setText("Live")
        self._heatmap_status_lbl.setStyleSheet(f"font-size:11px;color:{SUCCESS};")
        self.worker.start_tracking()

        if self._pending_study:
            pending = self._pending_study
            self._pending_study = None
            self._bottom_bar.setText("  Calibration complete — launching study…")
            QTimer.singleShot(300, lambda: self._launch_study_screen(pending))
        else:
            self._bottom_bar.setText("  Tracking active — view gaze data in the Heatmaps tab.")

    # ── Frame / Gaze ─────────────────────────────────────────
    def _on_frame(self, frame):
        self._frame_count += 1
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pix = QPixmap.fromImage(img)
        if hasattr(self, 'camera_label') and self.camera_label.isVisible():
            self.camera_label.setPixmap(
                pix.scaled(self.camera_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _on_gaze(self, gx, gy):
        if hasattr(self, '_m_gaze_x'):
            self._m_gaze_x.setText(f"{gx:.3f}"); self._m_gaze_y.setText(f"{gy:.3f}")
        if hasattr(self, 'gaze_map'): self.gaze_map.update_gaze(gx, gy)

    def _on_raw_gaze(self, rx, ry):
        if hasattr(self, '_m_raw_x'):
            self._m_raw_x.setText(f"{rx:.3f}"); self._m_raw_y.setText(f"{ry:.3f}")

    def _upd_fps(self):
        fps = str(self._frame_count)
        if hasattr(self, '_fps_status'): self._fps_status.setText(f"{fps}  FPS")
        self._frame_count = 0

    def closeEvent(self, e):
        if self._study_screen:
            self._study_screen._tick_timer.stop()
            self._study_screen.hide()
        self.worker.stop(); self.worker.wait(2000); self.overlay.hide(); super().closeEvent(e)


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from PyQt5.QtGui import QPalette
    pal = app.palette()
    pal.setColor(QPalette.Window,          QColor(BG))
    pal.setColor(QPalette.WindowText,      QColor(TEXT_DARK))
    pal.setColor(QPalette.Base,            QColor(CARD_BG))
    pal.setColor(QPalette.AlternateBase,   QColor(BG))
    pal.setColor(QPalette.Button,          QColor(CARD_BG))
    pal.setColor(QPalette.ButtonText,      QColor(TEXT_DARK))
    pal.setColor(QPalette.Highlight,       QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    app.setPalette(pal)
    w = MainWindow(); w.show(); sys.exit(app.exec_())