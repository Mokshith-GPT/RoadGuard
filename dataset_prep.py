"""
RoadGuard - Dataset Preparation Utility (RDD2022 to YOLO Converter)
Converts Pascal VOC XML annotations from the Road Damage Dataset (RDD2022) into YOLO format.
"""

import os
import glob
import xml.etree.ElementTree as ET
import shutil
from typing import Dict

# RDD2022 Class Mapping
CLASS_MAPPING: Dict[str, int] = {
    "D00": 0,  # Longitudinal Crack
    "D10": 1,  # Transverse Crack
    "D20": 2,  # Alligator Crack
    "D40": 3   # Pothole
}


def convert_voc_xml_to_yolo(xml_file: str, img_width: int, img_height: int) -> list:
    """Extracts bounding boxes from VOC XML and converts to normalized YOLO format [class_id, x_center, y_center, width, height]."""
    tree = ET.parse(xml_file)
    root = tree.getroot()
    yolo_lines = []

    for obj in root.findall("object"):
        name = obj.find("name").text
        if name not in CLASS_MAPPING:
            continue

        cls_id = CLASS_MAPPING[name]
        bndbox = obj.find("bndbox")
        xmin = float(bndbox.find("xmin").text)
        ymin = float(bndbox.find("ymin").text)
        xmax = float(bndbox.find("xmax").text)
        ymax = float(bndbox.find("ymax").text)

        # Convert to YOLO normalized format
        x_center = ((xmin + xmax) / 2.0) / img_width
        y_center = ((ymin + ymax) / 2.0) / img_height
        box_w = (xmax - xmin) / img_width
        box_h = (ymax - ymin) / img_height

        # Clamp between 0.0 and 1.0
        x_center = max(0.0, min(1.0, x_center))
        y_center = max(0.0, min(1.0, y_center))
        box_w = max(0.0, min(1.0, box_w))
        box_h = max(0.0, min(1.0, box_h))

        yolo_lines.append(f"{cls_id} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}")

    return yolo_lines


def prepare_dataset_splits(
    source_xml_dir: str,
    source_img_dir: str,
    target_dataset_dir: str = "dataset"
):
    """Organizes images and labels into train/val splits for YOLO training."""
    print(f"Preparing dataset from {source_img_dir} into {target_dataset_dir}...")
    train_img_dir = os.path.join(target_dataset_dir, "images", "train")
    train_lbl_dir = os.path.join(target_dataset_dir, "labels", "train")
    os.makedirs(train_img_dir, exist_ok=True)
    os.makedirs(train_lbl_dir, exist_ok=True)

    xml_files = glob.glob(os.path.join(source_xml_dir, "*.xml"))
    converted_count = 0

    for xml_path in xml_files:
        base_name = os.path.splitext(os.path.basename(xml_path))[0]
        img_path = os.path.join(source_img_dir, f"{base_name}.jpg")
        if not os.path.exists(img_path):
            continue

        # In RDD2022 standard resolution is usually known or read via PIL
        try:
            import cv2
            img = cv2.imread(img_path)
            if img is None:
                continue
            h, w = img.shape[:2]
        except Exception:
            h, w = 600, 600

        yolo_annotations = convert_voc_xml_to_yolo(xml_path, w, h)
        if yolo_annotations:
            # Save label
            lbl_file = os.path.join(train_lbl_dir, f"{base_name}.txt")
            with open(lbl_file, "w") as f:
                f.write("\n".join(yolo_annotations))
            # Copy image
            shutil.copy(img_path, os.path.join(train_img_dir, f"{base_name}.jpg"))
            converted_count += 1

    print(f"Successfully converted and copied {converted_count} annotated images into YOLO format!")


if __name__ == "__main__":
    print("RDD2022 Dataset Preparation Utility ready.")
    print("Usage: prepare_dataset_splits('path/to/annotations', 'path/to/images')")
