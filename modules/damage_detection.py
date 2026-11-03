"""
RoadGuard - Module 3: Road Damage Detection and Classification
Detects damage classes: D00 (Longitudinal), D10 (Transverse), D20 (Alligator), D40 (Pothole).
Supports both trained YOLO model inference and a standalone computer vision heuristic detector.
"""

import cv2
import numpy as np
import os
from typing import List, Dict, Any, Optional

# RDD2022 standard damage taxonomy
DAMAGE_CLASSES = {
    0: {"code": "D00", "name": "Longitudinal Crack", "color": (255, 140, 0)},     # Deep Sky Blue (BGR: Blue/Orange)
    1: {"code": "D10", "name": "Transverse Crack", "color": (0, 215, 255)},       # Gold/Yellow
    2: {"code": "D20", "name": "Alligator Crack", "color": (255, 0, 255)},        # Magenta
    3: {"code": "D40", "name": "Pothole", "color": (0, 0, 255)}                   # Red
}


class DamageDetector:
    """Detects and categorizes pavement damage regions."""

    def __init__(self, model_path: Optional[str] = None, conf_threshold: float = 0.25):
        self.conf_threshold = conf_threshold
        self.model = None
        self.backend = "heuristic"

        # Attempt to load YOLO if ultralytics is available and model weights exist
        if model_path and os.path.exists(model_path):
            try:
                from ultralytics import YOLO
                self.model = YOLO(model_path)
                self.backend = "yolo"
                print(f"[DamageDetector] Loaded YOLO model from {model_path}")
            except Exception as e:
                print(f"[DamageDetector] YOLO load failed ({e}), using CV heuristic detector.")
        else:
            print("[DamageDetector] No model path specified or file missing. Initialized with CV heuristic detector.")

    def detect(self, preprocessed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Executes damage detection.
        Returns list of detection dictionaries:
        [{'bbox': [x, y, w, h], 'class_id': int, 'class_code': str, 'class_name': str, 'confidence': float, 'color': tuple}]
        """
        if self.backend == "yolo" and self.model is not None:
            return self._detect_yolo(preprocessed_data["enhanced"])
        else:
            return self._detect_heuristic(preprocessed_data)

    def _detect_yolo(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """Inference via Ultralytics YOLO model."""
        detections = []
        try:
            results = self.model(image, conf=self.conf_threshold, verbose=False)
            for res in results:
                boxes = res.boxes
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    x, y, w, h = int(x1), int(y1), int(x2 - x1), int(y2 - y1)

                    raw_name = ""
                    if hasattr(self.model, "names") and cls_id in self.model.names:
                        raw_name = str(self.model.names[cls_id]).lower()

                    if "pothole" in raw_name:
                        code, name, color = "D40", "Pothole", (0, 0, 255)
                    elif "longitudinal" in raw_name:
                        code, name, color = "D00", "Longitudinal Crack", (255, 140, 0)
                    elif "transverse" in raw_name:
                        code, name, color = "D10", "Transverse Crack", (0, 215, 255)
                    elif "alligator" in raw_name or "block" in raw_name:
                        code, name, color = "D20", "Alligator Crack", (255, 0, 255)
                    elif "crack" in raw_name:
                        code, name, color = "D00", "Linear Crack", (255, 140, 0)
                    else:
                        cls_meta = DAMAGE_CLASSES.get(cls_id, {
                            "code": f"D{cls_id}",
                            "name": f"Defect-{cls_id}",
                            "color": (0, 255, 255)
                        })
                        code, name, color = cls_meta["code"], cls_meta["name"], cls_meta["color"]

                    detections.append({
                        "bbox": [x, y, w, h],
                        "class_id": cls_id,
                        "class_code": code,
                        "class_name": name,
                        "confidence": round(conf, 3),
                        "color": color
                    })
        except Exception as e:
            print(f"[DamageDetector] YOLO inference error: {e}")
        return detections

    def _detect_heuristic(self, prep_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Computer Vision Feature-Based Detector:
        Analyzes intensity depressions, local gradient variance, and contour geometries.
        Enables testing and baseline demonstration even before model training!
        """
        gray = prep_data["gray"]
        road_mask = prep_data["road_mask"]
        h_img, w_img = gray.shape[:2]

        # 1. Edge-preserving blur to eliminate single-pixel noise
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)

        # 2. Adaptive thresholding to segment dark pavement anomalies
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 41, 15
        )

        # 3. Mask out boundary outside the drivable road corridor
        if road_mask is not None:
            eroded_road = cv2.erode(road_mask, np.ones((15, 15), np.uint8))
            thresh = cv2.bitwise_and(thresh, thresh, mask=eroded_road)

        # 4. Morphological opening and closing
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        raw_boxes = []
        confidences = []
        class_ids = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 150 or area > (h_img * w_img * 0.45):
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            # Ignore upper horizon
            if y < int(h_img * 0.35):
                continue

            aspect_ratio = float(w) / max(h, 1)
            perimeter = cv2.arcLength(cnt, True)
            compactness = (perimeter ** 2) / (4 * np.pi * max(area, 1))

            # Classify based on geometric morphology
            if area > 800 and compactness < 3.2 and 0.45 <= aspect_ratio <= 2.2:
                # Large, circular/elliptical dark depression -> Pothole (D40)
                cls_id = 3
                conf = min(0.95, 0.70 + (area / 12000.0))
            elif aspect_ratio < 0.55 or (h > 1.8 * w):
                # Tall vertical crack -> Longitudinal crack (D00)
                cls_id = 0
                conf = 0.82
            elif aspect_ratio > 1.8 or (w > 1.8 * h):
                # Wide horizontal crack -> Transverse crack (D10)
                cls_id = 1
                conf = 0.80
            else:
                # Irregular network -> Alligator crack (D20)
                cls_id = 2
                conf = 0.75

            # Pad bounding box
            pad = 6
            x_pad = max(0, x - pad)
            y_pad = max(0, y - pad)
            w_pad = min(w_img - x_pad, w + 2 * pad)
            h_pad = min(h_img - y_pad, h + 2 * pad)

            raw_boxes.append([x_pad, y_pad, w_pad, h_pad])
            confidences.append(float(conf))
            class_ids.append(cls_id)

        detections = []
        if raw_boxes:
            # Apply Non-Maximum Suppression (NMS) to eliminate duplicate overlapping boxes
            indices = cv2.dnn.NMSBoxes(raw_boxes, confidences, score_threshold=0.3, nms_threshold=0.4)
            if len(indices) > 0:
                for i in indices.flatten():
                    cls_id = class_ids[i]
                    cls_meta = DAMAGE_CLASSES[cls_id]
                    detections.append({
                        "bbox": raw_boxes[i],
                        "class_id": cls_id,
                        "class_code": cls_meta["code"],
                        "class_name": cls_meta["name"],
                        "confidence": round(confidences[i], 2),
                        "color": cls_meta["color"]
                    })

        return detections
