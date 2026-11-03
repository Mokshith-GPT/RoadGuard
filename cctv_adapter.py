"""
RoadGuard - Authorized CCTV & IP Camera Ingestion Adapter
Module for sampling and inspecting frames from authorized RTSP, ONVIF, or HTTP/MJPEG streams.

Features:
- Connects to authorized RTSP/HTTP streams with authentication credentials.
- Configurable sampling interval (default 1 FPS or N seconds).
- Processes frames through RoadGuard's 5-module CVIP / AI pipeline.
- Tags flagged distress frames with Camera ID, Geo-coordinates, Location Name, and Timestamp.
- Outputs annotated evidence overlays and JSON audit logs to outputs/cctv_evidence/.
- Includes mock/simulation mode for automated testing without live physical cameras.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

import cv2

from modules.preprocessing import ImagePreprocessor
from modules.damage_detection import DamageDetector
from modules.segmentation_severity import SeverityEstimator
from modules.visualization_report import VisualizerAndReporter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [CCTV-Adapter] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("RoadGuard-CCTV")


class CCTVStreamIngestion:
    """Ingests frames from authorized CCTV / RTSP video streams for pavement inspection."""

    def __init__(
        self,
        stream_url: str,
        camera_id: str = "CAM-01",
        location_name: str = "North Corridor Junction",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        sample_interval_sec: float = 1.0,
        conf_threshold: float = 0.20,
        model_path: str = "models/best.pt",
        output_dir: str = "outputs/cctv_evidence"
    ):
        self.stream_url = stream_url
        self.camera_id = camera_id
        self.location_name = location_name
        self.latitude = latitude
        self.longitude = longitude
        self.sample_interval = max(0.2, sample_interval_sec)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initializing CCTV ingestion for camera: {self.camera_id} at '{self.location_name}'")
        logger.info(f"Stream Source: {self._mask_url(self.stream_url)}")

        # Initialize CVIP Modules
        self.preprocessor = ImagePreprocessor(target_size=(640, 640), clahe_clip_limit=3.0)
        self.detector = DamageDetector(model_path=model_path, conf_threshold=conf_threshold)
        self.estimator = SeverityEstimator(low_threshold=10.0, medium_threshold=30.0)

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask credentials in RTSP/HTTP URLs for logging safety."""
        if "@" in url and "://" in url:
            prefix, rest = url.split("://", 1)
            auth, host = rest.split("@", 1)
            return f"{prefix}://***:***@{host}"
        return url

    def process_frame(self, frame: cv2.Mat, frame_index: int) -> Optional[Dict[str, Any]]:
        """Run inspection pipeline on a sampled CCTV frame."""
        timestamp = datetime.now(timezone.utc).isoformat()
        preprocessed = self.preprocessor.process(frame)
        detections = self.detector.detect(preprocessed)
        analysis = self.estimator.process(preprocessed, detections)

        num_defects = len(detections)
        severity = analysis["overall_severity"]

        logger.info(
            f"Frame #{frame_index} evaluated: {num_defects} defect(s) detected, "
            f"Severity: {severity}, Area: {analysis['damage_area_percentage']}%"
        )

        # Flag and archive if defects are detected or severity > Optimal
        if num_defects > 0 or analysis["overall_score"] > 0:
            evidence_id = f"CCTV_{self.camera_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_f{frame_index}"
            
            # Render visual overlays
            overlay = VisualizerAndReporter.render_overlay(preprocessed["enhanced"], analysis)
            
            # Add camera HUD overlay
            hud_text = f"{self.camera_id} | {self.location_name} | {timestamp}"
            cv2.putText(overlay, hud_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (245, 255, 220), 2)

            image_path = self.output_dir / f"{evidence_id}.jpg"
            meta_path = self.output_dir / f"{evidence_id}.json"

            cv2.imwrite(str(image_path), overlay)

            record = {
                "evidence_id": evidence_id,
                "camera_id": self.camera_id,
                "location_name": self.location_name,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "timestamp": timestamp,
                "frame_index": frame_index,
                "image_file": str(image_path.name),
                "damage_area_percentage": analysis["damage_area_percentage"],
                "overall_severity": analysis["overall_severity"],
                "overall_score": analysis["overall_score"],
                "damage_counts": analysis["damage_counts"],
                "detections": [
                    {
                        "class_code": d["class_code"],
                        "class_name": d["class_name"],
                        "confidence": float(d["confidence"]),
                        "bbox": d["bbox"],
                        "damage_pixels": d["damage_pixels"]
                    }
                    for d in analysis["detections"]
                ]
            }

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)

            logger.info(f"Flagged evidence saved: {image_path.name} & {meta_path.name}")
            return record

        return None

    def run(self, max_frames: Optional[int] = None):
        """Start streaming loop, sampling frames at the configured interval."""
        logger.info(f"Opening video stream: {self._mask_url(self.stream_url)}")
        cap = cv2.VideoCapture(self.stream_url)

        if not cap.isOpened():
            logger.error("Failed to connect to video stream. Verify stream URL and network access.")
            return

        frame_count = 0
        inspected_count = 0
        flagged_count = 0
        last_sample_time = 0.0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    logger.warning("Stream ended or frame could not be read.")
                    break

                frame_count += 1
                now = time.time()

                if now - last_sample_time >= self.sample_interval:
                    last_sample_time = now
                    inspected_count += 1

                    result = self.process_frame(frame, frame_count)
                    if result:
                        flagged_count += 1

                    if max_frames and inspected_count >= max_frames:
                        logger.info(f"Reached specified limit of {max_frames} inspected frames.")
                        break

        except KeyboardInterrupt:
            logger.info("Ingestion interrupted by user.")
        finally:
            cap.release()
            logger.info(
                f"CCTV Ingestion ended. Total frames read: {frame_count}, "
                f"Frames inspected: {inspected_count}, Flagged evidence events: {flagged_count}"
            )


def main():
    parser = argparse.ArgumentParser(description="RoadGuard CCTV & IP Camera Stream Ingestion Adapter")
    parser.add_argument("--stream", type=str, default=os.getenv("CCTV_STREAM_URL", ""),
                        help="RTSP/HTTP/Video file URL (or mock sample path)")
    parser.add_argument("--camera-id", type=str, default=os.getenv("CCTV_CAMERA_ID", "CAM-PWD-001"),
                        help="Camera Identifier")
    parser.add_argument("--location", type=str, default=os.getenv("CCTV_LOCATION_NAME", "Main Ring Road - Sector 4"),
                        help="Location / corridor description")
    parser.add_argument("--lat", type=float, default=float(os.getenv("CCTV_LATITUDE", "12.9716")),
                        help="Latitude coordinate")
    parser.add_argument("--lon", type=float, default=float(os.getenv("CCTV_LONGITUDE", "77.5946")),
                        help="Longitude coordinate")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Sampling interval in seconds (default: 1.0s = 1 FPS)")
    parser.add_argument("--conf", type=float, default=0.15,
                        help="Detection confidence threshold (default: 0.15)")
    parser.add_argument("--model", type=str, default="models/best.pt",
                        help="Path to trained YOLO weights")
    parser.add_argument("--max-frames", type=int, default=None,
                        help="Maximum frames to inspect (useful for tests)")
    parser.add_argument("--test-mock", action="store_true",
                        help="Run verification test against sample road images if no stream URL is provided")

    args = parser.parse_args()

    stream_url = args.stream
    if not stream_url or args.test_mock:
        # Check if sample video or sample images exist
        sample_path = "samples/sample_linear_cracks.jpg"
        if os.path.exists(sample_path):
            logger.info(f"No stream specified. Running mock verification test on {sample_path}")
            stream_url = sample_path
            args.max_frames = 1
        else:
            logger.error("No stream URL provided and no sample images found. Exiting.")
            sys.exit(1)

    ingestion = CCTVStreamIngestion(
        stream_url=stream_url,
        camera_id=args.camera_id,
        location_name=args.location,
        latitude=args.lat,
        longitude=args.lon,
        sample_interval_sec=args.interval,
        conf_threshold=args.conf,
        model_path=args.model
    )

    ingestion.run(max_frames=args.max_frames)


if __name__ == "__main__":
    main()
