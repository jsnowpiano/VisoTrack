import sys
import base64
import json
from datetime import datetime

import requests

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QScrollArea,
    QLineEdit, QSpinBox, QFileDialog, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize, QByteArray, QBuffer
from PyQt5.QtGui import (
    QImage, QPixmap, QColor, QPainter, QPen, QBrush, QFont, QIcon
)

API_BASE = "http://127.0.0.1:5000"


try:
    import anthropic as _anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

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
#NavLink {{
    background: transparent; color: {TEXT_MED}; border: none;
    text-align: left; padding: 9px 28px; font-size: 13px;
}}
#NavLink:hover {{ color: {ACCENT}; background: transparent; }}
#NavLink[active="true"] {{ color: {ACCENT}; font-weight: 600; }}

#Card {{
    background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 4px;
}}
#AuthCard {{
    background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 6px;
}}
#CardTitle {{ font-size: 16px; font-weight: 600; color: {TEXT_DARK}; }}
#CardNote  {{ font-size: 12px; color: {TEXT_MED}; }}

#CodeBadge {{
    background: #EEF2F8; border: 1px solid {ACCENT}; border-radius: 4px;
    padding: 10px 18px;
}}

#PrimaryBtn {{
    background-color: {ACCENT}; color: white; border: none; border-radius: 3px;
    padding: 12px 32px; font-size: 13px; font-weight: 600;
}}
#PrimaryBtn:hover    {{ background-color: {ACCENT_DK}; }}
#PrimaryBtn:pressed  {{ background-color: #1e3a5f; }}
#PrimaryBtn:disabled {{ background-color: #aab8cb; color: #dde5ef; }}

#DangerBtn {{
    background-color: {DANGER}; color: white; border: none; border-radius: 3px;
    padding: 8px 20px; font-size: 12px; font-weight: 600;
}}
#DangerBtn:hover {{ background-color: #a93226; }}

#GhostBtn {{
    background: transparent; color: {ACCENT}; border: 1px solid {ACCENT};
    border-radius: 3px; padding: 8px 20px; font-size: 12px;
}}
#GhostBtn:hover {{ background: #eef2f8; }}

QLineEdit, QSpinBox {{
    background: {CARD_BG}; color: {TEXT_DARK}; border: 1px solid {BORDER};
    border-radius: 3px; padding: 8px 12px; font-size: 13px;
}}
QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; }}

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
"""


class ResearcherAuthScreen(QWidget):
    login_success = pyqtSignal(str, str)  # access_code, company_name

    def __init__(self):
        super().__init__()
        self.setStyleSheet(STYLESHEET + f"QWidget {{ background: {BG}; }}")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame(); card.setObjectName("AuthCard")
        card.setFixedWidth(440)
        cl = QVBoxLayout(card); cl.setContentsMargins(44, 40, 44, 40); cl.setSpacing(20)

        logo = QLabel("V")
        logo.setStyleSheet(
            f"color:{ACCENT}; font-size:52px; font-weight:700; font-family:'Georgia',serif;"
        )
        logo.setAlignment(Qt.AlignCenter); cl.addWidget(logo)

        title = QLabel("VisoTrack")
        title.setStyleSheet(f"font-size:18px; font-weight:700; color:{TEXT_DARK};")
        title.setAlignment(Qt.AlignCenter); cl.addWidget(title)

        sub = QLabel("Researcher Portal")
        sub.setStyleSheet(f"font-size:12px; color:{TEXT_LIGHT}; letter-spacing:1px;")
        sub.setAlignment(Qt.AlignCenter); cl.addWidget(sub)

        # Tab row
        tab_row = QHBoxLayout(); tab_row.setSpacing(0)
        self._login_tab = self._tab_btn("Log In",          active=True)
        self._reg_tab   = self._tab_btn("Register Company", active=False)
        self._login_tab.clicked.connect(lambda: self._switch("login"))
        self._reg_tab.clicked.connect(lambda: self._switch("register"))
        tab_row.addWidget(self._login_tab); tab_row.addWidget(self._reg_tab)
        cl.addLayout(tab_row)

        self._form_stack = QStackedWidget()
        self._form_stack.addWidget(self._build_login_form()) 
        self._form_stack.addWidget(self._build_register_form()) 
        cl.addWidget(self._form_stack)

        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet(f"font-size:12px; color:{DANGER};")
        self._err_lbl.setAlignment(Qt.AlignCenter)
        self._err_lbl.setWordWrap(True)
        cl.addWidget(self._err_lbl)

        outer.addWidget(card, 0, Qt.AlignCenter)

    def _tab_btn(self, text, active=False):
        btn = QPushButton(text); btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(34); self._style_tab(btn, active); return btn

    def _style_tab(self, btn, active):
        if active:
            btn.setStyleSheet(f"""
                QPushButton {{ background:{ACCENT}; color:white; border:none;
                    font-size:13px; font-weight:600; border-radius:3px; padding:6px 0; }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{ background:transparent; color:{TEXT_MED}; border:1px solid {BORDER};
                    font-size:13px; border-radius:3px; padding:6px 0; }}
                QPushButton:hover {{ color:{ACCENT}; border-color:{ACCENT}; }}
            """)

    def _switch(self, tab):
        self._err_lbl.setText("")
        if tab == "login":
            self._form_stack.setCurrentIndex(0)
            self._style_tab(self._login_tab, True)
            self._style_tab(self._reg_tab, False)
        else:
            self._form_stack.setCurrentIndex(1)
            self._style_tab(self._login_tab, False)
            self._style_tab(self._reg_tab, True)

    def _fl(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size:10px; font-weight:700; color:{TEXT_LIGHT}; letter-spacing:1px;")
        return lbl

    def _build_login_form(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(10); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self._fl("COMPANY NAME"))
        self._l_name = QLineEdit(); self._l_name.setPlaceholderText("Your company name")
        lay.addWidget(self._l_name)
        lay.addWidget(self._fl("PASSWORD"))
        self._l_pw = QLineEdit(); self._l_pw.setPlaceholderText("••••••••")
        self._l_pw.setEchoMode(QLineEdit.Password)
        lay.addWidget(self._l_pw)
        btn = self._action_btn("Log In"); btn.clicked.connect(self._do_login)
        self._l_name.returnPressed.connect(self._do_login)
        self._l_pw.returnPressed.connect(self._do_login)
        lay.addWidget(btn)
        return w

    def _build_register_form(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(10); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self._fl("COMPANY NAME"))
        self._r_name = QLineEdit(); self._r_name.setPlaceholderText("e.g. Acme Research Lab")
        lay.addWidget(self._r_name)
        lay.addWidget(self._fl("PASSWORD"))
        self._r_pw = QLineEdit(); self._r_pw.setPlaceholderText("••••••••")
        self._r_pw.setEchoMode(QLineEdit.Password)
        lay.addWidget(self._r_pw)
        note = QLabel("A unique 6-character access code will be generated for your participants.")
        note.setStyleSheet(f"font-size:11px; color:{TEXT_LIGHT};")
        note.setWordWrap(True); lay.addWidget(note)
        btn = self._action_btn("Register & Get Code"); btn.clicked.connect(self._do_register)
        lay.addWidget(btn)
        return w

    def _action_btn(self, label):
        btn = QPushButton(label); btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(42)
        btn.setStyleSheet(f"""
            QPushButton {{ background:{ACCENT}; color:white; border:none; border-radius:3px;
                font-size:14px; font-weight:600; }}
            QPushButton:hover {{ background:{ACCENT_DK}; }}
            QPushButton:pressed {{ background:#1e3a5f; }}
        """)
        return btn

    def _do_login(self):
        name = self._l_name.text().strip()
        pw   = self._l_pw.text()
        if not name or not pw:
            self._err_lbl.setText("Company name and password are required."); return
        self._err_lbl.setText("")
        try:
            resp = requests.post(f"{API_BASE}/api/companies/login",
                                 json={"name": name, "password": pw}, timeout=10)
            data = resp.json()
            if resp.ok:
                self.login_success.emit(data["access_code"], data["name"])
            else:
                self._err_lbl.setText(data.get("error", "Login failed."))
        except requests.exceptions.ConnectionError:
            self._err_lbl.setText("Cannot reach server. Is Flask running?")
        except Exception as e:
            self._err_lbl.setText(str(e))

    def _do_register(self):
        name = self._r_name.text().strip()
        pw   = self._r_pw.text()
        if not name or not pw:
            self._err_lbl.setText("Company name and password are required."); return
        self._err_lbl.setText("")
        try:
            resp = requests.post(f"{API_BASE}/api/companies/register",
                                 json={"name": name, "password": pw}, timeout=10)
            data = resp.json()
            if resp.ok:
                code = data["access_code"]
                msg = QMessageBox(self)
                msg.setWindowTitle("Company Registered!")
                msg.setText(
                    f"<b>Your participant access code is:</b><br><br>"
                    f"<span style='font-size:28px; letter-spacing:6px; color:{ACCENT};'><b>{code}</b></span><br><br>"
                    f"Share this code with participants so they can register and see your studies.<br>"
                    f"<i>You can always view it in the dashboard after logging in.</i>"
                )
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
                self.login_success.emit(code, name)
            else:
                self._err_lbl.setText(data.get("error", "Registration failed."))
        except requests.exceptions.ConnectionError:
            self._err_lbl.setText("Cannot reach server. Is Flask running?")
        except Exception as e:
            self._err_lbl.setText(str(e))


def make_card(margins=(28, 24, 28, 24), spacing=14):
    card = QFrame(); card.setObjectName("Card")
    lay  = QVBoxLayout(card)
    lay.setContentsMargins(*margins); lay.setSpacing(spacing)
    return card, lay

def hdiv():
    d = QFrame(); d.setFrameShape(QFrame.HLine)
    d.setStyleSheet(f"color:{BORDER};"); return d

def field_label(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(f"font-size:11px;font-weight:700;color:{TEXT_LIGHT};letter-spacing:1px;")
    return lbl

def section_title(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(f"font-size:20px;font-weight:700;color:{TEXT_DARK};")
    return lbl

class ImageDropZone(QLabel):
    image_selected = pyqtSignal(str)
    FIXED_HEIGHT = 200

    def __init__(self):
        super().__init__()
        self._path = None; self._pixmap_orig = None
        self.setAcceptDrops(True); self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(self.FIXED_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor); self._set_empty()

    def _set_empty(self):
        self.clear(); self._pixmap_orig = None
        self.setStyleSheet(f"""
            QLabel {{ background:#F7F5F2; border:2px dashed {BORDER}; border-radius:4px;
                color:{TEXT_LIGHT}; font-size:13px; }}
            QLabel:hover {{ border-color:{ACCENT}; color:{ACCENT}; }}
        """)
        self.setText("Click or drag a PNG / JPG here")

    def _display(self):
        if self._pixmap_orig and not self._pixmap_orig.isNull():
            scaled = self._pixmap_orig.scaled(self.width(), self.FIXED_HEIGHT,
                                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.setPixmap(scaled)

    def load_path(self, path):
        if not path: return
        pix = QPixmap(path)
        if pix.isNull(): return
        self._path = path; self._pixmap_orig = pix
        self.setStyleSheet(f"QLabel {{ background:#F7F5F2; border:2px solid {ACCENT}; border-radius:4px; }}")
        self._display(); self.image_selected.emit(path)

    def load_b64(self, b64_str):
        try:
            data = base64.b64decode(b64_str); pix = QPixmap(); pix.loadFromData(data)
            if not pix.isNull():
                self._path = None; self._pixmap_orig = pix
                self.setStyleSheet(f"background:#F7F5F2;border:1px solid {BORDER};border-radius:4px;")
                self._display()
        except Exception:
            pass

    def mousePressEvent(self, e):
        path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg)")
        if path: self.load_path(path)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.png', '.jpg', '.jpeg')):
                self.load_path(path); break

    def get_path(self): return self._path

    def resizeEvent(self, e):
        super().resizeEvent(e); self._display()


class GazeHeatmap(QLabel):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(240); self.setAlignment(Qt.AlignCenter)
        self._gaze_points = []; self._base_pixmap = None

    def set_image_b64(self, b64_str):
        try:
            data = base64.b64decode(b64_str); pix = QPixmap(); pix.loadFromData(data)
            if not pix.isNull(): self._base_pixmap = pix
        except Exception:
            pass
        self.update()

    def set_gaze_points(self, points):
        self._gaze_points = points; self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if self._base_pixmap:
            scaled = self._base_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x_off = (w - scaled.width()) // 2; y_off = (h - scaled.height()) // 2
            p.drawPixmap(x_off, y_off, scaled)
            draw_w, draw_h = scaled.width(), scaled.height(); ox, oy = x_off, y_off
        else:
            p.fillRect(self.rect(), QColor("#F7F5F2"))
            draw_w, draw_h = w, h; ox, oy = 0, 0
        for (nx, ny) in self._gaze_points:
            px = int(ox + nx * draw_w); py = int(oy + ny * draw_h)
            for radius, alpha in [(14, 18), (8, 35), (4, 60)]:
                p.setBrush(QColor(74, 111, 165, alpha)); p.setPen(Qt.NoPen)
                p.drawEllipse(px - radius, py - radius, radius * 2, radius * 2)
        if not self._gaze_points:
            p.setPen(QColor(TEXT_LIGHT)); p.setFont(QFont("Helvetica Neue", 12))
            p.drawText(self.rect(), Qt.AlignCenter, "No gaze data recorded yet")
        p.end()

class AIInsightsWorker(QThread):
    chunk_ready = pyqtSignal(str)
    finished_ok = pyqtSignal()
    error       = pyqtSignal(str)

    def __init__(self, api_key: str, image_png_b64: str,
                 study_name: str, n_points: int, n_sessions: int,
                 avg_x: str, avg_y: str):
        super().__init__()
        self._key      = api_key
        self._img      = image_png_b64
        self._study    = study_name
        self._n_points = n_points
        self._n_sess   = n_sessions
        self._avg_x    = avg_x
        self._avg_y    = avg_y

    def run(self):
        if not ANTHROPIC_AVAILABLE:
            self.error.emit(
                "anthropic package not installed — run: pip install anthropic"
            )
            return
        try:
            client = _anthropic.Anthropic(api_key=self._key)
            prompt = (
                f"You are an expert UX researcher analysing an eye-tracking gaze heatmap.\n\n"
                f"Study: '{self._study}'\n"
                f"Sessions: {self._n_sess}  |  Total gaze points: {self._n_points}  |  "
                f"Average gaze position: ({self._avg_x}, {self._avg_y}) in normalised 0–1 "
                f"coordinates where (0,0) is top-left.\n\n"
                f"The attached image shows the study stimulus with a translucent blue heatmap "
                f"overlay. Denser/brighter blue areas indicate more attention.\n\n"
                f"Please provide:\n"
                f"1. **Attention hotspots** — which areas attracted the most gaze and why.\n"
                f"2. **Neglected areas** — important regions that were largely ignored.\n"
                f"3. **Viewing pattern** — any scan path or reading order visible in the data.\n"
                f"4. **Design recommendations** — 2–3 concrete, actionable suggestions based "
                f"on the gaze data.\n"
                f"5. **Summary** — one sentence takeaway for stakeholders.\n\n"
                f"Be concise and specific. Use plain language suitable for a non-technical client."
            )
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/png",
                                "data":       self._img,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            ) as stream:
                for text in stream.text_stream:
                    self.chunk_ready.emit(text)
            self.finished_ok.emit()
        except Exception as ex:
            self.error.emit(str(ex))


class ResearcherDashboard(QWidget):
    def __init__(self, access_code: str, company_name: str, on_logout=None):
        super().__init__()
        self._access_code   = access_code
        self._company_name  = company_name
        self._on_logout_cb  = on_logout
        self._studies       = []
        self._current_study = None
        self._ai_key        = ""
        self._ai_worker     = None

    
        import os
        self._ai_key = os.environ.get("ANTHROPIC_API_KEY", "")

        self._build_ui()
        self.setStyleSheet(STYLESHEET)
        self._set_nav("Studies")
        QTimer.singleShot(300, self._load_studies)

    def _build_ui(self):
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        right = QWidget(); rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        self.stack = QStackedWidget(); self.stack.setStyleSheet(f"background:{BG};")
        rl.addWidget(self.stack, 1)
        self.stack.addWidget(self._page_studies())   # 0
        self.stack.addWidget(self._page_create())    # 1
        self.stack.addWidget(self._page_detail())    # 2

        self._status_bar = QLabel("  Ready")
        self._status_bar.setObjectName("BottomBar")
        rl.addWidget(self._status_bar)
        root.addWidget(right, 1)

    def _build_sidebar(self):
        sb = QWidget(); sb.setObjectName("Sidebar")
        sl = QVBoxLayout(sb); sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(0)

        hdr = QWidget(); hdr.setObjectName("SidebarHeader"); hdr.setFixedHeight(110)
        hdr.setStyleSheet(f"background:{HEADER_BG};")
        hl = QVBoxLayout(hdr); hl.setAlignment(Qt.AlignCenter)
        logo = QLabel("V")
        logo.setStyleSheet(f"color:{ACCENT};font-size:52px;font-weight:700;font-family:'Georgia',serif;")
        logo.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("RESEARCHER")
        subtitle.setStyleSheet(f"color:#6A8AB5;font-size:9px;letter-spacing:3px;font-weight:600;")
        subtitle.setAlignment(Qt.AlignCenter)
        hl.addWidget(logo); hl.addWidget(subtitle)
        sl.addWidget(hdr)


        co_lbl = QLabel(self._company_name)
        co_lbl.setAlignment(Qt.AlignCenter)
        co_lbl.setStyleSheet(f"font-size:12px; font-weight:600; color:{TEXT_DARK}; padding:10px 16px 2px 16px;")
        co_lbl.setWordWrap(True)
        sl.addWidget(co_lbl)

        code_badge = QWidget()
        code_badge.setObjectName("CodeBadge")
        code_badge.setStyleSheet(
            f"background:#EEF2F8; border:1px solid {ACCENT}; border-radius:4px; margin:4px 20px;"
        )
        cbl = QVBoxLayout(code_badge); cbl.setContentsMargins(10, 6, 10, 6); cbl.setSpacing(2)
        badge_title = QLabel("PARTICIPANT CODE")
        badge_title.setStyleSheet(f"font-size:9px; font-weight:700; color:{TEXT_LIGHT}; letter-spacing:1px;")
        badge_title.setAlignment(Qt.AlignCenter)
        badge_code = QLabel(self._access_code)
        badge_code.setStyleSheet(
            f"font-size:20px; font-weight:700; color:{ACCENT}; letter-spacing:4px;"
        )
        badge_code.setAlignment(Qt.AlignCenter)
        badge_hint = QLabel("Share with participants")
        badge_hint.setStyleSheet(f"font-size:9px; color:{TEXT_LIGHT};")
        badge_hint.setAlignment(Qt.AlignCenter)
        cbl.addWidget(badge_title); cbl.addWidget(badge_code); cbl.addWidget(badge_hint)
        sl.addWidget(code_badge)
        sl.addSpacing(10)

        self._nav_btns = {}
        for label, icon in [("Studies", "📋"), ("Create Study", "＋")]:
            btn = QPushButton(f"  {icon}  {label}"); btn.setObjectName("NavLink")
            btn.setCursor(Qt.PointingHandCursor); btn.setFixedHeight(36)
            btn.clicked.connect(lambda chk, l=label: self._set_nav(l))
            sl.addWidget(btn); self._nav_btns[label] = btn

        sl.addStretch()

        # Logout
        logout_btn = QPushButton("Log Out")
        logout_btn.setCursor(Qt.PointingHandCursor)
        logout_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{DANGER}; border:none;
                font-size:12px; padding:10px 28px; text-align:left; }}
            QPushButton:hover {{ color:#a93226; }}
        """)
        logout_btn.clicked.connect(self._logout)
        sl.addWidget(logout_btn)
        sl.addSpacing(8)
        return sb

    def _logout(self):
        if self._on_logout_cb:
            self._on_logout_cb()


    def _page_studies(self):
        page = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(40, 30, 40, 40); outer.setSpacing(20)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(section_title("Studies")); hdr_row.addStretch()
        self._study_count_lbl = QLabel("0 studies")
        self._study_count_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_LIGHT};")
        hdr_row.addWidget(self._study_count_lbl); hdr_row.addSpacing(16)

        refresh_btn = QPushButton("↻  Refresh"); refresh_btn.setObjectName("GhostBtn")
        refresh_btn.setCursor(Qt.PointingHandCursor); refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self._load_studies)
        hdr_row.addWidget(refresh_btn)

        new_btn = QPushButton("＋  New Study"); new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setFixedHeight(32)
        new_btn.setStyleSheet(f"""
            QPushButton {{ background:{ACCENT};color:white;border:none;border-radius:3px;
                padding:6px 18px;font-size:12px;font-weight:600; }}
            QPushButton:hover {{ background:{ACCENT_DK}; }}
        """)
        new_btn.clicked.connect(lambda: self._set_nav("Create Study"))
        hdr_row.addWidget(new_btn)
        outer.addLayout(hdr_row)

        self._gallery_scroll = QScrollArea()
        self._gallery_scroll.setWidgetResizable(True); self._gallery_scroll.setFrameShape(QFrame.NoFrame)
        self._gallery_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._gallery_scroll.setStyleSheet(f"""
            QScrollArea {{ background:{BG}; border:none; }}
            QScrollBar:horizontal {{ background:{BG}; height:6px; border-radius:3px; }}
            QScrollBar::handle:horizontal {{ background:#C8C4BF; border-radius:3px; min-width:40px; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
        """)

        self._gallery_container = QWidget(); self._gallery_container.setStyleSheet(f"background:{BG};")
        self._gallery_lay = QHBoxLayout(self._gallery_container)
        self._gallery_lay.setContentsMargins(0, 8, 0, 16); self._gallery_lay.setSpacing(16)
        self._gallery_lay.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._gallery_lay.addWidget(self._empty_state_gallery())

        self._gallery_scroll.setWidget(self._gallery_container)
        self._gallery_scroll.setFixedHeight(280)
        outer.addWidget(self._gallery_scroll)
        outer.addStretch()
        return page

    def _empty_state_gallery(self):
        w = QWidget(); w.setStyleSheet(f"background:{BG};"); w.setFixedSize(500, 240)
        el = QVBoxLayout(w); el.setAlignment(Qt.AlignCenter)
        icon = QLabel("🔬"); icon.setStyleSheet("font-size:32px;"); icon.setAlignment(Qt.AlignCenter); el.addWidget(icon)
        et = QLabel("No studies yet"); et.setStyleSheet(f"font-size:14px;font-weight:600;color:{TEXT_DARK};margin-top:10px;")
        et.setAlignment(Qt.AlignCenter); el.addWidget(et)
        es = QLabel("Click  ＋ New Study  to get started."); es.setStyleSheet(f"font-size:12px;color:{TEXT_LIGHT};margin-top:4px;")
        es.setAlignment(Qt.AlignCenter); el.addWidget(es)
        return w

    def _make_study_card(self, study: dict) -> QWidget:
        CARD_W, CARD_H = 200, 248
        card = QFrame(); card.setObjectName("Card"); card.setFixedSize(CARD_W, CARD_H)
        card.setCursor(Qt.PointingHandCursor)
        cl = QVBoxLayout(card); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

        img_lbl = QLabel(); img_lbl.setFixedSize(CARD_W, 130); img_lbl.setAlignment(Qt.AlignCenter)
        img_lbl.setStyleSheet(f"background:#F0EDE8;border-radius:4px 4px 0 0;")
        b64 = study.get("image_b64")
        if b64:
            try:
                data = base64.b64decode(b64); pix = QPixmap(); pix.loadFromData(data)
                if not pix.isNull():
                    img_lbl.setPixmap(pix.scaled(CARD_W, 130, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
                    img_lbl.setStyleSheet("border-radius:4px 4px 0 0; background:#000;")
            except Exception:
                pass
        else:
            img_lbl.setText("🖼"); img_lbl.setStyleSheet(f"background:#F0EDE8;border-radius:4px 4px 0 0;font-size:32px;")
        cl.addWidget(img_lbl)

        dv = QFrame(); dv.setFrameShape(QFrame.HLine); dv.setStyleSheet(f"color:{BORDER};"); cl.addWidget(dv)

        info = QWidget(); info.setStyleSheet(f"background:{CARD_BG};border-radius:0 0 4px 4px;")
        il = QVBoxLayout(info); il.setContentsMargins(14, 10, 14, 10); il.setSpacing(3)

        name_lbl = QLabel(study.get("study_name", "Untitled"))
        name_lbl.setStyleSheet(f"font-size:13px;font-weight:600;color:{TEXT_DARK};background:transparent;")
        fm = name_lbl.fontMetrics()
        name_lbl.setText(fm.elidedText(study.get("study_name","Untitled"), Qt.ElideRight, CARD_W - 28))
        il.addWidget(name_lbl)

        co_lbl = QLabel(study.get("company_name", "—"))
        co_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};background:transparent;")
        il.addWidget(co_lbl)

        il.addSpacing(4)
        row = QHBoxLayout(); row.setSpacing(6)
        vt_lbl = QLabel(f"⏱ {study.get('viewing_time','—')}s")
        vt_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_MED};background:transparent;")
        row.addWidget(vt_lbl); row.addStretch()

        del_btn = QPushButton("✕"); del_btn.setFixedSize(22, 22); del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent;color:{DANGER};border:none;font-size:12px;font-weight:700; }}
            QPushButton:hover {{ color:#a93226; }}
        """)
        del_btn.setToolTip("Delete study")
        del_btn.clicked.connect(lambda: self._confirm_delete(study))
        row.addWidget(del_btn)
        il.addLayout(row)

        cl.addWidget(info, 1)
        card.mousePressEvent = lambda e: self._open_detail(study)
        return card


    def _page_create(self):
        page = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        top_bar = QWidget()
        top_bar.setStyleSheet(f"QWidget {{ background:{CARD_BG}; border-bottom:1px solid {BORDER}; }}")
        top_bar.setFixedHeight(58)
        tbl = QHBoxLayout(top_bar); tbl.setContentsMargins(40, 0, 40, 0); tbl.setSpacing(12)
        page_title = QLabel("Create Study")
        page_title.setStyleSheet(f"font-size:18px;font-weight:700;color:{TEXT_DARK};background:transparent;")
        tbl.addWidget(page_title); tbl.addStretch()

        cancel_top = QPushButton("Cancel"); cancel_top.setCursor(Qt.PointingHandCursor); cancel_top.setFixedHeight(34)
        cancel_top.setStyleSheet(f"""
            QPushButton {{ background:transparent;color:{TEXT_MED};border:1px solid {BORDER};
                border-radius:3px;padding:6px 20px;font-size:12px; }}
            QPushButton:hover {{ border-color:{ACCENT};color:{ACCENT}; }}
        """)
        cancel_top.clicked.connect(lambda: self._set_nav("Studies"))

        save_top = QPushButton("💾  Save Study"); save_top.setCursor(Qt.PointingHandCursor); save_top.setFixedHeight(34)
        save_top.setStyleSheet(f"""
            QPushButton {{ background:{ACCENT};color:white;border:none;border-radius:3px;
                padding:6px 22px;font-size:13px;font-weight:700; }}
            QPushButton:hover {{ background:{ACCENT_DK}; }}
        """)
        save_top.clicked.connect(self._save_study)
        tbl.addWidget(cancel_top); tbl.addWidget(save_top)
        outer.addWidget(top_bar)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background:{BG};")
        inner = QWidget(); inner.setStyleSheet(f"background:{BG};")
        il = QVBoxLayout(inner); il.setContentsMargins(40, 24, 40, 40); il.setSpacing(20)

        det_card, det_lay = make_card()
        det_lay.addWidget(QLabel("Study Details") if False else self._ch("Study Details"))
        det_lay.addWidget(field_label("STUDY NAME"))
        self._inp_name = QLineEdit(); self._inp_name.setPlaceholderText("e.g. Resume Attention Study")
        det_lay.addWidget(self._inp_name)
        self._inp_company = QLineEdit()
        self._inp_company.setText(self._company_name)
        self._inp_company.hide()
        det_lay.addWidget(field_label("VIEWING TIME (seconds)"))
        time_row = QHBoxLayout(); time_row.setSpacing(10)
        self._inp_time = QSpinBox(); self._inp_time.setRange(1, 300); self._inp_time.setValue(10)
        self._inp_time.setSuffix("  seconds"); self._inp_time.setFixedWidth(160)
        time_row.addWidget(self._inp_time); time_row.addStretch()
        det_lay.addLayout(time_row)
        il.addWidget(det_card)

        img_card, img_lay = make_card()
        img_lay.addWidget(self._ch("Study Image")); img_lay.addWidget(hdiv())
        self._drop_zone = ImageDropZone(); img_lay.addWidget(self._drop_zone)
        img_note = QLabel("PNG or JPG. Encoded and stored in the database.")
        img_note.setObjectName("CardNote"); img_note.setWordWrap(True); img_lay.addWidget(img_note)
        clear_img_btn = QPushButton("Clear Image"); clear_img_btn.setObjectName("GhostBtn")
        clear_img_btn.setFixedWidth(120); clear_img_btn.setCursor(Qt.PointingHandCursor)
        clear_img_btn.clicked.connect(self._clear_image)
        img_lay.addWidget(clear_img_btn, 0, Qt.AlignLeft)
        il.addWidget(img_card); il.addStretch()
        scroll.setWidget(inner); outer.addWidget(scroll, 1)
        return page

    def _ch(self, text):
        lbl = QLabel(text); lbl.setObjectName("CardTitle"); return lbl

    def _clear_image(self):
        self._drop_zone._path = None; self._drop_zone.clear(); self._drop_zone._set_empty()


    def _page_detail(self):
        page = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(40, 30, 40, 40); outer.setSpacing(20)

        hdr_row = QHBoxLayout()
        back_btn = QPushButton("← Back to Studies"); back_btn.setObjectName("GhostBtn")
        back_btn.setCursor(Qt.PointingHandCursor); back_btn.setFixedHeight(30)
        back_btn.clicked.connect(lambda: self._set_nav("Studies"))
        hdr_row.addWidget(back_btn); hdr_row.addStretch()

        self._detail_refresh_btn = QPushButton("↻  Refresh"); self._detail_refresh_btn.setCursor(Qt.PointingHandCursor)
        self._detail_refresh_btn.setFixedHeight(30)
        self._detail_refresh_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent;color:{ACCENT};border:1px solid {ACCENT};
                border-radius:3px;padding:4px 14px;font-size:12px; }}
            QPushButton:hover {{ background:#eef2f8; }}
        """)
        self._detail_refresh_btn.clicked.connect(
            lambda: self._open_detail(self._current_study) if self._current_study else None)
        hdr_row.addWidget(self._detail_refresh_btn)
        outer.addLayout(hdr_row)

        self._detail_title = QLabel("Study Detail")
        self._detail_title.setStyleSheet(f"font-size:20px;font-weight:700;color:{TEXT_DARK};")
        outer.addWidget(self._detail_title)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background:{BG};")
        inner = QWidget(); inner.setStyleSheet(f"background:{BG};")
        il = QVBoxLayout(inner); il.setContentsMargins(0, 0, 0, 0); il.setSpacing(20)

        meta_card, meta_lay = make_card()
        meta_lay.addWidget(self._ch("Study Information")); meta_lay.addWidget(hdiv())
        meta_grid = QHBoxLayout(); meta_grid.setSpacing(40)
        self._detail_fields = {}
        for key, label in [("study_name","STUDY NAME"),("company_name","COMPANY"),
                            ("viewing_time","VIEWING TIME"),("created_at","CREATED")]:
            col = QVBoxLayout(); col.setSpacing(4)
            fl = QLabel(label); fl.setStyleSheet(f"font-size:10px;font-weight:700;color:{TEXT_LIGHT};letter-spacing:1px;")
            vl = QLabel("—"); vl.setStyleSheet(f"font-size:14px;color:{TEXT_DARK};font-weight:600;"); vl.setWordWrap(True)
            col.addWidget(fl); col.addWidget(vl); meta_grid.addLayout(col); self._detail_fields[key] = vl
        meta_grid.addStretch(); meta_lay.addLayout(meta_grid)
        il.addWidget(meta_card)

        img_card, img_lay = make_card()
        img_lay.addWidget(self._ch("Study Image")); img_lay.addWidget(hdiv())
        self._detail_image = ImageDropZone(); self._detail_image.setMinimumHeight(220)
        self._detail_image.mousePressEvent = lambda e: None; self._detail_image.setCursor(Qt.ArrowCursor)
        img_lay.addWidget(self._detail_image)
        il.addWidget(img_card)

        hm_card, hm_lay = make_card()
        hm_hdr = QHBoxLayout(); hm_hdr.addWidget(self._ch("Gaze Heatmap")); hm_hdr.addStretch()
        self._hm_session_lbl = QLabel("No session data")
        self._hm_session_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};"); hm_hdr.addWidget(self._hm_session_lbl)
        hm_hdr.addSpacing(12)
        self._dl_btn = QPushButton("⬇  Download"); self._dl_btn.setCursor(Qt.PointingHandCursor); self._dl_btn.setFixedHeight(28)
        self._dl_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent;color:{ACCENT};border:1px solid {ACCENT};
                border-radius:3px;padding:4px 14px;font-size:11px; }}
            QPushButton:hover {{ background:#eef2f8; }}
        """)
        self._dl_btn.clicked.connect(self._download_heatmap); hm_hdr.addWidget(self._dl_btn)
        hm_lay.addLayout(hm_hdr); hm_lay.addWidget(hdiv())
        self._heatmap = GazeHeatmap(); hm_lay.addWidget(self._heatmap)

        stats_row = QHBoxLayout(); stats_row.setSpacing(12)
        for attr, label, color in [
            ("_stat_points","GAZE POINTS",ACCENT), ("_stat_avg_x","AVG GAZE X",ACCENT),
            ("_stat_avg_y","AVG GAZE Y",ACCENT),   ("_stat_sessions","SESSIONS",TEXT_MED),
        ]:
            mc, ml = make_card(margins=(16,12,16,12), spacing=4)
            lb = QLabel(label); lb.setStyleSheet(f"font-size:10px;color:{TEXT_LIGHT};letter-spacing:1px;")
            vl = QLabel("—"); vl.setStyleSheet(f"font-size:22px;font-weight:300;color:{color};")
            ml.addWidget(lb); ml.addWidget(vl); stats_row.addWidget(mc); setattr(self, attr, vl)
        hm_lay.addLayout(stats_row)
        il.addWidget(hm_card)


        ai_card, ai_lay = make_card()
        ai_hdr = QHBoxLayout()
        ai_hdr.addWidget(self._ch("AI Insights")); ai_hdr.addStretch()
        ai_badge = QLabel("Powered by Claude")
        ai_badge.setStyleSheet(
            f"background:#EEF2F8;color:{ACCENT};border-radius:10px;"
            f"padding:3px 10px;font-size:10px;font-weight:600;"
        )
        ai_hdr.addWidget(ai_badge)
        ai_lay.addLayout(ai_hdr)
        ai_lay.addWidget(hdiv())


        key_row = QHBoxLayout(); key_row.setSpacing(8)
        key_lbl = QLabel("ANTHROPIC API KEY")
        key_lbl.setStyleSheet(f"font-size:11px;font-weight:700;color:{TEXT_LIGHT};letter-spacing:1px;")
        key_row.addWidget(key_lbl)
        self._ai_key_input = QLineEdit()
        self._ai_key_input.setPlaceholderText("sk-ant-…  (never stored, only used for this session)")
        self._ai_key_input.setEchoMode(QLineEdit.Password)
        self._ai_key_input.textChanged.connect(lambda t: setattr(self, '_ai_key', t.strip()))
        if self._ai_key:
            self._ai_key_input.setText(self._ai_key)
        key_row.addWidget(self._ai_key_input, 1)
        show_btn = QPushButton("👁")
        show_btn.setFixedSize(32, 32); show_btn.setCursor(Qt.PointingHandCursor)
        show_btn.setCheckable(True)
        show_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent;border:1px solid {BORDER};border-radius:3px;font-size:13px; }}
            QPushButton:checked {{ border-color:{ACCENT}; }}
        """)
        show_btn.toggled.connect(
            lambda on: self._ai_key_input.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password
            )
        )
        key_row.addWidget(show_btn)
        ai_lay.addLayout(key_row)

        key_hint = QLabel(
            'Get your key at <a href="https://console.anthropic.com/settings/keys" '
            f'style="color:{ACCENT};">console.anthropic.com</a>. '
            'Run <code>pip install anthropic</code> if not already installed.'
        )
        key_hint.setOpenExternalLinks(True)
        key_hint.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};")
        key_hint.setWordWrap(True)
        ai_lay.addWidget(key_hint)

        # Analyse button
        self._ai_btn = QPushButton("✦  Analyse Heatmap with AI")
        self._ai_btn.setCursor(Qt.PointingHandCursor)
        self._ai_btn.setStyleSheet(f"""
            QPushButton {{ background:{ACCENT};color:white;border:none;border-radius:3px;
                padding:10px 24px;font-size:13px;font-weight:600; }}
            QPushButton:hover {{ background:{ACCENT_DK}; }}
            QPushButton:disabled {{ background:#aab8cb;color:#dde5ef; }}
        """)
        self._ai_btn.clicked.connect(self._run_ai_insights)
        ai_lay.addWidget(self._ai_btn, 0, Qt.AlignLeft)


        self._ai_output = QLabel("")
        self._ai_output.setWordWrap(True)
        self._ai_output.setTextFormat(Qt.RichText)
        self._ai_output.setStyleSheet(
            f"font-size:13px;color:{TEXT_DARK};line-height:1.6;"
            f"background:#FAFAF8;border:1px solid {BORDER};"
            f"border-radius:3px;padding:16px;"
        )
        self._ai_output.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._ai_output.setMinimumHeight(80)
        self._ai_output.hide()
        ai_lay.addWidget(self._ai_output)

        il.addWidget(ai_card)
        il.addStretch()
        scroll.setWidget(inner); outer.addWidget(scroll, 1)
        return page


    _page_map = {"Studies": 0, "Create Study": 1, "Detail": 2}

    def _set_nav(self, label):
        self.stack.setCurrentIndex(self._page_map.get(label, 0))
        for k, btn in self._nav_btns.items():
            btn.setProperty("active", "true" if k == label else "false")
            btn.style().unpolish(btn); btn.style().polish(btn)


    def _load_studies(self):
        self._status("Loading studies…", WARNING)
        try:
            resp = requests.get(
                f"{API_BASE}/api/studies",
                params={"company_code": self._access_code},
                timeout=15,
            )
            resp.raise_for_status()
            studies = resp.json()
            if isinstance(studies, dict) and "error" in studies:
                raise RuntimeError(studies["error"])
            self._render_studies(studies)
            self._status(f"  Loaded {len(studies)} study/studies.", SUCCESS)
        except requests.exceptions.ConnectionError:
            self._status("  Server offline.", DANGER)
            self._render_studies([])
        except Exception as ex:
            self._status(f"  Error: {ex}", DANGER)
            self._render_studies([])

    def _render_studies(self, studies):
        self._studies = studies
        count = len(studies)
        self._study_count_lbl.setText(f"{count} stud{'ies' if count != 1 else 'y'}")
        while self._gallery_lay.count() > 0:
            item = self._gallery_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if count == 0:
            self._gallery_lay.addWidget(self._empty_state_gallery())
        else:
            for study in studies:
                self._gallery_lay.addWidget(self._make_study_card(study))
            self._gallery_lay.addStretch()

    def _save_study(self):
        name    = self._inp_name.text().strip()
        company = self._inp_company.text().strip()
        secs    = self._inp_time.value()
        if not name:
            self._status("  Study name is required.", DANGER); return
        if not company:
            self._status("  Company / organisation is required.", DANGER); return

        image_b64 = None
        path = self._drop_zone.get_path()
        if path:
            try:
                with open(path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception as ex:
                self._status(f"  Could not read image: {ex}", DANGER); return

        doc = {
            "study_name":    name,
            "company_name":  company,
            "viewing_time":  secs,
            "image_b64":     image_b64,
            "created_at":    datetime.utcnow().isoformat(),
            "gaze_sessions": [],
            "company_code":  self._access_code,
        }

        try:
            resp = requests.post(f"{API_BASE}/api/studies", json=doc, timeout=15)
            resp.raise_for_status()
            self._status(f"  Study saved.", SUCCESS)
            self._inp_name.clear(); self._inp_company.clear()
            self._inp_time.setValue(10); self._clear_image()
            self._set_nav("Studies")
            QTimer.singleShot(200, self._load_studies)
        except requests.exceptions.ConnectionError:
            self._status("  Server offline.", DANGER)
        except Exception as ex:
            self._status(f"  Save failed: {ex}", DANGER)

    def _open_detail(self, study: dict):
        self._current_study = study
        self._detail_title.setText(study.get("study_name", "Study Detail"))
        self.stack.setCurrentIndex(2)
        self._status("  Loading study details…", WARNING)

        try:
            resp = requests.get(
                f"{API_BASE}/api/studies/{requests.utils.quote(study.get('study_name',''))}",
                params={"company": study.get("company_name",""), "company_code": self._access_code},
                timeout=15,
            )
            if resp.ok:
                full = resp.json()
                self._current_study = full
            else:
                full = study
        except Exception as ex:
            self._status(f"  Could not load full study: {ex}", DANGER)
            full = study

        self._detail_fields["study_name"].setText(full.get("study_name", "—"))
        self._detail_fields["company_name"].setText(full.get("company_name", "—"))
        vt = full.get("viewing_time","—")
        self._detail_fields["viewing_time"].setText(f"{vt}s" if isinstance(vt, int) else str(vt))
        created = full.get("created_at","")
        self._detail_fields["created_at"].setText(created[:10] if created else "—")

        b64 = full.get("image_b64")
        if b64:
            self._detail_image.load_b64(b64)
        else:
            self._detail_image.clear(); self._detail_image._set_empty()

        sessions = full.get("gaze_sessions", [])
        TARGET_PER_SESSION = 50
        averaged_points = []
        for s in [s for s in sessions if s.get("gaze_points")]:
            pts = s.get("gaze_points", []); n = len(pts)
            if n <= TARGET_PER_SESSION:
                averaged_points.extend(pts)
            else:
                step = n / TARGET_PER_SESSION
                averaged_points.extend([pts[int(i * step)] for i in range(TARGET_PER_SESSION)])

        all_points = [p for s in sessions for p in s.get("gaze_points", [])]
        if b64:
            self._heatmap.set_image_b64(b64)
        else:
            self._heatmap._base_pixmap = None
        self._heatmap.set_gaze_points([(p[0], p[1]) for p in averaged_points])

        n = len(all_points)
        self._stat_points.setText(str(n)); self._stat_sessions.setText(str(len(sessions)))
        if n > 0:
            self._stat_avg_x.setText(f"{sum(p[0] for p in all_points)/n:.3f}")
            self._stat_avg_y.setText(f"{sum(p[1] for p in all_points)/n:.3f}")
        else:
            self._stat_avg_x.setText("—"); self._stat_avg_y.setText("—")

        self._hm_session_lbl.setText(f"{len(sessions)} session{'s' if len(sessions)!=1 else ''}")
        self._status(f"  Loaded — {len(sessions)} session(s), {n} total gaze points.", SUCCESS)


    def _run_ai_insights(self):
        if not self._ai_key:
            self._ai_output.setText(
                f'<span style="color:{DANGER};">Please enter your Anthropic API key above.</span>'
            )
            self._ai_output.show(); return

        if not ANTHROPIC_AVAILABLE:
            self._ai_output.setText(
                f'<span style="color:{DANGER};">The <code>anthropic</code> package is not installed.<br>'
                f'Run: <code>pip install anthropic</code> then restart.</span>'
            )
            self._ai_output.show(); return


        pixmap = self._heatmap.grab()
        buf = QByteArray()
        buf_io = QBuffer(buf)
        buf_io.open(QBuffer.WriteOnly)
        pixmap.save(buf_io, "PNG")
        buf_io.close()
        import base64 as _b64
        img_b64 = _b64.b64encode(bytes(buf)).decode()

        study  = self._current_study or {}
        n_pts  = self._stat_points.text()
        n_sess = self._stat_sessions.text()
        avg_x  = self._stat_avg_x.text()
        avg_y  = self._stat_avg_y.text()

        self._ai_btn.setEnabled(False)
        self._ai_btn.setText("Analysing…")
        self._ai_output.setText('<span style="color:#999;">Sending heatmap to Claude…</span>')
        self._ai_output.show()
        self._ai_raw = ""

        self._ai_worker = AIInsightsWorker(
            api_key    = self._ai_key,
            image_png_b64 = img_b64,
            study_name = study.get("study_name", "—"),
            n_points   = int(n_pts) if n_pts.isdigit() else 0,
            n_sessions = int(n_sess) if n_sess.isdigit() else 0,
            avg_x      = avg_x,
            avg_y      = avg_y,
        )
        self._ai_worker.chunk_ready.connect(self._on_ai_chunk)
        self._ai_worker.finished_ok.connect(self._on_ai_done)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.start()

    def _on_ai_chunk(self, text: str):
        self._ai_raw += text

        import re
        html = self._ai_raw

        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)

        html = re.sub(r'(?m)^(\d+)\.\s+', r'<br><b>\1.</b> ', html)

        html = html.replace('\n', '<br>')
        self._ai_output.setText(html)

    def _on_ai_done(self):
        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("✦  Analyse Heatmap with AI")
        self._status("  AI insights generated.", SUCCESS)

    def _on_ai_error(self, msg: str):
        self._ai_output.setText(
            f'<span style="color:{DANGER};"><b>Error:</b> {msg}</span>'
        )
        self._ai_btn.setEnabled(True)
        self._ai_btn.setText("✦  Analyse Heatmap with AI")
        self._status(f"  AI error: {msg}", DANGER)


    def _download_heatmap(self):
        study_name   = self._current_study.get("study_name","heatmap") if self._current_study else "heatmap"
        default_name = f"{study_name.replace(' ','_')}_heatmap.png"
        path, _ = QFileDialog.getSaveFileName(self, "Save Heatmap", default_name, "PNG Image (*.png)")
        if not path: return
        pix = self._heatmap.grab()
        if pix.save(path, "PNG"):
            self._status(f"  Heatmap saved to {path}", SUCCESS)
        else:
            self._status("  Failed to save heatmap.", DANGER)

    def _confirm_delete(self, study: dict):
        name = study.get("study_name","this study")
        reply = QMessageBox.question(
            self, "Delete Study",
            f"Are you sure you want to delete \"{name}\"? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel
        )
        if reply == QMessageBox.Yes:
            self._delete_study(study)

    def _delete_study(self, study: dict):
        try:
            resp = requests.delete(
                f"{API_BASE}/api/studies/{requests.utils.quote(study.get('study_name',''))}",
                json={"company_name": study.get("company_name",""), "company_code": self._access_code},
                timeout=15,
            )
            if resp.ok:
                self._status(f"  Deleted \"{study.get('study_name')}\".", SUCCESS)
                QTimer.singleShot(200, self._load_studies)
            else:
                self._status(f"  Delete failed: {resp.json().get('error','')}", DANGER)
        except requests.exceptions.ConnectionError:
            self._status("  Server offline.", DANGER)
        except Exception as ex:
            self._status(f"  Delete failed: {ex}", DANGER)

    def _status(self, msg, color=None):
        self._status_bar.setText(msg)
        c = color or TEXT_LIGHT
        self._status_bar.setStyleSheet(
            f"background:{SIDEBAR_BG};border-top:1px solid {BORDER};"
            f"padding:6px 20px;min-height:32px;max-height:32px;font-size:11px;color:{c};"
        )
        if color:
            QTimer.singleShot(4000, lambda: self._status("  Ready"))

class AppShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VisoTrack — Researcher")
        self.showMaximized()

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._auth = ResearcherAuthScreen()
        self._auth.login_success.connect(self._on_login)
        self._stack.addWidget(self._auth)   

        self._dashboard = None             

    def _on_login(self, access_code: str, company_name: str):
        if self._dashboard is not None:
            self._stack.removeWidget(self._dashboard)
            self._dashboard.deleteLater()


        self._dashboard = ResearcherDashboard(
            access_code, company_name, on_logout=self.go_to_auth
        )
        self._stack.addWidget(self._dashboard)
        self._stack.setCurrentIndex(1)
        self.setWindowTitle(f"VisoTrack — {company_name}")

    def go_to_auth(self):
        self._stack.setCurrentIndex(0)
        self.setWindowTitle("VisoTrack — Researcher")
        self._auth._l_name.clear()
        self._auth._l_pw.clear()
        self._auth._err_lbl.setText("")



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

    shell = AppShell()
    sys.exit(app.exec_())