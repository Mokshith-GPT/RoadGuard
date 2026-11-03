"""
RoadGuard - Mobile REST API Service
Lightweight FastAPI endpoint allowing Android mobile devices to stream or upload road frames
and receive real-time damage segmentation, area percentages, and severity tiers.
"""

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import cv2
import numpy as np

from modules.image_acquisition import ImageAcquisition
from modules.preprocessing import ImagePreprocessor
from modules.damage_detection import DamageDetector
from modules.segmentation_severity import SeverityEstimator

app = FastAPI(
    title="RoadGuard Mobile Inspection API",
    description="REST backend for RoadGuard Android Mobile Application",
    version="1.0.0"
)

# Initialize singletons
preprocessor = ImagePreprocessor(target_size=(640, 640), clahe_clip_limit=3.0)
detector = DamageDetector(model_path="models/best.pt")
estimator = SeverityEstimator(low_threshold=10.0, medium_threshold=30.0)


@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "RoadGuard Mobile Telemetry Backend",
        "active_backend": detector.backend
    }


@app.post("/api/v1/inspect")
async def inspect_road_frame(file: UploadFile = File(...)):
    """
    Receives an image frame from Android camera, executes 5-module inspection,
    and returns detected defects, area percentage, and hazard severity.
    """
    contents = await file.read()
    success, img_bgr, msg = ImageAcquisition.load_image(contents)
    if not success:
        return JSONResponse(status_code=400, content={"error": msg})

    # Execute Pipeline
    prep_data = preprocessor.process(img_bgr)
    detections = detector.detect(prep_data)
    analysis = estimator.process(prep_data, detections)

    # Return clean mobile payload
    response_payload = {
        "overall_severity": analysis["overall_severity"],
        "overall_score": analysis["overall_score"],
        "damage_area_percentage": analysis["damage_area_percentage"],
        "total_defects_count": len(analysis["detections"]),
        "damage_counts": analysis["damage_counts"],
        "detections": [
            {
                "class_code": d["class_code"],
                "class_name": d["class_name"],
                "confidence": d["confidence"],
                "bbox": d["bbox"],
                "damage_pixels": d["damage_pixels"],
                "bbox_damage_percentage": d["bbox_damage_percentage"],
                "severity_tier": d["severity_tier"]
            }
            for d in analysis["detections"]
        ]
    }
    return response_payload


if __name__ == "__main__":
    import uvicorn
    print("Starting RoadGuard Mobile API Server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
