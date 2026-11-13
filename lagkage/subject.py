"""Marker motiv med ISNet (open source, fra rembg-projektet), kører lokalt via onnxruntime."""
import os
import threading
import numpy as np
from PIL import Image

from . import inpaint

MODEL_URL = 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx'
SIZE = 1024
_session = None
_lock = threading.Lock()


def model_path():
    return os.path.join(os.path.dirname(inpaint.model_path()), 'isnet-general-use.onnx')


def model_ready():
    p = model_path()
    return os.path.exists(p) and os.path.getsize(p) > 100_000_000


def download_model(progress=None):
    return inpaint.download_model(progress, MODEL_URL, model_path())


def _sess():
    global _session
    with _lock:
        if _session is None:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            _session = ort.InferenceSession(model_path(), opts, providers=['CPUExecutionProvider'])
        return _session


def subject_mask(rgb):
    """rgb: (H, W, 3) uint8 -> (H, W) uint8 maske over motivet."""
    h, w = rgb.shape[:2]
    small = np.asarray(Image.fromarray(rgb).resize((SIZE, SIZE), Image.LANCZOS)).astype(np.float32)
    small = small / max(1.0, float(small.max())) - 0.5
    x = small.transpose(2, 0, 1)[None].astype(np.float32)
    pred = _sess().run(None, {'input_image': x})[0][0, 0]
    lo, hi = float(pred.min()), float(pred.max())
    pred = (pred - lo) / max(1e-6, hi - lo)
    m = Image.fromarray((pred * 255).astype(np.uint8)).resize((w, h), Image.LANCZOS)
    m = np.asarray(m).astype(np.float32)
    # skærp kanten lidt, så markeringen ikke bliver grødet
    m = np.clip((m - 128) * 1.6 + 128, 0, 255)
    return m.astype(np.uint8)
