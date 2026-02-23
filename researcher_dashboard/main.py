import sys
import base64
import json
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QScrollArea,
    QLineEdit, QSpinBox, QFileDialog, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt5.QtGui import (
    QImage, QPixmap, QColor, QPainter, QPen, QBrush, QFont, QIcon
)

# ── Try to import DB connection (graceful fallback if path differs) ──
try:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
    from storage.connection import StudyDatabaseConnection
    DB_AVAILABLE = True
except Exception as e:
    DB_AVAILABLE = False
    print(f"[WARN] Could not connect to DB: {e}")

# ─────────────────────────────────────────────────────────────
#  Design tokens  (matches participant client exactly)
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
#CardNote  {{ font-size: 12px; color: {TEXT_MED}; }}

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
#TagPill {{
    background: #EEF2F8; color: {ACCENT}; border-radius: 10px;
    padding: 3px 10px; font-size: 11px; font-weight: 600;
}}
"""


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────
#  Clickable image drop-zone
# ─────────────────────────────────────────────────────────────
class ImageDropZone(QLabel):
    image_selected = pyqtSignal(str)

    FIXED_HEIGHT = 200

    def __init__(self):
        super().__init__()
        self._path         = None
        self._pixmap_orig  = None
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(self.FIXED_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._set_empty()

    def _set_empty(self):
        self.clear()
        self._pixmap_orig = None
        self.setStyleSheet(f"""
            QLabel {{
                background: #F7F5F2;
                border: 2px dashed {BORDER};
                border-radius: 4px;
                color: {TEXT_LIGHT};
                font-size: 13px;
            }}
            QLabel:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
        """)
        self.setText("Click or drag a PNG / JPG here")

    def _display(self):
        if self._pixmap_orig and not self._pixmap_orig.isNull():
            scaled = self._pixmap_orig.scaled(
                self.width(), self.FIXED_HEIGHT,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.setPixmap(scaled)

    def load_path(self, path):
        if not path: return
        pix = QPixmap(path)
        if pix.isNull(): return
        self._path        = path
        self._pixmap_orig = pix
        self.setStyleSheet(f"""
            QLabel {{
                background: #F7F5F2;
                border: 2px solid {ACCENT};
                border-radius: 4px;
            }}
        """)
        self._display()
        self.image_selected.emit(path)

    def load_b64(self, b64_str):
        try:
            data = base64.b64decode(b64_str)
            pix  = QPixmap()
            pix.loadFromData(data)
            if not pix.isNull():
                self._path        = None
                self._pixmap_orig = pix
                self.setStyleSheet(
                    f"background:#F7F5F2;border:1px solid {BORDER};border-radius:4px;"
                )
                self._display()
        except Exception:
            pass

    def mousePressEvent(self, e):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg)"
        )
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
        super().resizeEvent(e)
        self._display()


# ─────────────────────────────────────────────────────────────
#  Gaze heatmap widget
# ─────────────────────────────────────────────────────────────
class GazeHeatmap(QLabel):
    """Overlays a translucent heatmap on top of the study image."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(240)
        self.setAlignment(Qt.AlignCenter)
        self._gaze_points = []
        self._base_pixmap = None

    def set_image_b64(self, b64_str):
        try:
            data = base64.b64decode(b64_str)
            pix  = QPixmap(); pix.loadFromData(data)
            if not pix.isNull(): self._base_pixmap = pix
        except Exception:
            pass
        self.update()

    def set_gaze_points(self, points):
        self._gaze_points = points
        self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background / base image
        if self._base_pixmap:
            scaled = self._base_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x_off  = (w - scaled.width())  // 2
            y_off  = (h - scaled.height()) // 2
            p.drawPixmap(x_off, y_off, scaled)
            draw_w, draw_h = scaled.width(), scaled.height()
            ox, oy = x_off, y_off
        else:
            p.fillRect(self.rect(), QColor("#F7F5F2"))
            draw_w, draw_h = w, h
            ox, oy = 0, 0

        # ── Heatmap blobs — reduced radii for precision ──────────
        for (nx, ny) in self._gaze_points:
            px = int(ox + nx * draw_w)
            py = int(oy + ny * draw_h)
            for radius, alpha in [(14, 18), (8, 35), (4, 60)]:
                p.setBrush(QColor(74, 111, 165, alpha))
                p.setPen(Qt.NoPen)
                p.drawEllipse(px - radius, py - radius, radius * 2, radius * 2)

        # Empty state hint
        if not self._gaze_points:
            p.setPen(QColor(TEXT_LIGHT))
            p.setFont(QFont("Helvetica Neue", 12))
            p.drawText(self.rect(), Qt.AlignCenter, "No gaze data recorded yet")

        p.end()


# ─────────────────────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────────────────────
class ResearcherDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VisoTrack — Researcher Dashboard")
        self.resize(1100, 720); self.setMinimumSize(880, 580)
        self._studies = []
        self._current_study = None

        self._build_ui()
        self.setStyleSheet(STYLESHEET)
        self._set_nav("Studies")

        QTimer.singleShot(300, self._load_studies_from_db)

    # ── Build ────────────────────────────────────────────────
    def _build_ui(self):
        root_w = QWidget(); self.setCentralWidget(root_w)
        root = QHBoxLayout(root_w)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        right = QWidget(); rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{BG};")
        rl.addWidget(self.stack, 1)

        self.stack.addWidget(self._page_studies())       # 0
        self.stack.addWidget(self._page_create())        # 1
        self.stack.addWidget(self._page_detail())        # 2

        self._status_bar = QLabel("  Ready")
        self._status_bar.setObjectName("BottomBar")
        rl.addWidget(self._status_bar)

        root.addWidget(right, 1)

    # ── Sidebar ──────────────────────────────────────────────
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
        sl.addSpacing(16)

        self._nav_btns = {}
        for label, icon in [("Studies", "📋"), ("Create Study", "＋")]:
            btn = QPushButton(f"  {icon}  {label}"); btn.setObjectName("NavLink")
            btn.setCursor(Qt.PointingHandCursor); btn.setFixedHeight(36)
            btn.clicked.connect(lambda chk, l=label: self._set_nav(l))
            sl.addWidget(btn); self._nav_btns[label] = btn

        self._sidebar_study_btns = []
        sl.addStretch()

        db_row = QWidget(); db_row.setStyleSheet(f"background:{SIDEBAR_BG};")
        dl = QHBoxLayout(db_row); dl.setContentsMargins(24, 12, 24, 16); dl.setSpacing(6)
        self._db_dot = QLabel("●")
        dot_color = SUCCESS if DB_AVAILABLE else DANGER
        self._db_dot.setStyleSheet(f"font-size:9px;color:{dot_color};")
        self._db_lbl = QLabel("DB Connected" if DB_AVAILABLE else "DB Offline")
        self._db_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};")
        dl.addWidget(self._db_dot); dl.addWidget(self._db_lbl); dl.addStretch()
        sl.addWidget(db_row)
        return sb

    # ── Page: Studies gallery ────────────────────────────────
    def _page_studies(self):
        page = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(40, 30, 40, 40); outer.setSpacing(20)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(section_title("Studies")); hdr_row.addStretch()

        self._study_count_lbl = QLabel("0 studies")
        self._study_count_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_LIGHT};")
        hdr_row.addWidget(self._study_count_lbl)
        hdr_row.addSpacing(16)

        refresh_btn = QPushButton("↻  Refresh"); refresh_btn.setObjectName("GhostBtn")
        refresh_btn.setCursor(Qt.PointingHandCursor); refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self._load_studies_from_db)
        hdr_row.addWidget(refresh_btn)

        new_btn = QPushButton("＋  New Study")
        new_btn.setCursor(Qt.PointingHandCursor); new_btn.setFixedHeight(32)
        new_btn.setStyleSheet(f"""
            QPushButton {{ background:{ACCENT};color:white;border:none;border-radius:3px;
                padding:6px 18px;font-size:12px;font-weight:600; }}
            QPushButton:hover {{ background:{ACCENT_DK}; }}
        """)
        new_btn.clicked.connect(lambda: self._set_nav("Create Study"))
        hdr_row.addWidget(new_btn)
        outer.addLayout(hdr_row)

        self._gallery_scroll = QScrollArea()
        self._gallery_scroll.setWidgetResizable(True)
        self._gallery_scroll.setFrameShape(QFrame.NoFrame)
        self._gallery_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._gallery_scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG}; border: none; }}
            QScrollBar:horizontal {{
                background: {BG}; height: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:horizontal {{ background: #C8C4BF; border-radius: 3px; min-width: 40px; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

        self._gallery_container = QWidget()
        self._gallery_container.setStyleSheet(f"background:{BG};")
        self._gallery_lay = QHBoxLayout(self._gallery_container)
        self._gallery_lay.setContentsMargins(0, 8, 0, 16)
        self._gallery_lay.setSpacing(16)
        self._gallery_lay.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self._gallery_empty = self._empty_state_gallery()
        self._gallery_lay.addWidget(self._gallery_empty)

        self._gallery_scroll.setWidget(self._gallery_container)
        self._gallery_scroll.setFixedHeight(280)
        outer.addWidget(self._gallery_scroll)
        outer.addStretch()
        return page

    def _empty_state(self, message="No studies yet", sub="Create your first study using the button above."):
        w = QWidget(); w.setStyleSheet(f"background:{CARD_BG};")
        el = QVBoxLayout(w); el.setAlignment(Qt.AlignCenter); el.setContentsMargins(40, 60, 40, 60)
        icon = QLabel("🔬"); icon.setStyleSheet("font-size:36px;"); icon.setAlignment(Qt.AlignCenter)
        el.addWidget(icon)
        et = QLabel(message)
        et.setStyleSheet(f"font-size:15px;font-weight:600;color:{TEXT_DARK};margin-top:12px;")
        et.setAlignment(Qt.AlignCenter); el.addWidget(et)
        es = QLabel(sub)
        es.setStyleSheet(f"font-size:12px;color:{TEXT_LIGHT};margin-top:4px;")
        es.setAlignment(Qt.AlignCenter); es.setWordWrap(True); el.addWidget(es)
        return w

    def _empty_state_gallery(self):
        w = QWidget(); w.setStyleSheet(f"background:{BG};")
        w.setFixedSize(500, 240)
        el = QVBoxLayout(w); el.setAlignment(Qt.AlignCenter)
        icon = QLabel("🔬"); icon.setStyleSheet("font-size:32px;"); icon.setAlignment(Qt.AlignCenter)
        el.addWidget(icon)
        et = QLabel("No studies yet")
        et.setStyleSheet(f"font-size:14px;font-weight:600;color:{TEXT_DARK};margin-top:10px;")
        et.setAlignment(Qt.AlignCenter); el.addWidget(et)
        es = QLabel("Click  ＋ New Study  to get started.")
        es.setStyleSheet(f"font-size:12px;color:{TEXT_LIGHT};margin-top:4px;")
        es.setAlignment(Qt.AlignCenter); el.addWidget(es)
        return w

    def _make_study_card(self, study: dict) -> QWidget:
        CARD_W, CARD_H = 200, 248

        card = QFrame(); card.setObjectName("Card")
        card.setFixedSize(CARD_W, CARD_H)
        card.setCursor(Qt.PointingHandCursor)
        cl = QVBoxLayout(card); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

        img_lbl = QLabel(); img_lbl.setFixedSize(CARD_W, 130)
        img_lbl.setAlignment(Qt.AlignCenter)
        img_lbl.setStyleSheet(f"background:#F0EDE8;border-radius:4px 4px 0 0;")

        b64 = study.get("image_b64")
        if b64:
            try:
                data = base64.b64decode(b64)
                pix  = QPixmap(); pix.loadFromData(data)
                if not pix.isNull():
                    img_lbl.setPixmap(
                        pix.scaled(CARD_W, 130, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    )
                    img_lbl.setStyleSheet("border-radius:4px 4px 0 0; background:#000;")
            except Exception:
                pass
        else:
            img_lbl.setText("🖼")
            img_lbl.setStyleSheet(f"background:#F0EDE8;border-radius:4px 4px 0 0;font-size:32px;")
        cl.addWidget(img_lbl)

        dv = QFrame(); dv.setFrameShape(QFrame.HLine)
        dv.setStyleSheet(f"color:{BORDER};"); cl.addWidget(dv)

        info = QWidget(); info.setStyleSheet(f"background:{CARD_BG};border-radius:0 0 4px 4px;")
        il = QVBoxLayout(info); il.setContentsMargins(14, 10, 14, 10); il.setSpacing(3)

        name_lbl = QLabel(study.get("study_name", "Untitled"))
        name_lbl.setStyleSheet(f"font-size:13px;font-weight:600;color:{TEXT_DARK};background:transparent;")
        fm = name_lbl.fontMetrics()
        name_lbl.setText(fm.elidedText(study.get("study_name","Untitled"), Qt.ElideRight, CARD_W - 28))
        il.addWidget(name_lbl)

        co_lbl = QLabel(study.get("company_name", "—"))
        co_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};background:transparent;")
        co_lbl.setText(co_lbl.fontMetrics().elidedText(study.get("company_name","—"), Qt.ElideRight, CARD_W - 28))
        il.addWidget(co_lbl)

        il.addSpacing(4)
        row = QHBoxLayout(); row.setSpacing(6)
        vt_lbl = QLabel(f"⏱ {study.get('viewing_time','—')}s")
        vt_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_MED};background:transparent;")
        row.addWidget(vt_lbl); row.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22); del_btn.setCursor(Qt.PointingHandCursor)
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

    # ── Page: Create study ───────────────────────────────────
    def _page_create(self):
        page = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        top_bar = QWidget()
        top_bar.setStyleSheet(f"QWidget {{ background: {CARD_BG}; border-bottom: 1px solid {BORDER}; }}")
        top_bar.setFixedHeight(58)
        tbl = QHBoxLayout(top_bar); tbl.setContentsMargins(40, 0, 40, 0); tbl.setSpacing(12)

        page_title = QLabel("Create Study")
        page_title.setStyleSheet(f"font-size:18px;font-weight:700;color:{TEXT_DARK};background:transparent;")
        tbl.addWidget(page_title); tbl.addStretch()

        cancel_top = QPushButton("Cancel"); cancel_top.setObjectName("GhostBtn")
        cancel_top.setCursor(Qt.PointingHandCursor); cancel_top.setFixedHeight(34)
        cancel_top.setStyleSheet(f"""
            QPushButton {{ background:transparent;color:{TEXT_MED};border:1px solid {BORDER};
                border-radius:3px;padding:6px 20px;font-size:12px; }}
            QPushButton:hover {{ border-color:{ACCENT};color:{ACCENT}; }}
        """)
        cancel_top.clicked.connect(lambda: self._set_nav("Studies"))

        save_top = QPushButton("💾  Save Study")
        save_top.setCursor(Qt.PointingHandCursor); save_top.setFixedHeight(34)
        save_top.setStyleSheet(f"""
            QPushButton {{ background:{ACCENT};color:white;border:none;border-radius:3px;
                padding:6px 22px;font-size:13px;font-weight:700; }}
            QPushButton:hover {{ background:{ACCENT_DK}; }}
            QPushButton:pressed {{ background:#1e3a5f; }}
        """)
        save_top.clicked.connect(self._save_study)

        tbl.addWidget(cancel_top); tbl.addWidget(save_top)
        outer.addWidget(top_bar)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background:{BG};")
        inner = QWidget(); inner.setStyleSheet(f"background:{BG};")
        il = QVBoxLayout(inner); il.setContentsMargins(40, 24, 40, 40); il.setSpacing(20)

        det_card, det_lay = make_card()
        det_lay.addWidget(self._card_header("Study Details"))

        det_lay.addWidget(field_label("STUDY NAME"))
        self._inp_name = QLineEdit(); self._inp_name.setPlaceholderText("e.g. Resume Attention Study")
        det_lay.addWidget(self._inp_name)

        det_lay.addWidget(field_label("COMPANY / ORGANISATION"))
        self._inp_company = QLineEdit(); self._inp_company.setPlaceholderText("e.g. Acme Corp")
        det_lay.addWidget(self._inp_company)

        det_lay.addWidget(field_label("VIEWING TIME (seconds)"))
        time_row = QHBoxLayout(); time_row.setSpacing(10)
        self._inp_time = QSpinBox()
        self._inp_time.setRange(1, 300); self._inp_time.setValue(10)
        self._inp_time.setSuffix("  seconds"); self._inp_time.setFixedWidth(160)
        time_row.addWidget(self._inp_time); time_row.addStretch()
        det_lay.addLayout(time_row)
        il.addWidget(det_card)

        img_card, img_lay = make_card()
        img_lay.addWidget(self._card_header("Study Image"))
        img_lay.addWidget(hdiv())

        self._drop_zone = ImageDropZone()
        img_lay.addWidget(self._drop_zone)

        img_note = QLabel("PNG or JPG, any size. The image will be encoded and stored in the database.")
        img_note.setObjectName("CardNote"); img_note.setWordWrap(True)
        img_lay.addWidget(img_note)

        clear_img_btn = QPushButton("Clear Image"); clear_img_btn.setObjectName("GhostBtn")
        clear_img_btn.setFixedWidth(120); clear_img_btn.setCursor(Qt.PointingHandCursor)
        clear_img_btn.clicked.connect(self._clear_image)
        img_lay.addWidget(clear_img_btn, 0, Qt.AlignLeft)
        il.addWidget(img_card)
        il.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return page

    def _card_header(self, text):
        lbl = QLabel(text); lbl.setObjectName("CardTitle"); return lbl

    def _clear_image(self):
        self._drop_zone._path = None
        self._drop_zone.clear()
        self._drop_zone._set_empty()

    # ── Page: Study detail ───────────────────────────────────
    def _page_detail(self):
        page = QWidget(); page.setStyleSheet(f"background:{BG};")
        outer = QVBoxLayout(page); outer.setContentsMargins(40, 30, 40, 40); outer.setSpacing(20)

        hdr_row = QHBoxLayout()
        back_btn = QPushButton("← Back to Studies"); back_btn.setObjectName("GhostBtn")
        back_btn.setCursor(Qt.PointingHandCursor); back_btn.setFixedHeight(30)
        back_btn.clicked.connect(lambda: self._set_nav("Studies"))
        hdr_row.addWidget(back_btn); hdr_row.addStretch()

        self._detail_refresh_btn = QPushButton("↻  Refresh")
        self._detail_refresh_btn.setCursor(Qt.PointingHandCursor)
        self._detail_refresh_btn.setFixedHeight(30)
        self._detail_refresh_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent;color:{ACCENT};border:1px solid {ACCENT};
                border-radius:3px;padding:4px 14px;font-size:12px; }}
            QPushButton:hover {{ background:#eef2f8; }}
        """)
        self._detail_refresh_btn.clicked.connect(
            lambda: self._open_detail(self._current_study) if self._current_study else None
        )
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
        meta_lay.addWidget(self._card_header("Study Information"))
        meta_lay.addWidget(hdiv())

        meta_grid = QHBoxLayout(); meta_grid.setSpacing(40)
        self._detail_fields = {}
        for key, label in [
            ("study_name",   "STUDY NAME"),
            ("company_name", "COMPANY"),
            ("viewing_time", "VIEWING TIME"),
            ("created_at",   "CREATED"),
        ]:
            col = QVBoxLayout(); col.setSpacing(4)
            fl = QLabel(label); fl.setStyleSheet(f"font-size:10px;font-weight:700;color:{TEXT_LIGHT};letter-spacing:1px;")
            vl = QLabel("—"); vl.setStyleSheet(f"font-size:14px;color:{TEXT_DARK};font-weight:600;")
            vl.setWordWrap(True)
            col.addWidget(fl); col.addWidget(vl)
            meta_grid.addLayout(col)
            self._detail_fields[key] = vl
        meta_grid.addStretch()
        meta_lay.addLayout(meta_grid)
        il.addWidget(meta_card)

        img_card, img_lay = make_card()
        img_lay.addWidget(self._card_header("Study Image"))
        img_lay.addWidget(hdiv())
        self._detail_image = ImageDropZone()
        self._detail_image.setMinimumHeight(220)
        self._detail_image.mousePressEvent = lambda e: None
        self._detail_image.setCursor(Qt.ArrowCursor)
        img_lay.addWidget(self._detail_image)
        il.addWidget(img_card)

        hm_card, hm_lay = make_card()
        hm_hdr = QHBoxLayout()
        hm_hdr.addWidget(self._card_header("Gaze Heatmap"))
        hm_hdr.addStretch()
        self._hm_session_lbl = QLabel("No session data")
        self._hm_session_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_LIGHT};")
        hm_hdr.addWidget(self._hm_session_lbl)
        hm_hdr.addSpacing(12)
        self._dl_btn = QPushButton("⬇  Download")
        self._dl_btn.setCursor(Qt.PointingHandCursor)
        self._dl_btn.setFixedHeight(28)
        self._dl_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent;color:{ACCENT};border:1px solid {ACCENT};
                border-radius:3px;padding:4px 14px;font-size:11px; }}
            QPushButton:hover {{ background:#eef2f8; }}
        """)
        self._dl_btn.clicked.connect(self._download_heatmap)
        hm_hdr.addWidget(self._dl_btn)
        hm_lay.addLayout(hm_hdr)
        hm_lay.addWidget(hdiv())
        self._heatmap = GazeHeatmap()
        hm_lay.addWidget(self._heatmap)

        stats_row = QHBoxLayout(); stats_row.setSpacing(12)
        for attr, label, color in [
            ("_stat_points",    "GAZE POINTS",   ACCENT),
            ("_stat_avg_x",     "AVG GAZE X",    ACCENT),
            ("_stat_avg_y",     "AVG GAZE Y",    ACCENT),
            ("_stat_sessions",  "SESSIONS",      TEXT_MED),
        ]:
            mc, ml = make_card(margins=(16, 12, 16, 12), spacing=4)
            lb = QLabel(label); lb.setStyleSheet(f"font-size:10px;color:{TEXT_LIGHT};letter-spacing:1px;")
            vl = QLabel("—"); vl.setStyleSheet(f"font-size:22px;font-weight:300;color:{color};")
            ml.addWidget(lb); ml.addWidget(vl)
            stats_row.addWidget(mc); setattr(self, attr, vl)
        hm_lay.addLayout(stats_row)
        il.addWidget(hm_card)
        il.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return page

    # ── Nav ──────────────────────────────────────────────────
    _page_map = {"Studies": 0, "Create Study": 1, "Detail": 2}

    def _set_nav(self, label):
        idx = self._page_map.get(label, 0)
        self.stack.setCurrentIndex(idx)
        for k, btn in self._nav_btns.items():
            btn.setProperty("active", "true" if k == label else "false")
            btn.style().unpolish(btn); btn.style().polish(btn)

    # ── DB operations ────────────────────────────────────────
    def _load_studies_from_db(self):
        self._status("Loading studies…", WARNING)
        if not DB_AVAILABLE:
            self._status("DB not available — showing no data.", DANGER)
            self._render_studies([])
            return
        try:
            db = StudyDatabaseConnection()
            studies = db.get_all_studies()
            self._render_studies(studies)
            self._status(f"  Loaded {len(studies)} study/studies.", SUCCESS)
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
            self._gallery_empty = self._empty_state_gallery()
            self._gallery_lay.addWidget(self._gallery_empty)
        else:
            for study in studies:
                card = self._make_study_card(study)
                self._gallery_lay.addWidget(card)
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
        }

        if not DB_AVAILABLE:
            self._status("  DB offline — study not saved.", DANGER); return

        try:
            db  = StudyDatabaseConnection()
            _id = db.add_study(doc)
            self._status(f"  Study saved (id: {_id}).", SUCCESS)
            self._inp_name.clear(); self._inp_company.clear()
            self._inp_time.setValue(10); self._clear_image()
            self._set_nav("Studies")
            QTimer.singleShot(200, self._load_studies_from_db)
        except Exception as ex:
            self._status(f"  Save failed: {ex}", DANGER)

    def _open_detail(self, study: dict):
        self._current_study = study
        self._detail_title.setText(study.get("study_name", "Study Detail"))
        self.stack.setCurrentIndex(2)
        self._status("  Loading study details…", WARNING)

        full = study
        if DB_AVAILABLE:
            try:
                db = StudyDatabaseConnection()
                fetched = db.get_study(
                    study.get("study_name", ""),
                    study.get("company_name", "")
                )
                if fetched:
                    full = fetched
            except Exception as ex:
                self._status(f"  Could not load full study: {ex}", DANGER)

        self._current_study = full

        self._detail_fields["study_name"].setText(full.get("study_name", "—"))
        self._detail_fields["company_name"].setText(full.get("company_name", "—"))
        vt = full.get("viewing_time", "—")
        self._detail_fields["viewing_time"].setText(f"{vt}s" if isinstance(vt, int) else str(vt))
        created = full.get("created_at", "")
        self._detail_fields["created_at"].setText(created[:10] if created else "—")

        b64 = full.get("image_b64")
        if b64:
            self._detail_image.load_b64(b64)
        else:
            self._detail_image.clear()
            self._detail_image._set_empty()

        sessions   = full.get("gaze_sessions", [])
        all_points = []
        for s in sessions:
            pts = s.get("gaze_points", [])
            all_points.extend(pts)

        if b64:
            self._heatmap.set_image_b64(b64)
        else:
            self._heatmap._base_pixmap = None

        self._heatmap.set_gaze_points([(p[0], p[1]) for p in all_points])

        n = len(all_points)
        self._stat_points.setText(str(n))
        self._stat_sessions.setText(str(len(sessions)))
        if n > 0:
            avg_x = sum(p[0] for p in all_points) / n
            avg_y = sum(p[1] for p in all_points) / n
            self._stat_avg_x.setText(f"{avg_x:.3f}")
            self._stat_avg_y.setText(f"{avg_y:.3f}")
        else:
            self._stat_avg_x.setText("—")
            self._stat_avg_y.setText("—")

        session_count = len(sessions)
        self._hm_session_lbl.setText(
            f"{session_count} session{'s' if session_count != 1 else ''}"
        )
        self._status(
            f"  Loaded — {session_count} session(s), {n} total gaze points.", SUCCESS
        )


    def _download_heatmap(self):
        """Render the GazeHeatmap widget to a PNG and save it."""
        study_name = self._current_study.get("study_name", "heatmap") if self._current_study else "heatmap"
        default_name = f"{study_name.replace(' ', '_')}_heatmap.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Heatmap", default_name, "PNG Image (*.png)"
        )
        if not path:
            return
        # Grab the widget as a pixmap at its current rendered size
        pix = self._heatmap.grab()
        if pix.save(path, "PNG"):
            self._status(f"  Heatmap saved to {path}", SUCCESS)
        else:
            self._status("  Failed to save heatmap.", DANGER)

    def _confirm_delete(self, study: dict):
        name = study.get("study_name", "this study")
        reply = QMessageBox.question(
            self, "Delete Study",
            f"Are you sure you want to delete \"{name}\"? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        if reply == QMessageBox.Yes:
            self._delete_study(study)

    def _delete_study(self, study: dict):
        if not DB_AVAILABLE:
            self._status("  DB offline.", DANGER); return
        try:
            db = StudyDatabaseConnection()
            db.delete_study(study.get("study_name", ""), study.get("company_name", ""))
            self._status(f"  Deleted \"{study.get('study_name')}\".", SUCCESS)
            QTimer.singleShot(200, self._load_studies_from_db)
        except Exception as ex:
            self._status(f"  Delete failed: {ex}", DANGER)

    # ── Status bar ───────────────────────────────────────────
    def _status(self, msg, color=None):
        self._status_bar.setText(msg)
        c = color or TEXT_LIGHT
        self._status_bar.setStyleSheet(f"background:{SIDEBAR_BG};border-top:1px solid {BORDER};"
                                       f"padding:6px 20px;min-height:32px;max-height:32px;"
                                       f"font-size:11px;color:{c};")
        if color:
            QTimer.singleShot(4000, lambda: self._status("  Ready"))


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
    w = ResearcherDashboard(); w.show()
    sys.exit(app.exec_())