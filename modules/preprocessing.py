"""
RoadGuard - Module 2: Image Preprocessing
Enhances road imagery via CLAHE, bilateral/Gaussian filtering, and road ROI isolation.
"""

import cv2
import numpy as np
from typing import Tuple, Dict, Any, Optional


class ImagePreprocessor:
    """Preprocesses road images to enhance fracture visibility and suppress lighting artifacts."""

    def __init__(
        self,
        target_size: Tuple[int, int] = (640, 640),
        clahe_clip_limit: float = 3.0,
        clahe_tile_grid_size: Tuple[int, int] = (8, 8),
        blur_kernel_size: int = 5,
        apply_road_roi: bool = True
    ):
        self.target_size = target_size
        self.clahe_clip_limit = clahe_clip_limit
        self.clahe_tile_grid_size = clahe_tile_grid_size
        self.blur_kernel_size = blur_kernel_size
        self.apply_road_roi = apply_road_roi
        self.clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip_limit,
            tileGridSize=self.clahe_tile_grid_size
        )

    def resize(self, image: np.ndarray) -> np.ndarray:
        """Resizes the image to the target dimensions."""
        return cv2.resize(image, self.target_size, interpolation=cv2.INTER_AREA)

    def apply_clahe(self, image: np.ndarray) -> np.ndarray:
        """
        Enhances local contrast using CLAHE on the Lightness (L*) channel in Lab color space.
        Normalizes harsh shadows from trees, bridges, and overhead structures on pavement.
        """
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        enhanced_l = self.clahe.apply(l_channel)
        enhanced_lab = cv2.merge((enhanced_l, a_channel, b_channel))
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    def denoise(self, image: np.ndarray, method: str = "bilateral") -> np.ndarray:
        """
        Reduces asphalt granular noise while preserving sharp crack boundaries.
        'bilateral' preserves edges; 'gaussian' provides gentle smoothing.
        """
        if method == "bilateral":
            return cv2.bilateralFilter(image, d=7, sigmaColor=50, sigmaSpace=50)
        else:
            k = self.blur_kernel_size
            if k % 2 == 0:
                k += 1
            return cv2.GaussianBlur(image, (k, k), 0)

    def get_trapezoidal_road_mask(self, height: int, width: int) -> np.ndarray:
        """
        Generates a trapezoidal mask corresponding to the drivable road corridor,
        filtering out sky, trees, and irrelevant roadside background.
        """
        mask = np.zeros((height, width), dtype=np.uint8)
        # Vertices of the trapezoid (vanishing point corridor)
        roi_corners = np.array([[
            (int(width * 0.05), height),               # Bottom-left
            (int(width * 0.35), int(height * 0.40)),   # Top-left (horizon)
            (int(width * 0.65), int(height * 0.40)),   # Top-right (horizon)
            (int(width * 0.95), height)                # Bottom-right
        ]], dtype=np.int32)
        cv2.fillPoly(mask, roi_corners, 255)
        return mask

    def process(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Full preprocessing pipeline.
        Returns dictionary containing original, resized, enhanced, and road-masked images.
        """
        h_orig, w_orig = image.shape[:2]
        resized = self.resize(image)
        h, w = resized.shape[:2]

        # 1. Edge-preserving smoothing
        denoised = self.denoise(resized, method="bilateral")

        # 2. Local contrast enhancement via CLAHE
        enhanced = self.apply_clahe(denoised)

        # 3. Grayscale conversion for downstream intensity processing
        gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)

        # 4. Optional Road ROI mask
        road_mask = self.get_trapezoidal_road_mask(h, w)
        if self.apply_road_roi:
            roi_image = cv2.bitwise_and(enhanced, enhanced, mask=road_mask)
            roi_gray = cv2.bitwise_and(gray, gray, mask=road_mask)
        else:
            roi_image = enhanced.copy()
            roi_gray = gray.copy()

        return {
            "original": image,
            "original_dimensions": (w_orig, h_orig),
            "resized": resized,
            "enhanced": enhanced,
            "gray": gray,
            "roi_image": roi_image,
            "roi_gray": roi_gray,
            "road_mask": road_mask
        }
