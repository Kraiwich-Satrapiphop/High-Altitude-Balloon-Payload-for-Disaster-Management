import cv2
import os
import threading
from datetime import datetime

# Keep the camera open between calls — opening/closing on every call exhausts
# the USB driver after a few rapid cycles and causes isOpened() to return False.
_cap  = None
_lock = threading.Lock()   # shared by client handler thread and auto_capture thread


def _ensure_open():
    """Return the VideoCapture, (re)opening it if necessary."""
    global _cap
    if _cap is None or not _cap.isOpened():
        if _cap is not None:
            _cap.release()
        _cap = cv2.VideoCapture(0)
    return _cap


def read_cam(folder_path, logger):
    global _cap
    with _lock:
        cap = _ensure_open()

        if not cap.isOpened():
            logger.log("[Camera] Failed to open Space Camera")
            raise RuntimeError("Failed to open Space Camera")

        ret, frame = cap.read()
        if not ret:
            logger.log("[Camera] Failed to grab frame — reinitialising camera")
            cap.release()
            _cap = None
            raise RuntimeError("Failed to grab frame")

        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = folder_path + f"/SpaceCam/SpaceCam_{timestamp}.jpg"
        cv2.imwrite(filename, frame)

        success, encoded_image = cv2.imencode('.jpg', frame)
        if not success:
            raise RuntimeError("Failed to encode frame")
        jpg_bytes = encoded_image.tobytes()

        logger.log(f"[Camera] Successfully read a frame ({width}x{height})")
        return jpg_bytes
