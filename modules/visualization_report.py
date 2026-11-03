"""
RoadGuard - Module 5: Visualization and Report Generation
Renders color-coded damage overlays, HUD telemetry banners, side-by-side comparisons,
and exports structured road condition audit reports.
"""

import cv2
import numpy as np
import os
import json
import csv
from datetime import datetime
from typing import Dict, Any, Tuple, Optional


class VisualizerAndReporter:
    """Renders overlays, HUD banners, side-by-side panels, and audit reports."""

    SEVERITY_COLORS = {
        "Low": (0, 220, 0),       # Green (BGR)
        "Medium": (0, 165, 255),  # Orange (BGR)
        "High": (0, 0, 240),      # Red (BGR)
        "Optimal / Healthy": (255, 255, 255)
    }

    @classmethod
    def render_overlay(
        cls,
        image_bgr: np.ndarray,
        analysis_data: Dict[str, Any],
        show_masks: bool = True,
        show_boxes: bool = True,
        show_hud: bool = True
    ) -> np.ndarray:
        """
        Creates an augmented reality road view with translucent damage masks,
        bounding boxes, and an on-screen telemetry banner.
        """
        canvas = image_bgr.copy()
        h, w = canvas.shape[:2]

        # 1. Draw translucent color-coded segmentation mask
        if show_masks:
            mask_layer = np.zeros_like(canvas)
            for det in analysis_data["detections"]:
                tier = det.get("severity_tier", "Low")
                color = cls.SEVERITY_COLORS.get(tier, (0, 0, 255))
                contours = det.get("contours", [])
                cv2.drawContours(mask_layer, contours, -1, color, thickness=cv2.FILLED)

            # Alpha blend mask with original image
            cv2.addWeighted(mask_layer, 0.45, canvas, 1.0, 0, canvas)

            # Draw crisp contour borders
            for det in analysis_data["detections"]:
                tier = det.get("severity_tier", "Low")
                color = cls.SEVERITY_COLORS.get(tier, (0, 0, 255))
                contours = det.get("contours", [])
                cv2.drawContours(canvas, contours, -1, color, thickness=2)

        # 2. Draw Bounding Boxes with Class and Severity Tags
        if show_boxes:
            for det in analysis_data["detections"]:
                x, y, bw, bh = det["bbox"]
                box_color = det.get("color", (0, 255, 255))
                tier = det.get("severity_tier", "Low")
                score = det.get("severity_score", 0.0)
                code = det.get("class_code", "Defect")
                name = det.get("class_name", "Damage")
                conf = det.get("confidence", 0.0)

                # Draw rectangle
                cv2.rectangle(canvas, (x, y), (x + bw, y + bh), box_color, 2)

                # Label tag
                label = f"{code} {name} | {tier} ({score}%)"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)

                # Header background
                cv2.rectangle(canvas, (x, max(0, y - th - 8)), (x + tw + 6, max(th + 8, y)), box_color, -1)
                cv2.putText(
                    canvas, label, (x + 3, max(12, y - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA
                )

        # 3. Telemetry HUD Banner at Top
        if show_hud:
            banner_h = 50
            banner = np.zeros((banner_h, w, 3), dtype=np.uint8)
            banner[:] = (25, 25, 25)  # Dark slate gray

            sev = analysis_data.get("overall_severity", "N/A")
            sev_color = cls.SEVERITY_COLORS.get(sev, (255, 255, 255))
            pct = analysis_data.get("damage_area_percentage", 0.0)
            cnt = len(analysis_data.get("detections", []))

            # Title
            cv2.putText(banner, "RoadGuard Telemetry", (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(banner, f"Defects: {cnt} | Affected Area: {pct:.2f}%", (12, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA)

            # Severity Pill
            sev_text = f"SEVERITY: {sev.upper()}"
            (stw, sth), _ = cv2.getTextSize(sev_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            pill_x = w - stw - 24
            cv2.rectangle(banner, (pill_x, 10), (w - 12, 40), sev_color, -1)
            cv2.putText(banner, sev_text, (pill_x + 6, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 0), 2, cv2.LINE_AA)

            # Stack banner on canvas
            canvas = np.vstack([banner, canvas])

        return canvas

    @classmethod
    def create_side_by_side_comparison(
        cls,
        original_resized: np.ndarray,
        preprocessed_enhanced: np.ndarray,
        annotated_overlay: np.ndarray
    ) -> np.ndarray:
        """
        Combines original, CLAHE enhanced, and annotated detection views into a single panel.
        """
        h, w = original_resized.shape[:2]
        # Ensure heights match (annotated might have HUD banner)
        ann_h, ann_w = annotated_overlay.shape[:2]
        if ann_h != h:
            annotated_resized = cv2.resize(annotated_overlay, (w, h))
        else:
            annotated_resized = annotated_overlay

        # Label each view
        v1 = original_resized.copy()
        v2 = preprocessed_enhanced.copy()
        v3 = annotated_resized.copy()

        cv2.putText(v1, "1. Input Camera", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(v2, "2. Preprocessed (CLAHE)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(v3, "3. RoadGuard Segmented HUD", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

        return np.hstack([v1, v2, v3])

    @staticmethod
    def generate_audit_report(
        analysis_data: Dict[str, Any],
        output_dir: str = "outputs",
        filename_prefix: str = "roadguard_audit"
    ) -> Dict[str, str]:
        """
        Exports both CSV and JSON inspection records.
        """
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(output_dir, f"{filename_prefix}_{timestamp}.csv")
        json_path = os.path.join(output_dir, f"{filename_prefix}_{timestamp}.json")

        # 1. Write CSV
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Defect ID", "Class Code", "Damage Type", "Confidence", "Damage Pixels", "BBox Area %", "Severity Tier", "Severity Score"])
            for idx, det in enumerate(analysis_data.get("detections", []), start=1):
                writer.writerow([
                    idx,
                    det.get("class_code"),
                    det.get("class_name"),
                    det.get("confidence"),
                    det.get("damage_pixels"),
                    det.get("bbox_damage_percentage"),
                    det.get("severity_tier"),
                    det.get("severity_score")
                ])
            writer.writerow([])
            writer.writerow(["SUMMARY METRIC", "VALUE"])
            writer.writerow(["Overall Severity", analysis_data.get("overall_severity")])
            writer.writerow(["Overall Severity Score", analysis_data.get("overall_score")])
            writer.writerow(["Total Damaged Pixels", analysis_data.get("total_damaged_pixels")])
            writer.writerow(["Road Damage Area %", analysis_data.get("damage_area_percentage")])

        # 2. Write JSON (excluding raw non-serializable contours/masks)
        serializable = {
            "timestamp": timestamp,
            "overall_severity": analysis_data.get("overall_severity"),
            "overall_score": analysis_data.get("overall_score"),
            "damage_area_percentage": analysis_data.get("damage_area_percentage"),
            "total_damaged_pixels": analysis_data.get("total_damaged_pixels"),
            "total_road_pixels": analysis_data.get("total_road_pixels"),
            "damage_counts": analysis_data.get("damage_counts"),
            "detections": [
                {
                    "class_code": d.get("class_code"),
                    "class_name": d.get("class_name"),
                    "confidence": d.get("confidence"),
                    "bbox": d.get("bbox"),
                    "damage_pixels": d.get("damage_pixels"),
                    "bbox_damage_percentage": d.get("bbox_damage_percentage"),
                    "severity_tier": d.get("severity_tier"),
                    "severity_score": d.get("severity_score")
                }
                for d in analysis_data.get("detections", [])
            ]
        }
        with open(json_path, mode="w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=4)

        return {"csv": csv_path, "json": json_path}
