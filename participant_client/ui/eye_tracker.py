"""
eye_tracker.py  —  ultrawide edition with offset correction
────────────────────────────────────────────────────────────
Drop next to main.py.  Import with:

    from eye_tracker import EyeTracker

Key fixes vs previous versions
───────────────────────────────
1. Removed broken `from mediapipe.python.*` import.
2. Raw iris values normalised to [0,1] before polynomial fit (fixes left-skew).
3. Post-calibration offset correction: after the 20-point grid, one final
   centre-point is shown.  The difference between where the model predicts
   and (0.5, 0.5) is stored as a bias and subtracted from every live reading.
   This eliminates the systematic up/down/left/right drift caused by camera
   angle and monitor height.

Signals
───────
  frame_ready(np.ndarray)          BGR webcam frame
  gaze_updated(float, float)       Calibrated + corrected gaze in [0, 1]
  raw_gaze_updated(float, float)   Raw iris ratio
  calib_step(int, float, float)    Point index, screen_x, screen_y
  calib_done()                     Calibration + offset correction complete
"""

import time
import threading
import numpy as np
import cv2
import mediapipe as mp
from PyQt5.QtCore import QThread, pyqtSignal


# ── landmark indices ─────────────────────────────────────────────────────────
LEFT_EYE_OUTER   = 33
LEFT_EYE_INNER   = 133
LEFT_EYE_TOP     = 159
LEFT_EYE_BOTTOM  = 145
RIGHT_EYE_OUTER  = 263
RIGHT_EYE_INNER  = 362
RIGHT_EYE_TOP    = 386
RIGHT_EYE_BOTTOM = 374
LEFT_IRIS        = 468
RIGHT_IRIS       = 473

# ── 5×4 calibration grid (20 points) ─────────────────────────────────────────
CALIB_POINTS = [
    (0.05, 0.10), (0.28, 0.10), (0.50, 0.10), (0.72, 0.10), (0.95, 0.10),
    (0.05, 0.37), (0.28, 0.37), (0.50, 0.37), (0.72, 0.37), (0.95, 0.37),
    (0.05, 0.63), (0.28, 0.63), (0.50, 0.63), (0.72, 0.63), (0.95, 0.63),
    (0.05, 0.90), (0.28, 0.90), (0.50, 0.90), (0.72, 0.90), (0.95, 0.90),
]

# Final offset-correction point shown after the grid (screen centre)
OFFSET_POINT     = (0.50, 0.50)

SAMPLES_PER_POINT = 50
SKIP_FRAMES       = 25
OVERLAY_WAIT      = 0.6
SMOOTH_ALPHA      = 0.35

# Total steps reported to the UI = 20 grid points + 1 offset point
TOTAL_STEPS = len(CALIB_POINTS) + 1


# ─────────────────────────────────────────────────────────────────────────────
class EyeTracker(QThread):
# ─────────────────────────────────────────────────────────────────────────────

    frame_ready      = pyqtSignal(object)
    gaze_updated     = pyqtSignal(float, float)
    raw_gaze_updated = pyqtSignal(float, float)
    calib_step       = pyqtSignal(int, float, float)  # global step idx, sx, sy
    calib_done       = pyqtSignal()

    # ── init ─────────────────────────────────────────────────────────────────
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock           = threading.Lock()
        self._running        = False
        self._mode           = "preview"
        self._cam_index      = 0
        self._next_cam_index = 0
        self._cap            = None

        self._calib_raw    = []
        self._calib_screen = []
        self._calib_model  = None   # (cx, cy, raw_min, raw_range)
        self._offset_x     = 0.0   # post-calibration bias correction
        self._offset_y     = 0.0

        self._sx = 0.5
        self._sy = 0.5

        self._reset_point()

    def _reset_point(self):
        self._pt_idx          = 0
        self._pt_samples      = []
        self._pt_skip         = SKIP_FRAMES
        self._pt_wait_t       = 0.0
        self._pt_emitted      = False
        self._offset_phase    = False   # True when collecting the centre offset point

    # ── public API ───────────────────────────────────────────────────────────
    def start_preview(self):
        with self._lock:
            self._mode = "preview"
        if not self.isRunning():
            self._running = True
            self.start()

    def start_calibration(self):
        with self._lock:
            self._mode         = "calibration"
            self._calib_raw    = []
            self._calib_screen = []
            self._calib_model  = None
            self._offset_x     = 0.0
            self._offset_y     = 0.0
        self._reset_point()

    def start_tracking(self):
        with self._lock:
            if self._calib_model is not None:
                self._mode = "tracking"

    def switch_camera(self, index: int):
        self._next_cam_index = index

    def stop(self):
        self._running = False

    # ── worker thread ────────────────────────────────────────────────────────
    def run(self):
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self._cap       = self._open_cam(self._next_cam_index)
        self._cam_index = self._next_cam_index
        self._reset_point()

        while self._running:

            if self._next_cam_index != self._cam_index:
                if self._cap:
                    self._cap.release()
                self._cam_index = self._next_cam_index
                self._cap = self._open_cam(self._cam_index)

            if not self._cap or not self._cap.isOpened():
                time.sleep(0.1)
                continue

            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            self.frame_ready.emit(frame)

            rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            if not results.multi_face_landmarks:
                continue

            lms          = results.multi_face_landmarks[0].landmark
            raw_x, raw_y = self._iris_ratio(lms)
            self.raw_gaze_updated.emit(float(raw_x), float(raw_y))

            with self._lock:
                mode = self._mode

            if mode == "calibration":
                self._calib_tick(raw_x, raw_y)
            elif mode == "tracking":
                self._track_tick(raw_x, raw_y)

        if self._cap:
            self._cap.release()
        face_mesh.close()

    # ── calibration state machine ────────────────────────────────────────────
    def _calib_tick(self, rx, ry):

        # ── offset-correction phase (after all 20 grid points) ───────────────
        if self._offset_phase:
            self._offset_tick(rx, ry)
            return

        # ── normal grid phase ─────────────────────────────────────────────────

        # announce dot
        if not self._pt_emitted:
            px, py = CALIB_POINTS[self._pt_idx]
            self.calib_step.emit(self._pt_idx, px, py)
            self._pt_wait_t  = time.time()
            self._pt_skip    = SKIP_FRAMES
            self._pt_emitted = True
            return

        # overlay animation wait
        if time.time() - self._pt_wait_t < OVERLAY_WAIT:
            return

        # settle frames
        if self._pt_skip > 0:
            self._pt_skip -= 1
            return

        # collect
        self._pt_samples.append((rx, ry))
        if len(self._pt_samples) < SAMPLES_PER_POINT:
            return

        # store median
        arr    = np.array(self._pt_samples)
        mx     = float(np.median(arr[:, 0]))
        my     = float(np.median(arr[:, 1]))
        px, py = CALIB_POINTS[self._pt_idx]

        with self._lock:
            self._calib_raw.append((mx, my))
            self._calib_screen.append((px, py))

        self._pt_samples = []
        self._pt_idx    += 1
        self._pt_emitted = False

        # all grid points done → fit model then start offset phase
        if self._pt_idx >= len(CALIB_POINTS):
            self._fit_model()
            # transition to offset phase
            self._offset_phase   = True
            self._pt_emitted     = False
            self._pt_samples     = []
            self._pt_skip        = SKIP_FRAMES
            self._pt_wait_t      = 0.0

    # ── offset correction tick ───────────────────────────────────────────────
    def _offset_tick(self, rx, ry):
        """
        Show the centre dot (step index = 20), collect samples,
        compute where the model predicts vs (0.5, 0.5), store the delta.
        """
        # announce centre dot (step 20 = last step in the UI progress bar)
        if not self._pt_emitted:
            self.calib_step.emit(len(CALIB_POINTS), OFFSET_POINT[0], OFFSET_POINT[1])
            self._pt_wait_t  = time.time()
            self._pt_skip    = SKIP_FRAMES
            self._pt_emitted = True
            return

        if time.time() - self._pt_wait_t < OVERLAY_WAIT:
            return

        if self._pt_skip > 0:
            self._pt_skip -= 1
            return

        self._pt_samples.append((rx, ry))
        if len(self._pt_samples) < SAMPLES_PER_POINT:
            return

        # compute median of centre-point readings
        arr = np.array(self._pt_samples)
        mx  = float(np.median(arr[:, 0]))
        my  = float(np.median(arr[:, 1]))

        # where does the model think we're looking?
        pred_x, pred_y = self._map_raw(mx, my)

        # offset = prediction − truth  (we'll subtract this from live readings)
        with self._lock:
            self._offset_x = pred_x - OFFSET_POINT[0]
            self._offset_y = pred_y - OFFSET_POINT[1]
            self._mode     = "tracking"

        self.calib_done.emit()

    # ── tracking ─────────────────────────────────────────────────────────────
    def _track_tick(self, rx, ry):
        gx, gy = self._map_raw(rx, ry)

        # apply offset correction
        with self._lock:
            gx -= self._offset_x
            gy -= self._offset_y

        self._sx = SMOOTH_ALPHA * gx + (1 - SMOOTH_ALPHA) * self._sx
        self._sy = SMOOTH_ALPHA * gy + (1 - SMOOTH_ALPHA) * self._sy
        self.gaze_updated.emit(
            float(np.clip(self._sx, 0.0, 1.0)),
            float(np.clip(self._sy, 0.0, 1.0)),
        )

    # ── iris ratio ───────────────────────────────────────────────────────────
    def _iris_ratio(self, lms):
        def _eye(lc, rc, top, bot, iris):
            l  = lms[lc].x;   r  = lms[rc].x
            t  = lms[top].y;  b  = lms[bot].y
            ix = lms[iris].x; iy = lms[iris].y
            w  = abs(r - l) or 1e-6
            h  = abs(b - t) or 1e-6
            return 1.0 - (ix - min(l, r)) / w, (iy - t) / h

        lx, ly = _eye(LEFT_EYE_OUTER,  LEFT_EYE_INNER,
                      LEFT_EYE_TOP,    LEFT_EYE_BOTTOM, LEFT_IRIS)
        rx, ry = _eye(RIGHT_EYE_INNER, RIGHT_EYE_OUTER,
                      RIGHT_EYE_TOP,   RIGHT_EYE_BOTTOM, RIGHT_IRIS)
        return (lx + rx) / 2.0, (ly + ry) / 2.0

    # ── polynomial fit ───────────────────────────────────────────────────────
    def _fit_model(self):
        with self._lock:
            raw    = np.array(self._calib_raw)
            screen = np.array(self._calib_screen)

        raw_min   = raw.min(axis=0)
        raw_max   = raw.max(axis=0)
        raw_range = raw_max - raw_min
        raw_range[raw_range < 1e-6] = 1e-6

        norm   = (raw - raw_min) / raw_range
        nx, ny = norm[:, 0], norm[:, 1]
        A = np.column_stack([
            np.ones(len(norm)), nx, ny,
            nx * ny, nx ** 2, ny ** 2,
        ])
        cx, *_ = np.linalg.lstsq(A, screen[:, 0], rcond=None)
        cy, *_ = np.linalg.lstsq(A, screen[:, 1], rcond=None)

        with self._lock:
            self._calib_model = (cx, cy, raw_min, raw_range)

    def _map_raw(self, rx, ry):
        """Apply polynomial model (without offset correction)."""
        with self._lock:
            model = self._calib_model
        if model is None:
            return rx, ry
        cx, cy, raw_min, raw_range = model
        nx = (rx - raw_min[0]) / raw_range[0]
        ny = (ry - raw_min[1]) / raw_range[1]
        f  = np.array([1.0, nx, ny, nx * ny, nx ** 2, ny ** 2])
        return float(np.dot(cx, f)), float(np.dot(cy, f))

    # ── camera ───────────────────────────────────────────────────────────────
    @staticmethod
    def _open_cam(index):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS,          30)
        return cap