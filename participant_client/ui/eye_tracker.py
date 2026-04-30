import time
import threading
import numpy as np
import cv2
import mediapipe as mp
from PyQt5.QtCore import QThread, pyqtSignal


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

CALIB_POINTS = [
    (0.08, 0.10), (0.28, 0.10), (0.50, 0.10), (0.72, 0.10), (0.92, 0.10),
    (0.08, 0.50), (0.28, 0.50), (0.50, 0.50), (0.72, 0.50), (0.92, 0.50),
    (0.08, 0.90), (0.28, 0.90), (0.50, 0.90), (0.72, 0.90), (0.92, 0.90),
]

OFFSET_POINT      = (0.50, 0.50)

SAMPLES_PER_POINT = 80
SKIP_FRAMES       = 50
OVERLAY_WAIT      = 1.5
SMOOTH_ALPHA      = 0.12  


VERTICAL_STRETCH  = 1.0
VERTICAL_BIAS     = 0.0

TOTAL_STEPS = len(CALIB_POINTS) + 1


class EyeTracker(QThread):

    frame_ready      = pyqtSignal(object)
    gaze_updated     = pyqtSignal(float, float)
    raw_gaze_updated = pyqtSignal(float, float)
    calib_step       = pyqtSignal(int, float, float)
    calib_done       = pyqtSignal()

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
        self._calib_model  = None
        self._offset_x     = 0.0
        self._offset_y     = 0.0

        self._sx = 0.5
        self._sy = 0.5

        self._reset_point()

    def _reset_point(self):
        self._pt_idx       = 0
        self._pt_samples   = []
        self._pt_skip      = SKIP_FRAMES
        self._pt_wait_t    = 0.0
        self._pt_emitted   = False
        self._offset_phase = False

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

    def run(self):
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        )

        self._cap       = self._open_cam(self._next_cam_index)
        self._cam_index = self._next_cam_index
        self._reset_point()

        while self._running:

            # swap camera if user changed it
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

    # steps through each calibration point one at a time
    def _calib_tick(self, rx, ry):

        if self._offset_phase:
            self._offset_tick(rx, ry)
            return

        # show the dot for this point
        if not self._pt_emitted:
            px, py = CALIB_POINTS[self._pt_idx]
            self.calib_step.emit(self._pt_idx, px, py)
            self._pt_wait_t  = time.time()
            self._pt_skip    = SKIP_FRAMES
            self._pt_emitted = True
            return

        # wait for the overlay animation to settle
        if time.time() - self._pt_wait_t < OVERLAY_WAIT:
            return

        # skip some frames so the eye has time to land on the dot
        if self._pt_skip > 0:
            self._pt_skip -= 1
            return

        # collect samples for this point
        self._pt_samples.append((rx, ry))
        if len(self._pt_samples) < SAMPLES_PER_POINT:
            return

        # use the median to reduce noise
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

        # all points done, fit the model and move to offset correction
        if self._pt_idx >= len(CALIB_POINTS):
            self._fit_model()
            self._offset_phase = True
            self._pt_emitted   = False
            self._pt_samples   = []
            self._pt_skip      = SKIP_FRAMES
            self._pt_wait_t    = 0.0

    #show center dot and measure how far off the model is
    def _offset_tick(self, rx, ry):
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

        arr            = np.array(self._pt_samples)
        mx             = float(np.median(arr[:, 0]))
        my             = float(np.median(arr[:, 1]))
        pred_x, pred_y = self._map_raw(mx, my)

        # store the error so it can subtract it from live readings
        with self._lock:
            self._offset_x = pred_x - OFFSET_POINT[0]
            self._offset_y = pred_y - OFFSET_POINT[1]
            self._mode     = "tracking"

        self.calib_done.emit()

    # apply the model then stretch/bias to correct for low camera angle
    def _track_tick(self, rx, ry):
        gx, gy = self._map_raw(rx, ry)

        with self._lock:
            gx -= self._offset_x
            gy -= self._offset_y

        # vertical stretch and bias applied here
        gy = 0.5 + (gy - 0.5) * VERTICAL_STRETCH
        gy = gy - VERTICAL_BIAS

        self._sx = SMOOTH_ALPHA * gx + (1 - SMOOTH_ALPHA) * self._sx
        self._sy = SMOOTH_ALPHA * gy + (1 - SMOOTH_ALPHA) * self._sy
        self.gaze_updated.emit(
            float(np.clip(self._sx, 0.0, 1.0)),
            float(np.clip(self._sy, 0.0, 1.0)),
        )

    # figure out where the iris is relative to the eye corners
    def _iris_ratio(self, lms):

        def _eye(lc, rc, top, bot, iris):
            lx = lms[lc].x;  rx = lms[rc].x
            ty = lms[top].y; by = lms[bot].y
            ix = lms[iris].x; iy = lms[iris].y
            w  = abs(rx - lx) or 1e-6
            h  = abs(by - ty) or 1e-6
            openness = h / w
            ratio_x  = 1.0 - (ix - min(lx, rx)) / w
            ratio_y  = (iy - ty) / h
            return ratio_x, ratio_y, openness

        lrx, lry, l_open = _eye(LEFT_EYE_OUTER,  LEFT_EYE_INNER,
                                 LEFT_EYE_TOP,    LEFT_EYE_BOTTOM, LEFT_IRIS)
        rrx, rry, r_open = _eye(RIGHT_EYE_INNER, RIGHT_EYE_OUTER,
                                 RIGHT_EYE_TOP,   RIGHT_EYE_BOTTOM, RIGHT_IRIS)

        total = l_open + r_open or 1e-6
        raw_x = (lrx * l_open + rrx * r_open) / total
        raw_y = (lry * l_open + rry * r_open) / total

        # correct for head turning left/right using distance between eye corners
        iod = abs(lms[RIGHT_EYE_OUTER].x - lms[LEFT_EYE_OUTER].x) or 1e-6
        yaw_scale = 1.0
        raw_x = 0.5 + (raw_x - 0.5) * yaw_scale

        return float(np.clip(raw_x, 0.0, 1.0)), float(np.clip(raw_y, 0.0, 1.0))

    # fit a polynomial that maps raw iris position to screen position
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

        # build the feature matrix for the polynomial
        A = np.column_stack([
            np.ones(len(norm)),
            nx, ny,
            nx * ny,
            nx ** 2, ny ** 2,
            nx ** 2 * ny,
            nx * ny ** 2,
        ])
        cx, *_ = np.linalg.lstsq(A, screen[:, 0], rcond=None)
        cy, *_ = np.linalg.lstsq(A, screen[:, 1], rcond=None)

        with self._lock:
            self._calib_model = (cx, cy, raw_min, raw_range)

    # apply the fitted model to get screen coordinates from the iris reading
    def _map_raw(self, rx, ry):
        with self._lock:
            model = self._calib_model
        if model is None:
            return rx, ry
        cx, cy, raw_min, raw_range = model
        nx = (rx - raw_min[0]) / raw_range[0]
        ny = (ry - raw_min[1]) / raw_range[1]
        f  = np.array([
            1.0,
            nx, ny,
            nx * ny,
            nx ** 2, ny ** 2,
            nx ** 2 * ny,
            nx * ny ** 2,
        ])
        return float(np.dot(cx, f)), float(np.dot(cy, f))

    # open the camera with the right backend for mac
    @staticmethod
    def _open_cam(index):
        cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FPS, 30)
        return cap