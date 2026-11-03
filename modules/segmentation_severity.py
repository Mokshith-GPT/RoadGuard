"""
RoadGuard - Module 4: Damage Segmentation and Severity Estimation
Performs pixel-level contour segmentation, computes damage area percentage,
and evaluates road condition severity (Low, Medium, High).
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Tuple


class SeverityEstimator:
    """Estimates pixel-level damage masks, area percentages, and hazard tiers."""

    def __init__(
        self,
        low_threshold: float = 10.0,
        medium_threshold: float = 30.0,
        morph_kernel_size: int = 3
    ):
        self.low_threshold = low_threshold
        self.medium_threshold = medium_threshold
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (morph_kernel_size, morph_kernel_size))

    def segment_defect(self, image_gray: np.ndarray, bbox: List[int]) -> Tuple[np.ndarray, List[np.ndarray], int]:
        """
        Segments damaged pixels inside the given bounding box [x, y, w, h].
        Returns:
            defect_mask: binary mask of size (h, w)
            contours: list of segmented contours inside ROI coordinates
            pixel_count: number of damaged pixels in the ROI
        """
        x, y, w, h = bbox
        h_img, w_img = image_gray.shape[:2]

        # Clamp bounding box
        x = max(0, min(x, w_img - 1))
        y = max(0, min(y, h_img - 1))
        w = max(1, min(w, w_img - x))
        h = max(1, min(h, h_img - y))

        roi = image_gray[y:y+h, x:x+w]
        if roi.size == 0:
            return np.zeros((h, w), dtype=np.uint8), [], 0

        # 1. Contrast stretching on the local crop
        norm_roi = cv2.normalize(roi, None, 0, 255, cv2.NORM_MINMAX)

        # 2. Local adaptive thresholding combined with Otsu binarization
        # Invert so darker fracture pixels become foreground (255)
        _, otsu = cv2.threshold(norm_roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        adaptive = cv2.adaptiveThreshold(
            norm_roi, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 3
        )
        combined = cv2.bitwise_and(otsu, adaptive)

        # 3. Morphological closing to seal fissure gaps, opening to purge salt-and-pepper noise
        closed = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, self.kernel, iterations=2)
        opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, self.kernel, iterations=1)

        # 4. Find internal contours
        contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter out negligible single-pixel noise contours
        valid_contours = [c for c in contours if cv2.contourArea(c) > 15]

        # Re-render clean mask
        clean_mask = np.zeros_like(opened)
        cv2.drawContours(clean_mask, valid_contours, -1, 255, thickness=cv2.FILLED)
        pixel_count = int(np.count_nonzero(clean_mask))

        return clean_mask, valid_contours, pixel_count

    def process(
        self,
        preprocessed_data: Dict[str, Any],
        detections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Executes segmentation on all detected defect bounding boxes and computes aggregate severity.
        """
        gray = preprocessed_data["gray"]
        road_mask = preprocessed_data["road_mask"]
        h_img, w_img = gray.shape[:2]

        # Calculate total reference road surface pixels
        total_road_pixels = int(np.count_nonzero(road_mask)) if road_mask is not None else (h_img * w_img)
        if total_road_pixels == 0:
            total_road_pixels = h_img * w_img

        full_damage_mask = np.zeros((h_img, w_img), dtype=np.uint8)
        enriched_detections = []
        total_damage_pixels = 0

        # Type hazard severity weights: Pothole > Alligator > Linear
        class_weights = {
            "D40": 1.4,  # Pothole
            "D20": 1.2,  # Alligator
            "D10": 1.0,  # Transverse
            "D00": 1.0   # Longitudinal
        }

        weighted_defect_severity_sum = 0.0

        for det in detections:
            bbox = det["bbox"]
            x, y, w, h = bbox
            defect_mask, local_cnts, pixel_count = self.segment_defect(gray, bbox)

            # Map local defect mask onto the full frame mask
            y_end = min(y + h, h_img)
            x_end = min(x + w, w_img)
            mask_h = y_end - y
            mask_w = x_end - x

            if mask_h > 0 and mask_w > 0:
                full_damage_mask[y:y_end, x:x_end] = cv2.bitwise_or(
                    full_damage_mask[y:y_end, x:x_end],
                    defect_mask[:mask_h, :mask_w]
                )

            # Shift contours to global frame coordinates
            global_contours = []
            for c in local_cnts:
                shifted = c.copy()
                shifted[:, 0, 0] += x
                shifted[:, 0, 1] += y
                global_contours.append(shifted)

            # Local region damage ratio within its own bounding box
            bbox_area = max(1, w * h)
            bbox_damage_ratio = (pixel_count / bbox_area) * 100.0

            # Local severity
            weight = class_weights.get(det["class_code"], 1.0)
            local_severity_score = min(100.0, bbox_damage_ratio * weight)

            if local_severity_score < self.low_threshold:
                local_tier = "Low"
            elif local_severity_score <= self.medium_threshold:
                local_tier = "Medium"
            else:
                local_tier = "High"

            enriched_det = dict(det)
            enriched_det.update({
                "damage_pixels": pixel_count,
                "bbox_damage_percentage": round(bbox_damage_ratio, 2),
                "severity_tier": local_tier,
                "severity_score": round(local_severity_score, 1),
                "contours": global_contours
            })
            enriched_detections.append(enriched_det)

            total_damage_pixels += pixel_count
            weighted_defect_severity_sum += (local_severity_score * (pixel_count + 1))

        # Overall Road Damage Ratio across entire road surface:
        # A_d = (N_d / N_r) * 100
        actual_damaged_pixels = int(np.count_nonzero(full_damage_mask))
        overall_damage_area_pct = (actual_damaged_pixels / total_road_pixels) * 100.0

        # Aggregate Road Severity Tier
        if overall_damage_area_pct < 1.0 and len(detections) <= 1:
            overall_severity = "Low"
            overall_score = round(overall_damage_area_pct * 10, 1)
        elif overall_damage_area_pct < 5.0 and not any(d["class_code"] == "D40" for d in detections):
            overall_severity = "Medium"
            overall_score = round(35.0 + overall_damage_area_pct * 6, 1)
        else:
            # Significant damage or major potholes detected
            overall_severity = "High"
            overall_score = min(100.0, round(65.0 + overall_damage_area_pct * 5, 1))

        if len(detections) == 0:
            overall_severity = "Optimal / Healthy"
            overall_score = 0.0

        return {
            "detections": enriched_detections,
            "full_damage_mask": full_damage_mask,
            "total_damaged_pixels": actual_damaged_pixels,
            "total_road_pixels": total_road_pixels,
            "damage_area_percentage": round(overall_damage_area_pct, 2),
            "overall_severity": overall_severity,
            "overall_score": overall_score,
            "damage_counts": {
                "D00": sum(1 for d in detections if d["class_code"] == "D00"),
                "D10": sum(1 for d in detections if d["class_code"] == "D10"),
                "D20": sum(1 for d in detections if d["class_code"] == "D20"),
                "D40": sum(1 for d in detections if d["class_code"] == "D40")
            }
        }
