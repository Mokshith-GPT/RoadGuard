"""
RoadGuard - Module 1: Road Image Acquisition
Handles image/video loading, camera stream capture, and frame extraction.
"""

import cv2
import numpy as np
from typing import Union, Generator, Tuple, Optional


class ImageAcquisition:
    """Handles loading and ingestion of road imagery and video streams."""

    @staticmethod
    def load_image(source: Union[str, bytes, np.ndarray]) -> Tuple[bool, Optional[np.ndarray], str]:
        """
        Loads an image from a file path, byte stream, or numpy array.
        Returns: (success, image_bgr, message)
        """
        try:
            if isinstance(source, np.ndarray):
                if len(source.shape) == 2:
                    image = cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
                elif source.shape[2] == 4:
                    image = cv2.cvtColor(source, cv2.COLOR_BGRA2BGR)
                else:
                    image = source.copy()
                return True, image, "Image loaded from array."

            elif isinstance(source, (bytes, bytearray)):
                nparr = np.frombuffer(source, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if image is None:
                    return False, None, "Failed to decode image from bytes."
                return True, image, "Image decoded successfully."

            elif isinstance(source, str):
                image = cv2.imread(source, cv2.IMREAD_COLOR)
                if image is None:
                    return False, None, f"Could not read image from path: {source}"
                return True, image, f"Image loaded from {source}"

            else:
                return False, None, f"Unsupported source type: {type(source)}"

        except Exception as e:
            return False, None, f"Error acquiring image: {str(e)}"

    @staticmethod
    def extract_video_frames(
        video_path: str,
        frame_interval: int = 1,
        max_frames: Optional[int] = None
    ) -> Generator[Tuple[int, float, np.ndarray], None, None]:
        """
        Yields (frame_index, timestamp_sec, frame_bgr) from a video file.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video source: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = 0
        yielded_count = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                timestamp = frame_count / fps
                yield frame_count, timestamp, frame
                yielded_count += 1
                if max_frames and yielded_count >= max_frames:
                    break

            frame_count += 1

        cap.release()

    @staticmethod
    def validate_image(image: np.ndarray) -> Tuple[bool, str]:
        """Checks if the image has valid dimensions and color channels."""
        if image is None:
            return False, "Image is None."
        if not isinstance(image, np.ndarray):
            return False, "Input is not a numpy array."
        if image.size == 0:
            return False, "Image array is empty."
        if len(image.shape) != 3 or image.shape[2] != 3:
            return False, f"Expected 3-channel BGR image, got shape {image.shape}"
        h, w = image.shape[:2]
        if h < 50 or w < 50:
            return False, f"Image dimensions too small ({w}x{h})."
        return True, f"Valid image dimensions: {w}x{h}"
