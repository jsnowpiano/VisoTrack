"""
eye_tracker.py
─────────────────
Drop this file next to main.py and add this import at the top of main.py:

    from eye_tracker import EyeTracker

The class runs entirely on a background QThread so the UI stays responsive.

Signals emitted
───────────────
  frame_ready(np.ndarray)        – BGR webcam frame (for the Camera tab preview)
  gaze_updated(float, float)     – calibrated gaze position, both values in [0, 1]
  raw_gaze_updated(float, float) – raw iris-ratio values before calibration
  calib_step(int, float, float)  – fired for each of the 9 calibration points
                                   args: point_index, screen_x_ratio, screen_y_ratio
  calib_done()                   – fired once all 9 points have been collected

How calibration works
─────────────────────
Nine screen positions arranged in a 3×3 grid are shown one at a time (via the
CalibOverlay in main.py).  For each position the worker records ~45 iris
feature vectors, takes the median, and stores the (raw_x, raw_y) → (screen_x,
screen_y) mapping.  After all 9 points are collected a simple bilinear
regression is solved with np.linalg.lstsq so that every subsequent raw reading
is mapped to an estimated screen position.
"""

import time
import threading
import numpy as np
import cv2

import mediapipe as mp
from mediapipe.python.solutions.face_mesh_connections import FACEMESH_LEFT_IRIS, FACEMESH_RIGHT_IRIS

from PyQt5.QtCore import QThread, pyqtSignal

# ─────────────────────────────────────────────────────────────
#  MediaPipe landmark indices
# ─────────────────────────────────────────────────────────────
# Eye-corner landmarks (used to normalise iris position within the eye)
LEFT_EYE_OUTER  = 33
LEFT_EYE_INNER  = 133
LEFT_EYE_TOP    = 159
LEFT_EYE_BOTTOM = 145

RIGHT_EYE_OUTER  = 263
RIGHT_EYE_INNER  = 362
RIGHT_EYE_TOP    = 386
RIGHT_EYE_BOTTOM = 374

# Centre of each iris (landmark 468 = left iris centre, 473 = right iris centre)
LEFT_IRIS_CENTER  = 468
RIGHT_IRIS_CENTER = 473

# ─────────────────────────────────────────────────────────────
#  Calibration grid  (normalised screen coords, x then y)
# ─────────────────────────────────────────────────────────────
CALIB_POINTS = [
    (0.10, 0.10), (0.37, 0.10), (0.63, 0.10), (0.90, 0.10),
    (0.10, 0.37), (0.37, 0.37), (0.63, 0.37), (0.90, 0.37),
    (0.10, 0.63), (0.37, 0.63), (0.63, 0.63), (0.90, 0.63),
    (0.10, 0.90), (0.37, 0.90), (0.63, 0.90), (0.90, 0.90),
]

# How many frames to collect per calibration point
SAMPLES_PER_POINT = 60
# How many frames to skip at the start of each point (let the eye settle)
SKIP_FRAMES = 20

# Exponential moving-average alpha for gaze smoothing (lower = smoother)
SMOOTH_ALPHA = 0.40


class EyeTracker(QThread):
    """Background thread that drives the webcam, MediaPipe, calibration,
    and gaze estimation.  Communicate with it via its public methods;
    receive data via the Qt signals listed above."""

    frame_ready      = pyqtSignal(object)          # BGR ndarray
    gaze_updated     = pyqtSignal(float, float)    # calibrated (x, y) in [0,1]
    raw_gaze_updated = pyqtSignal(float, float)    # raw iris ratio (x, y)
    calib_step       = pyqtSignal(int, float, float)  # idx, screen_x, screen_y
    calib_done       = pyqtSignal()

    # ── lifecycle ────────────────────────────────────────────
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cam_index      = 0
        self._next_cam_index = 0          # set by switch_camera()
        self._cap            = None

        # state machine
        self._mode   = "preview"          # "preview" | "calibration" | "tracking"
        self._lock   = threading.Lock()

        # calibration data
        self._calib_raw    = []           # list of (raw_x, raw_y) medians, one per point
        self._calib_screen = []           # matching screen (px, py) coords
        self._calib_model  = None         # solved least-squares coefficients

        # smoothing state
        self._smooth_x = 0.5
        self._smooth_y = 0.5

        self._running = False

    # ── public API (thread-safe) ─────────────────────────────
    def start_preview(self):
        """Start (or restart) the camera in preview-only mode."""
        with self._lock:
            self._mode = "preview"
        if not self.isRunning():
            self._running = True
            self.start()

    def start_calibration(self):
        """Trigger a fresh 9-point calibration sequence."""
        with self._lock:
            self._mode            = "calibration"
            self._calib_raw       = []
            self._calib_screen    = []
            self._calib_model     = None
            # Reset per-point state so the run() loop restarts cleanly
            self._calib_point_idx  = 0
            self._calib_samples    = []
            self._calib_skip       = SKIP_FRAMES
            self._calib_wait_start = None
            self._calib_point_emitted = False   # have we fired calib_step for current point?

    def start_tracking(self):
        """Switch to tracking mode (calibration must have been run first)."""
        with self._lock:
            if self._calib_model is not None:
                self._mode = "tracking"

    def switch_camera(self, index: int):
        """Hot-swap the camera while the thread is running."""
        self._next_cam_index = index

    def stop(self):
        self._running = False

    # ── main thread loop ─────────────────────────────────────
    def run(self):
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,       # enables iris landmarks 468-477
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self._cap = self._open_camera(self._next_cam_index)
        self._cam_index = self._next_cam_index

        # Calibration state lives on self so start_calibration() can reset it
        # from outside the thread safely (under _lock).
        self._calib_point_idx     = 0
        self._calib_samples       = []
        self._calib_skip          = SKIP_FRAMES
        self._calib_wait_start    = None
        self._calib_point_emitted = False

        while self._running:
            # ── hot-swap camera ──────────────────────────────
            if self._next_cam_index != self._cam_index:
                if self._cap:
                    self._cap.release()
                self._cam_index = self._next_cam_index
                self._cap = self._open_camera(self._cam_index)

            if not self._cap or not self._cap.isOpened():
                time.sleep(0.1)
                continue

            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            # ── emit raw frame ───────────────────────────────
            self.frame_ready.emit(frame)

            # ── MediaPipe inference ──────────────────────────
            rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            if not results.multi_face_landmarks:
                continue

            lms = results.multi_face_landmarks[0].landmark
            h, w = frame.shape[:2]

            raw_x, raw_y = self._extract_iris_ratio(lms)

            self.raw_gaze_updated.emit(raw_x, raw_y)

            # ── mode dispatch ────────────────────────────────
            with self._lock:
                mode = self._mode

            if mode == "calibration":
                # ── Step 1: emit the signal for the current point if not yet done ──
                if not self._calib_point_emitted:
                    px, py = CALIB_POINTS[self._calib_point_idx]
                    self.calib_step.emit(self._calib_point_idx, px, py)
                    self._calib_wait_start    = time.time()
                    self._calib_skip          = SKIP_FRAMES
                    self._calib_point_emitted = True

                # ── Step 2: wait briefly so the overlay can animate in ───────────
                if (time.time() - self._calib_wait_start) < 0.5:
                    continue

                # ── Step 3: skip a few frames to let the eye settle ──────────────
                if self._calib_skip > 0:
                    self._calib_skip -= 1
                    continue

                # ── Step 4: collect a sample ─────────────────────────────────────
                self._calib_samples.append((raw_x, raw_y))

                # ── Step 5: once enough samples, compute median and advance ───────
                if len(self._calib_samples) >= SAMPLES_PER_POINT:
                    arr   = np.array(self._calib_samples)
                    med_x = float(np.median(arr[:, 0]))
                    med_y = float(np.median(arr[:, 1]))
                    px, py = CALIB_POINTS[self._calib_point_idx]

                    with self._lock:
                        self._calib_raw.append((med_x, med_y))
                        self._calib_screen.append((px, py))

                    self._calib_samples       = []
                    self._calib_point_idx    += 1
                    self._calib_point_emitted = False   # trigger emit for next point

                    if self._calib_point_idx >= len(CALIB_POINTS):
                        # All 9 points done — fit the model
                        self._fit_calibration_model()
                        self._calib_point_idx = 0
                        with self._lock:
                            self._mode = "tracking"
                        self.calib_done.emit()

            elif mode == "tracking":
                gx, gy = self._map_gaze(raw_x, raw_y)
                # Exponential smoothing
                self._smooth_x = SMOOTH_ALPHA * gx + (1 - SMOOTH_ALPHA) * self._smooth_x
                self._smooth_y = SMOOTH_ALPHA * gy + (1 - SMOOTH_ALPHA) * self._smooth_y
                self.gaze_updated.emit(
                    float(np.clip(self._smooth_x, 0.0, 1.0)),
                    float(np.clip(self._smooth_y, 0.0, 1.0)),
                )

        if self._cap:
            self._cap.release()
        face_mesh.close()

    # ── iris feature extraction ──────────────────────────────
    def _extract_iris_ratio(self, lms):
        """
        Return (raw_x, raw_y): normalised iris position averaged over both eyes.
        raw_x in [0,1]: 0 = screen left,  1 = screen right
        raw_y in [0,1]: 0 = screen top,   1 = screen bottom

        MediaPipe landmarks are in image space where x increases left→right
        *from the camera's view*, which is the mirror of the screen.
        We flip x (1 - ratio) so that looking right → higher raw_x.
        """
        def eye_ratio(left_corner, right_corner, top, bottom, iris_center):
            # left_corner/right_corner are in screen-space x order
            lx = lms[left_corner].x
            rx = lms[right_corner].x
            ty = lms[top].y
            by = lms[bottom].y
            cx = lms[iris_center].x
            cy = lms[iris_center].y

            eye_w = abs(rx - lx) or 1e-6
            eye_h = abs(by - ty) or 1e-6

            # Horizontal ratio in image space, then flip for screen space
            ratio_x_img = (cx - min(lx, rx)) / eye_w
            ratio_x = 1.0 - ratio_x_img   # mirror correction

            # Vertical: 0 = top of eye, 1 = bottom
            ratio_y = (cy - ty) / eye_h
            return ratio_x, ratio_y

        # LEFT eye: on screen, outer=33 is left, inner=133 is right
        lx, ly = eye_ratio(LEFT_EYE_OUTER, LEFT_EYE_INNER,
                           LEFT_EYE_TOP, LEFT_EYE_BOTTOM, LEFT_IRIS_CENTER)
        # RIGHT eye: on screen, inner=362 is left, outer=263 is right
        rx, ry = eye_ratio(RIGHT_EYE_INNER, RIGHT_EYE_OUTER,
                           RIGHT_EYE_TOP, RIGHT_EYE_BOTTOM, RIGHT_IRIS_CENTER)

        # Average both eyes
        return (lx + rx) / 2.0, (ly + ry) / 2.0

    # ── calibration model ────────────────────────────────────
    def _fit_calibration_model(self):
        """
        Fit a polynomial (degree-2 bilinear) mapping:
            raw (rx, ry)  →  screen (sx, sy)

        We build a feature matrix  [1, rx, ry, rx*ry, rx², ry²]
        and solve two independent least-squares problems (one for x, one for y).
        """
        with self._lock:
            raw    = np.array(self._calib_raw)
            screen = np.array(self._calib_screen)

        def features(r):
            rx, ry = r[:, 0], r[:, 1]
            return np.column_stack([
                np.ones(len(r)),
                rx, ry,
                rx * ry,
                rx ** 2,
                ry ** 2,
            ])

        A = features(raw)
        cx, _, _, _ = np.linalg.lstsq(A, screen[:, 0], rcond=None)
        cy, _, _, _ = np.linalg.lstsq(A, screen[:, 1], rcond=None)

        with self._lock:
            self._calib_model = (cx, cy)

    def _map_gaze(self, rx: float, ry: float) -> tuple:
        """Apply the fitted calibration model to a raw gaze reading."""
        with self._lock:
            model = self._calib_model

        if model is None:
            return rx, ry

        cx, cy = model
        f = np.array([1, rx, ry, rx * ry, rx ** 2, ry ** 2])
        gx = float(np.dot(cx, f))
        gy = float(np.dot(cy, f))
        return gx, gy

    # ── helpers ──────────────────────────────────────────────
    @staticmethod
    def _open_camera(index: int):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
        return cap