"""
RoadGuard - YOLO Training Script
Trains a lightweight YOLOv8 nano model on the 4 road damage classes (D00, D10, D20, D40).
"""

import os

# Sample dataset configuration YAML
DATA_YAML_CONTENT = """# RoadGuard Dataset Configuration
path: ../dataset
train: images/train
val: images/train  # For mini-project can use split or subset

names:
  0: D00_Longitudinal_Crack
  1: D10_Transverse_Crack
  2: D20_Alligator_Crack
  3: D40_Pothole
"""


def train():
    try:
        from ultralytics import YOLO
    except ImportError:
        print("Ultralytics not installed. Install via: pip install ultralytics")
        return

    # Write data.yaml if not present
    yaml_path = "dataset_config.yaml"
    with open(yaml_path, "w") as f:
        f.write(DATA_YAML_CONTENT)
    print(f"Created {yaml_path}")

    # Load baseline nano model
    model = YOLO("yolov8n.pt")

    # Train for 30 epochs
    print("Starting YOLOv8 training on Road Damage Dataset...")
    results = model.train(
        data=yaml_path,
        epochs=30,
        imgsz=640,
        batch=16,
        name="roadguard_yolo",
        project="models",
        save=True
    )
    print("Training complete! Best weights saved to models/roadguard_yolo/weights/best.pt")


if __name__ == "__main__":
    print("Run `python train_yolo.py` when your dataset folder has been prepared.")
