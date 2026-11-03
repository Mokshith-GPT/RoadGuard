"""
RoadGuard trained-model inference adapter.

Exposes the JSON contract consumed by cloudflare-backend/src/index.js.
Only loads and reports trained YOLO detections when a real weights file exists.
No image uploads or detections are persisted by this service.
"""
import base64
import binascii
import hmac
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from modules.image_acquisition import ImageAcquisition
from modules.preprocessing import ImagePreprocessor
from modules.damage_detection import DamageDetector
from modules.segmentation_severity import SeverityEstimator

MODEL_PATH = Path(os.getenv("MODEL_PATH", "models/best.pt"))
MODEL_API_TOKEN = os.getenv("MODEL_API_TOKEN", "")
CONFIDENCE = float(os.getenv("MODEL_CONFIDENCE", "0.25"))

app = FastAPI(
    title="RoadGuard YOLO Inference API",
    version="1.0.0",
    description="Authenticated road-surface distress inference adapter for the RoadGuard Cloudflare Worker."
)

preprocessor = ImagePreprocessor(target_size=(640, 640), clahe_clip_limit=3.0)
detector = DamageDetector(model_path=str(MODEL_PATH), conf_threshold=CONFIDENCE)
estimator = SeverityEstimator(low_threshold=10.0, medium_threshold=30.0)


class InspectionPayload(BaseModel):
    image_base64: str = Field(min_length=100, max_length=9_000_000)
    filename: Optional[str] = Field(default="road-image.jpg", max_length=160)
    metadata: Dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health():
    model_ready = detector.backend == "yolo" and detector.model is not None
    return {
        "status": "online",
        "service": "RoadGuard trained-model inference",
        "modelConfigured": model_ready,
        "modelPathExists": MODEL_PATH.is_file(),
        "modelBackend": detector.backend,
        "supportedClasses": ["D00", "D10", "D20", "D40"]
    }


@app.post("/api/v1/inspect")
def inspect(payload: InspectionPayload, authorization: Optional[str] = Header(default=None)):
    if not MODEL_API_TOKEN:
        raise HTTPException(status_code=503, detail="MODEL_API_TOKEN is not configured on the inference service.")
    supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not hmac.compare_digest(supplied, MODEL_API_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if detector.backend != "yolo" or detector.model is None:
        raise HTTPException(
            status_code=503,
            detail="Trained YOLO weights are missing. Copy the trained weights to models/best.pt and restart."
        )

    encoded = payload.image_base64
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="image_base64 is invalid.")

    if len(image_bytes) > 6 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds the 6 MB inference limit.")

    ok, image_bgr, message = ImageAcquisition.load_image(image_bytes)
    if not ok or image_bgr is None:
        raise HTTPException(status_code=400, detail=message)
    valid, validation_message = ImageAcquisition.validate_image(image_bgr)
    if not valid:
        raise HTTPException(status_code=400, detail=validation_message)

    preprocessed = preprocessor.process(image_bgr)
    detections = detector.detect(preprocessed)
    analysis = estimator.process(preprocessed, detections)

    result_detections = []
    for item in analysis["detections"]:
        result_detections.append({
            "class_code": item["class_code"],
            "class_name": item["class_name"],
            "confidence": float(item["confidence"]),
            "bbox": [int(v) for v in item["bbox"]],
            "damage_pixels": int(item["damage_pixels"]),
            "bbox_damage_percentage": float(item["bbox_damage_percentage"]),
            "severity_tier": item["severity_tier"],
            "severity_score": float(item["severity_score"])
        })

    return {
        "success": True,
        "model": "trained-yolo",
        "filename": payload.filename,
        "overall_severity": analysis["overall_severity"],
        "overall_score": float(analysis["overall_score"]),
        "damage_area_percentage": float(analysis["damage_area_percentage"]),
        "total_defects_count": len(result_detections),
        "damage_counts": analysis["damage_counts"],
        "detections": result_detections,
        "metadata_received": payload.metadata
    }
