"""
SCOT — Inférence ONNX (sans PyTorch).

Reproduit exactement le prétraitement de predict.py / train.py (validation) :
  RGB → niveaux de gris → resize bilinéaire img_size×img_size → [0,1] → (x-0.5)/0.5
et la règle « image entièrement noire → sans_defaut ».
"""

import io
import json
import time

import numpy as np
import onnxruntime as ort
from PIL import Image

NO_DEFECT_CLASS = "sans_defaut"
WHITE_PIXEL_THRESHOLD = 1


class OnnxClassifier:
    def __init__(self, onnx_bytes: bytes, model_name: str = ""):
        self.session = ort.InferenceSession(onnx_bytes, providers=["CPUExecutionProvider"])
        meta = self.session.get_modelmeta().custom_metadata_map
        self.classes = json.loads(meta["classes"])
        self.img_size = int(meta.get("img_size", 128))
        self.model_name = model_name or meta.get("source_checkpoint", "")
        self.input_name = self.session.get_inputs()[0].name

    @property
    def display_classes(self):
        c = list(self.classes)
        return c if NO_DEFECT_CLASS in c else [*c, NO_DEFECT_CLASS]

    def preprocess(self, img: Image.Image) -> np.ndarray:
        gray = img.convert("RGB").convert("L").resize((self.img_size, self.img_size), Image.BILINEAR)
        x = np.asarray(gray, dtype=np.float32) / 255.0
        x = (x - 0.5) / 0.5
        return x[None, None, :, :]

    def predict_bytes(self, data: bytes) -> dict:
        img = Image.open(io.BytesIO(data))
        return self.predict_image(img)

    def predict_image(self, img: Image.Image) -> dict:
        t0 = time.perf_counter()
        classes = self.display_classes

        gray = np.asarray(img.convert("L"), dtype=np.uint8)
        if gray.size and not np.any(gray >= WHITE_PIXEL_THRESHOLD):
            probs = np.zeros(len(classes), dtype=np.float32)
            probs[classes.index(NO_DEFECT_CLASS)] = 1.0
        else:
            logits = self.session.run(None, {self.input_name: self.preprocess(img)})[0][0]
            e = np.exp(logits - logits.max())
            probs = (e / e.sum()).astype(np.float32)
            if len(classes) != len(self.classes):
                probs = np.append(probs, 0.0)

        idx = int(probs.argmax())
        return {
            "predicted_class": classes[idx],
            "confidence": float(probs[idx]),
            "probabilities": {c: round(float(p), 6) for c, p in zip(classes, probs)},
            "model_name": self.model_name,
            "inference_ms": int((time.perf_counter() - t0) * 1000),
            "width": img.width,
            "height": img.height,
        }
