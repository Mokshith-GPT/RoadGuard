# 🛣️ RoadGuard: Intelligent Road Damage Detection, Segmentation & Severity Estimation

> **Subject:** Computer Vision & Image Processing (CVIP) Mini-Project  
> **Proposed Short Name:** RoadGuard  
> **Key Technologies:** Python, OpenCV, YOLO, NumPy, Streamlit, Digital Image Processing

---

## 📌 1. Project Overview

**RoadGuard** is an automated pavement distress assessment pipeline that transcends conventional "bounding-box-only" pothole detection. Instead of simply tagging damage with a box, the system extracts the exact pixel-level morphology of road defects, computes the actual percentage of the road surface compromised ($A_d$), and assigns a calibrated structural severity index (**Low**, **Medium**, or **High**).

### 🎯 Key Differentiators (Why Professors Approve This)
* **Not Just YOLO:** While deep learning identifies the general defect location, the core evaluation is powered by **classical computer vision & digital image processing** (CLAHE local contrast equalization, bilateral edge-preserving filtering, trapezoidal vanishing-point road corridor isolation, Otsu adaptive thresholding, and morphological contour analysis).
* **Quantitative Surface Assessment:** Computes metric road damage coverage:
  $$A_d = \frac{N_d}{N_r} \times 100$$
  where $N_d$ is the count of damaged pixels and $N_r$ is the drivable road surface pixels.
* **Multi-Class Taxonomy:** Detects and classifies 4 standard pavement distress types:
  * `D00`: Longitudinal Linear Cracks (parallel to traffic)
  * `D10`: Transverse Linear Cracks (perpendicular to traffic)
  * `D20`: Alligator / Fatigue Cracks (interconnected mesh)
  * `D40`: Potholes / Cavities (structural surface depressions)
* **Interactive Telemetry Dashboard:** A live web-based HUD built in Streamlit featuring side-by-side computer vision pipeline comparisons, real-time analytics, and automated CSV/JSON audit report exports.

---

## 📸 Pipeline Demonstration

### 3-Stage Computer Vision Pipeline
![Pipeline Demo](assets/pipeline_demo.jpg)

### Augmented Reality HUD & Damage Segmentation
![Overlay Demo](assets/overlay_demo.jpg)

---

## 🏛️ 2. Five System Modules Architecture

```
┌─────────────────────────────────────────────────────────────┐
│             MODULE 1: ROAD IMAGE ACQUISITION                │
│    (Loads JPG/PNG images, MP4 video streams, camera feeds)  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              MODULE 2: IMAGE PREPROCESSING                  │
│    (Resizing, Bilateral Denoising, CLAHE, Road ROI Mask)    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             MODULE 3: ROAD DAMAGE DETECTION                 │
│      (YOLOv8 Deep Learning + CV Feature Heuristic Engine)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│     MODULE 4: DAMAGE SEGMENTATION & SEVERITY ESTIMATION     │
│   (Adaptive Thresholding, Contours, Pixel Area %, Scoring)  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│       MODULE 5: VISUALIZATION & AUDIT REPORT GENERATION     │
│    (Color-Coded Masks, HUD Banner, Side-by-Side, CSV/JSON)  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 3. Repository File Structure

```
RoadGuard/
├── modules/
│   ├── __init__.py                  # Package exports
│   ├── image_acquisition.py         # Module 1: Image & video frame ingestion
│   ├── preprocessing.py             # Module 2: CLAHE, bilateral filter, road ROI
│   ├── damage_detection.py          # Module 3: YOLO & CV feature detection engine
│   ├── segmentation_severity.py     # Module 4: Pixel mask segmentation & severity
│   └── visualization_report.py      # Module 5: Overlay HUD & report generator
├── models/                          # Storage for trained weights (e.g. best.pt)
├── samples/                         # Preloaded test road images
├── outputs/                         # Exported CSV/JSON audit logs & images
├── app.py                           # Full interactive Streamlit Web Dashboard
├── test_pipeline.py                 # Automated end-to-end verification test
├── generate_samples.py              # Synthetic benchmark road image generator
├── dataset_prep.py                  # RDD2022 VOC XML to YOLO converter
├── train_yolo.py                    # YOLOv8 model training script
├── requirements.txt                 # Python dependencies
└── README.md                        # Documentation
```

---

## 🚀 4. How to Run & Demonstrate

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Generate Benchmark Samples & Verify Pipeline
```bash
# Generate sample test road images
python generate_samples.py

# Run the 5-module verification test
python test_pipeline.py
```

### Step 3: Launch the Streamlit Web Application
```bash
streamlit run app.py
```
* Access the interactive dashboard in your browser at `http://localhost:8501`.
* Select any benchmark sample or upload your own road photo.
* Inspect the **Side-by-Side Pipeline Comparison**, view the **Damage Analytics charts**, and click **Download Inspection CSV Report** to demonstrate a complete real-world road survey.

---

## 🎤 5. Viva / Presentation Talking Points

When presenting to your guide and external examiners:
1. **Explain the Limitation of Pure YOLO:** 
   > *"If we only used YOLO, we would only get rectangular bounding boxes. A bounding box around a diagonal crack consists of 85% healthy asphalt and only 15% damaged pixels. Our project extracts the exact damaged pixels via Module 4 adaptive thresholding and contour integration, giving the true damage area ratio."*
2. **Explain the Role of CLAHE in Preprocessing:**
   > *"Roads suffer from extreme lighting variations—such as shadows cast by trees, bridges, and vehicles. Standard global thresholding fails under shadows. By converting to Lab space and applying CLAHE to the Lightness channel, we normalize local contrast and prevent shadow edges from triggering false alarms."*
3. **Explain the Severity Rule:**
   > *"We compute the Road Damage Severity Index based on the affected surface area combined with defect hazard weighting. Potholes present an immediate structural hazard to vehicular suspensions and tire integrity, so they are assigned a 1.4x weighting factor compared to superficial linear cracks."*
