"""
RoadGuard - End-to-End Pipeline Verification Test
Tests all five modules in sequence on sample road images.
"""

import os
import cv2
from modules.image_acquisition import ImageAcquisition
from modules.preprocessing import ImagePreprocessor
from modules.damage_detection import DamageDetector
from modules.segmentation_severity import SeverityEstimator
from modules.visualization_report import VisualizerAndReporter


def run_pipeline_test(sample_path: str):
    print(f"\n=======================================================")
    print(f"Testing Pipeline on: {sample_path}")
    print(f"=======================================================")

    # Module 1: Image Acquisition
    success, image, msg = ImageAcquisition.load_image(sample_path)
    assert success, f"Acquisition failed: {msg}"
    print(f"[Module 1 PASS] {msg} Shape: {image.shape}")

    # Module 2: Preprocessing
    preprocessor = ImagePreprocessor(target_size=(640, 640), clahe_clip_limit=3.0)
    prep_data = preprocessor.process(image)
    print(f"[Module 2 PASS] Preprocessed. Enhanced shape: {prep_data['enhanced'].shape}")

    # Module 3: Damage Detection
    detector = DamageDetector(model_path="models/best.pt", conf_threshold=0.15)
    detections = detector.detect(prep_data)
    print(f"[Module 3 PASS] Detected {len(detections)} damage entities.")
    for d in detections:
        print(f"   -> [{d['class_code']}] {d['class_name']} (Conf: {d['confidence']}, BBox: {d['bbox']})")

    # Module 4: Segmentation & Severity Estimation
    estimator = SeverityEstimator(low_threshold=10.0, medium_threshold=30.0)
    analysis = estimator.process(prep_data, detections)
    print(f"[Module 4 PASS] Damage Area: {analysis['damage_area_percentage']}% | Severity: {analysis['overall_severity']} (Score: {analysis['overall_score']})")

    # Module 5: Visualization & Report Generation
    overlay = VisualizerAndReporter.render_overlay(prep_data["enhanced"], analysis)
    side_by_side = VisualizerAndReporter.create_side_by_side_comparison(
        prep_data["resized"], prep_data["enhanced"], overlay
    )

    out_overlay_path = os.path.join("outputs", "test_overlay.jpg")
    out_sbs_path = os.path.join("outputs", "test_side_by_side.jpg")
    os.makedirs("outputs", exist_ok=True)
    cv2.imwrite(out_overlay_path, overlay)
    cv2.imwrite(out_sbs_path, side_by_side)

    reports = VisualizerAndReporter.generate_audit_report(analysis, output_dir="outputs")
    print(f"[Module 5 PASS] Rendered overlays and generated audit reports:")
    print(f"   CSV:  {reports['csv']}")
    print(f"   JSON: {reports['json']}")
    print("ALL 5 MODULES PASSED SYSTEM VERIFICATION!")


if __name__ == "__main__":
    for sample in ["samples/sample_multi_damage.jpg", "samples/sample_linear_cracks.jpg"]:
        if os.path.exists(sample):
            run_pipeline_test(sample)
