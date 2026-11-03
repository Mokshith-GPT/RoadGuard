"""
RoadGuard - Sample Road Image Generator
Generates realistic synthetic asphalt road images with potholes and cracks
for testing and immediate live demonstration without external downloads.
"""

import cv2
import numpy as np
import os


def generate_synthetic_road_sample(output_path: str, damage_types: list = ["pothole", "longitudinal"]):
    """
    Synthesizes a realistic road surface with simulated asphalt texture and specified damage.
    """
    width, height = 640, 640
    # 1. Base asphalt texture (gray with noise)
    base_color = 110  # medium asphalt gray
    texture = np.random.normal(base_color, 14, (height, width)).astype(np.float32)
    
    # Add road lane markings (white/yellow dashed line)
    cv2.line(texture, (width // 2, 0), (width // 2, height), 200, 4)

    # Convert to 3-channel uint8
    texture = np.clip(texture, 0, 255).astype(np.uint8)
    road_bgr = cv2.cvtColor(texture, cv2.COLOR_GRAY2BGR)

    # 2. Add damage patterns
    for dtype in damage_types:
        if dtype == "pothole":
            # Solid dark cohesive depression
            center = (np.random.randint(260, 380), np.random.randint(340, 460))
            axes = (np.random.randint(65, 95), np.random.randint(45, 75))
            angle = np.random.randint(-30, 30)
            
            # Draw dark crater with rough perimeter
            cv2.ellipse(road_bgr, center, axes, angle, 0, 360, (30, 25, 20), -1)
            # Subtle inner variation
            cv2.ellipse(road_bgr, center, (int(axes[0]*0.75), int(axes[1]*0.75)), angle, 0, 360, (20, 18, 15), -1)

        elif dtype == "longitudinal":
            # Vertical jagged crack
            start_x = np.random.randint(180, 260)
            start_y = np.random.randint(250, 320)
            curr_x, curr_y = start_x, start_y
            for _ in range(35):
                next_x = curr_x + np.random.randint(-3, 4)
                next_y = curr_y + np.random.randint(8, 14)
                cv2.line(road_bgr, (curr_x, curr_y), (next_x, next_y), (35, 30, 25), 3)
                curr_x, curr_y = next_x, next_y
                if curr_y >= height - 20:
                    break

        elif dtype == "transverse":
            # Horizontal jagged crack across lane
            start_x = np.random.randint(120, 180)
            start_y = np.random.randint(350, 450)
            curr_x, curr_y = start_x, start_y
            for _ in range(40):
                next_x = curr_x + np.random.randint(8, 15)
                next_y = curr_y + np.random.randint(-3, 4)
                cv2.line(road_bgr, (curr_x, curr_y), (next_x, next_y), (30, 28, 25), 3)
                curr_x, curr_y = next_x, next_y
                if curr_x >= width - 120:
                    break

        elif dtype == "alligator":
            # Interconnected mesh pattern
            grid_ox = np.random.randint(340, 450)
            grid_oy = np.random.randint(320, 420)
            for i in range(4):
                for j in range(4):
                    pt1 = (grid_ox + i * 25 + np.random.randint(-4, 5), grid_oy + j * 20 + np.random.randint(-4, 5))
                    pt2 = (grid_ox + (i+1) * 25 + np.random.randint(-4, 5), grid_oy + j * 20 + np.random.randint(-4, 5))
                    pt3 = (grid_ox + i * 25 + np.random.randint(-4, 5), grid_oy + (j+1) * 20 + np.random.randint(-4, 5))
                    cv2.line(road_bgr, pt1, pt2, (40, 35, 30), 2)
                    cv2.line(road_bgr, pt1, pt3, (40, 35, 30), 2)

    # Apply subtle blur to blend
    road_bgr = cv2.GaussianBlur(road_bgr, (3, 3), 0)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, road_bgr)
    print(f"Generated sample: {output_path}")


if __name__ == "__main__":
    samples_dir = "samples"
    generate_synthetic_road_sample(os.path.join(samples_dir, "sample_pothole_critical.jpg"), ["pothole"])
    generate_synthetic_road_sample(os.path.join(samples_dir, "sample_linear_cracks.jpg"), ["longitudinal", "transverse"])
    generate_synthetic_road_sample(os.path.join(samples_dir, "sample_alligator_fatigue.jpg"), ["alligator"])
    generate_synthetic_road_sample(os.path.join(samples_dir, "sample_multi_damage.jpg"), ["pothole", "longitudinal", "alligator"])
