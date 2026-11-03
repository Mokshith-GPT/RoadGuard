"""
RoadGuard - Streamlit Interactive Web Application
Intelligent Road Damage Detection, Segmentation and Severity Estimation
"""

import streamlit as st
import cv2
import numpy as np
import os
import pandas as pd
from PIL import Image
import tempfile
import time

from modules.image_acquisition import ImageAcquisition
from modules.preprocessing import ImagePreprocessor
from modules.damage_detection import DamageDetector, DAMAGE_CLASSES
from modules.segmentation_severity import SeverityEstimator
from modules.visualization_report import VisualizerAndReporter

# Page configuration
st.set_page_config(
    page_title="RoadGuard | Road Damage Assessment System",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 12px;
        border-left: 5px solid #2563EB;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .severity-pill-high {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
    }
    .severity-pill-med {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
    }
    .severity-pill-low {
        background-color: #D1FAE5;
        color: #065F46;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


def main():
    st.markdown('<div class="main-title">🛣️ RoadGuard: Intelligent Pavement Distress Monitoring</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Automated Road Damage Detection, Pixel Segmentation & Multi-Tier Severity Indexing | CVIP Mini-Project</div>', unsafe_allow_html=True)

    # Sidebar Controls
    st.sidebar.image("https://img.icons8.com/color/96/road.png", width=70)
    st.sidebar.title("System Controls")

    input_mode = st.sidebar.radio(
        "Select Input Source",
        ["Use Preloaded Sample", "Upload Custom Image", "Video Stream / File"]
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Preprocessing & Detection")
    clahe_clip = st.sidebar.slider("CLAHE Clip Limit (Contrast)", 1.0, 5.0, 3.0, 0.5)
    apply_roi = st.sidebar.checkbox("Apply Road Corridor ROI Mask", value=True)
    conf_thresh = st.sidebar.slider("Detection Confidence Threshold", 0.10, 0.90, 0.25, 0.05)

    st.sidebar.markdown("---")
    st.sidebar.subheader("📐 Severity Indexing Bounds")
    low_thresh = st.sidebar.slider("Low / Medium Boundary (%)", 5.0, 20.0, 10.0, 1.0)
    med_thresh = st.sidebar.slider("Medium / High Boundary (%)", 20.0, 50.0, 30.0, 1.0)

    # Initialize Modules
    preprocessor = ImagePreprocessor(
        target_size=(640, 640),
        clahe_clip_limit=clahe_clip,
        apply_road_roi=apply_roi
    )
    detector = DamageDetector(model_path="models/best.pt", conf_threshold=conf_thresh)
    estimator = SeverityEstimator(low_threshold=low_thresh, medium_threshold=med_thresh)

    # Display active backend badge
    backend_badge = "Deep Learning (YOLOv8)" if detector.backend == "yolo" else "Computer Vision Feature Pipeline"
    st.sidebar.info(f"Active Engine: **{backend_badge}**")

    # Image Acquisition
    image_bgr = None
    source_name = ""

    if input_mode == "Use Preloaded Sample":
        sample_files = {
            "Critical Pothole": "samples/sample_pothole_critical.jpg",
            "Linear Cracks (Longitudinal & Transverse)": "samples/sample_linear_cracks.jpg",
            "Alligator Structural Fatigue": "samples/sample_alligator_fatigue.jpg",
            "Multi-Damage Pavement Corridor": "samples/sample_multi_damage.jpg"
        }
        choice = st.selectbox("Choose a Benchmark Sample", list(sample_files.keys()))
        selected_path = sample_files[choice]
        if os.path.exists(selected_path):
            success, image_bgr, msg = ImageAcquisition.load_image(selected_path)
            source_name = choice
        else:
            st.error(f"Sample file not found: {selected_path}. Run generate_samples.py first.")

    elif input_mode == "Upload Custom Image":
        uploaded_file = st.file_uploader("Upload a road image (JPG, PNG, JPEG)", type=["jpg", "jpeg", "png"])
        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            success, image_bgr, msg = ImageAcquisition.load_image(file_bytes)
            source_name = uploaded_file.name

    elif input_mode == "Video Stream / File":
        uploaded_video = st.file_uploader("Upload road footage (MP4, AVI, MOV)", type=["mp4", "avi", "mov"])
        if uploaded_video is not None:
            tfile = tempfile.NamedTemporaryFile(delete=False)
            tfile.write(uploaded_video.read())
            st.video(tfile.name)
            if st.button("Process Keyframes from Video"):
                frames = list(ImageAcquisition.extract_video_frames(tfile.name, frame_interval=30, max_frames=5))
                if frames:
                    st.success(f"Extracted {len(frames)} keyframes for inspection.")
                    image_bgr = frames[0][2]
                    source_name = f"{uploaded_video.name} (Keyframe 0)"

    # Process and Render
    if image_bgr is not None:
        valid, vmsg = ImageAcquisition.validate_image(image_bgr)
        if not valid:
            st.error(vmsg)
            return

        with st.spinner("Analyzing pavement surface..."):
            start_time = time.time()
            prep_data = preprocessor.process(image_bgr)
            detections = detector.detect(prep_data)
            analysis = estimator.process(prep_data, detections)
            latency_ms = (time.time() - start_time) * 1000

        # High-level Metrics Row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Defects Found", len(analysis["detections"]))
        with col2:
            st.metric("Road Area Damaged", f"{analysis['damage_area_percentage']:.2f}%")
        with col3:
            sev_tier = analysis["overall_severity"]
            st.metric("Overall Road Severity", sev_tier, delta=f"Score: {analysis['overall_score']}/100")
        with col4:
            st.metric("Inference Latency", f"{latency_ms:.1f} ms", f"{1000/max(latency_ms, 1):.1f} FPS")

        # Tabs for detailed inspection
        tab1, tab2, tab3 = st.tabs(["🖼️ Visual Inspection & Overlay", "📊 Damage Analytics", "📄 Audit Report & Export"])

        with tab1:
            st.subheader("Pavement Inspection Views")
            view_mode = st.radio(
                "Inspection View Mode",
                ["Segmented HUD Overlay", "Side-by-Side Pipeline Comparison (Input ➔ CLAHE ➔ Overlay)"],
                horizontal=True
            )

            c_boxes = st.checkbox("Show Bounding Boxes", value=True)
            c_masks = st.checkbox("Show Translucent Segmentation Masks", value=True)
            c_hud = st.checkbox("Show Telemetry Banner", value=True)

            overlay = VisualizerAndReporter.render_overlay(
                prep_data["enhanced"],
                analysis,
                show_masks=c_masks,
                show_boxes=c_boxes,
                show_hud=c_hud
            )

            if view_mode == "Segmented HUD Overlay":
                # Convert BGR to RGB for Streamlit
                overlay_rgb = cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)
                st.image(overlay_rgb, caption=f"Analyzed View: {source_name}", use_container_width=True)
            else:
                sbs = VisualizerAndReporter.create_side_by_side_comparison(
                    prep_data["resized"], prep_data["enhanced"], overlay
                )
                sbs_rgb = cv2.cvtColor(sbs, cv2.COLOR_BGR2RGB)
                st.image(sbs_rgb, caption="3-Stage Computer Vision Pipeline: Original Input | CLAHE Enhanced | Segmented Telemetry", use_container_width=True)

        with tab2:
            st.subheader("Statistical Breakdown by Distress Category")
            counts = analysis["damage_counts"]
            df_counts = pd.DataFrame([
                {"Category Code": "D00", "Damage Type": "Longitudinal Crack", "Instances": counts["D00"]},
                {"Category Code": "D10", "Damage Type": "Transverse Crack", "Instances": counts["D10"]},
                {"Category Code": "D20", "Damage Type": "Alligator Crack", "Instances": counts["D20"]},
                {"Category Code": "D40", "Damage Type": "Pothole (Cavity)", "Instances": counts["D40"]},
            ])
            
            c_chart, c_table = st.columns([1, 1])
            with c_chart:
                st.bar_chart(df_counts.set_index("Damage Type")["Instances"])
            with c_table:
                st.dataframe(df_counts, hide_index=True, use_container_width=True)

            if analysis["detections"]:
                st.subheader("Individual Defect Measurement Ledger")
                det_rows = []
                for idx, d in enumerate(analysis["detections"], start=1):
                    det_rows.append({
                        "ID": idx,
                        "Type": f"{d['class_code']} - {d['class_name']}",
                        "Confidence": d["confidence"],
                        "BBox (x,y,w,h)": str(d["bbox"]),
                        "Damaged Pixels": d["damage_pixels"],
                        "Local Area %": f"{d['bbox_damage_percentage']}%",
                        "Severity Tier": d["severity_tier"],
                        "Hazard Score": d["severity_score"]
                    })
                st.dataframe(pd.DataFrame(det_rows), hide_index=True, use_container_width=True)

        with tab3:
            st.subheader("Road Condition Audit Report")
            rep_files = VisualizerAndReporter.generate_audit_report(analysis)
            
            st.success(f"Audit log generated at {rep_files['csv']}")
            
            with open(rep_files["csv"], "rb") as f:
                st.download_button(
                    "📥 Download Inspection CSV Report",
                    data=f,
                    file_name=os.path.basename(rep_files["csv"]),
                    mime="text/csv"
                )

            with open(rep_files["json"], "rb") as f:
                st.download_button(
                    "📥 Download Inspection JSON Audit",
                    data=f,
                    file_name=os.path.basename(rep_files["json"]),
                    mime="application/json"
                )

            st.markdown("### Executive Summary")
            st.info(f"""
            - **Evaluation Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S')}
            - **Source Media:** {source_name}
            - **Overall Road Condition:** **{analysis['overall_severity']}** (Distress Score: {analysis['overall_score']}/100)
            - **Total Drivable Corridor Area Damaged:** **{analysis['damage_area_percentage']:.2f}%**
            - **High-Risk Entities (Potholes):** {counts['D40']} detected
            - **Structural Cracks (Alligator / Linear):** {counts['D00'] + counts['D10'] + counts['D20']} detected
            """)

    else:
        st.info("👈 Please select a preloaded sample or upload an image from the sidebar to begin analysis.")


if __name__ == "__main__":
    main()
