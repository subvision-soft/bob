import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple
import base64
import cv2
import numpy as np
import os
import uuid

from engine.yoloseg.YOLOSeg import YOLOSeg

import concurrent.futures

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from numpy import ndarray


PICTURE_WIDTH_SHEET_DETECTION = 2000
PICTURE_HEIGHT_SHEET_DETECTION = 2000
KERNEL_SIZE = (PICTURE_WIDTH_SHEET_DETECTION // 200, PICTURE_WIDTH_SHEET_DETECTION // 200)
ROUND_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, KERNEL_SIZE)
model_onnx = model_path = os.path.join(os.path.dirname(__file__), "nano_semantic_model.onnx")
yolo_v8 = YOLOSeg(model_onnx, conf_thres=0.5)





# Récupération de la distance entre deux points
def get_distance(point1, point2):
    return math.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)



def clamp(value, min_value=-1.0, max_value=1.0):
    return max(min_value, min(value, max_value))


# On récupère le plus grand contour valide
def get_biggest_valid_contour(contours):
    biggest_contour = None
    biggest_area = 0
    for contour in contours:
        approx = cv2.approxPolyDP(contour, cv2.arcLength(contour, True) * 0.01, True)
        if len(approx) != 4 or cv2.contourArea(approx) < biggest_area:
            continue
        angles = [math.acos(clamp(
            ((p1[0] - p2[0]) * (p3[0] - p2[0]) + (p1[1] - p2[1]) * (p3[1] - p2[1])) /
            (((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5 *
             ((p3[0] - p2[0]) ** 2 + (p3[1] - p2[1]) ** 2) ** 0.5))) * 180 / math.pi
                  for i in range(4)
                  for p1, p2, p3 in [(approx[i][0], approx[(i + 1) % 4][0], approx[(i + 2) % 4][0])]]
        if any(angle < 70 or angle > 110 for angle in angles):
            continue
        area = cv2.contourArea(approx)
        if area / (PICTURE_WIDTH_SHEET_DETECTION * PICTURE_HEIGHT_SHEET_DETECTION) < 0.1 or area / (
                PICTURE_WIDTH_SHEET_DETECTION * PICTURE_HEIGHT_SHEET_DETECTION) > 0.9:
            continue
        biggest_contour = approx
        biggest_area = area
    return biggest_contour


def coordinates_to_percentage(coordinates, width, height):
    percentage_coordinates = []
    for coordinate in coordinates:
        percentage_coordinates.append((coordinate[0] / width, coordinate[1] / height))
    return percentage_coordinates


# Récupération des coordonnées du plastron
def get_sheet_coordinates(sheet_mat: ndarray):
    mat_resized = cv2.resize(sheet_mat.copy(), (PICTURE_WIDTH_SHEET_DETECTION, PICTURE_HEIGHT_SHEET_DETECTION))
    boxes, scores, _, masks = yolo_v8(mat_resized)
    if masks is not None and len(masks) > 0:
        best_detection_index = np.argsort(scores)[-1:]
        mask = masks[best_detection_index[0]]
        mask = (mask * 255).astype(np.uint8)
        mask = cv2.resize(mask, (PICTURE_WIDTH_SHEET_DETECTION, PICTURE_HEIGHT_SHEET_DETECTION))
        contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        biggest_contour = get_biggest_valid_contour(contours)
        if biggest_contour is None:
            return None
        return coordinates_to_percentage(
            [(biggest_contour[i][0][0], biggest_contour[i][0][1]) for i in range(4)],
            PICTURE_WIDTH_SHEET_DETECTION, PICTURE_HEIGHT_SHEET_DETECTION
        )
    return None


# A partir des coordonnées en pourcentage, on les convertit en coordonnées réelles (pixels)
def percentage_to_coordinates(percentage_coordinates, width, height):
    coordinates = []
    for percentage_coordinate in percentage_coordinates:
        coordinates.append((int(percentage_coordinate[0] * width), int(percentage_coordinate[1] * height)))
    return coordinates


# A partir de l'image initial, on extraie l'image du plastron recadré
def get_sheet_picture(image: ndarray) -> Optional[ndarray]:
    coordinates = get_sheet_coordinates(image)
    if coordinates is None:
        return None
    height, width, _ = image.shape
    real_coordinates = percentage_to_coordinates(coordinates, width, height)
    approx = np.array(real_coordinates, np.float32)
    target_coordinates = np.array([
        [0, 0],
        [PICTURE_WIDTH_SHEET_DETECTION, 0],
        [PICTURE_WIDTH_SHEET_DETECTION, PICTURE_HEIGHT_SHEET_DETECTION], [0, PICTURE_HEIGHT_SHEET_DETECTION]
    ], np.float32)
    transformation_matrix = cv2.getPerspectiveTransform(approx, target_coordinates)
    return cv2.warpPerspective(image, transformation_matrix,
                               (PICTURE_WIDTH_SHEET_DETECTION, PICTURE_HEIGHT_SHEET_DETECTION))


def get_sheet_bounds_original(image: ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Get bounding box of target (sheet) in original frame coordinates.
    Returns: (x_min, y_min, x_max, y_max) or None if target not detected
    """
    coordinates = get_sheet_coordinates(image)
    if coordinates is None:
        return None
    height, width, _ = image.shape
    real_coordinates = percentage_to_coordinates(coordinates, width, height)
    # real_coordinates is list of 4 corner points
    xs = [pt[0] for pt in real_coordinates]
    ys = [pt[1] for pt in real_coordinates]
    return (min(xs), min(ys), max(xs), max(ys))


def _point_in_bounds(point: Tuple[int, int], bounds: Tuple[int, int, int, int]) -> bool:
    """Check if point (x, y) is within bounding box (x_min, y_min, x_max, y_max)"""
    x, y = point
    x_min, y_min, x_max, y_max = bounds
    return x_min <= x <= x_max and y_min <= y <= y_max


def _get_line_angle(x1: float, y1: float, x2: float, y2: float) -> float:
    """Get angle of line in degrees (0-180)"""
    angle = np.arctan2(abs(y2 - y1), abs(x2 - x1)) * 180.0 / np.pi
    return angle


def _filter_parallel_lines(line_segments: list, angle_tolerance: float = 15.0) -> list:
    """
    Filter lines to keep only those that are nearly parallel to the longest line.
    Arrow shafts are generally parallel to each other.
    
    angle_tolerance: maximum angle difference in degrees (default 15°)
    """
    if not line_segments or len(line_segments) <= 1:
        return line_segments
    
    # Find the longest line and its angle
    longest_line = None
    longest_length = 0.0
    for x1, y1, x2, y2 in line_segments:
        length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        if length > longest_length:
            longest_length = length
            longest_line = (x1, y1, x2, y2)
    
    if longest_line is None:
        return line_segments
    
    ref_angle = _get_line_angle(*longest_line)
    
    # Keep lines parallel to the reference line
    parallel_lines = [longest_line]
    for x1, y1, x2, y2 in line_segments:
        if (x1, y1, x2, y2) == longest_line:
            continue
        angle = _get_line_angle(x1, y1, x2, y2)
        angle_diff = abs(angle - ref_angle)
        # Handle 180° wraparound
        if angle_diff > 90:
            angle_diff = 180 - angle_diff
        if angle_diff <= angle_tolerance:
            parallel_lines.append([x1, y1, x2, y2])
    
    return parallel_lines


def decode_image_data(image_data: str) -> ndarray:
    if "," in image_data and image_data.strip().startswith("data:"):
        image_data = image_data.split(",", 1)[1]
    decoded_data = base64.b64decode(image_data)
    np_array = np.frombuffer(decoded_data, dtype=np.uint8)
    image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Invalid image format.")
    return image


def _normalize_sheet_view(image: ndarray) -> ndarray:
    sheet_picture = get_sheet_picture(image)
    if sheet_picture is None:
        return cv2.resize(image, (PICTURE_WIDTH_SHEET_DETECTION, PICTURE_HEIGHT_SHEET_DETECTION))
    return sheet_picture


def _diff_metrics(previous_frame: ndarray, current_frame: ndarray) -> Tuple[np.ndarray, float, int, list]:
    """
    Detect arrow appearance by finding lines in the original frame space.
    Only returns lines where at least one endpoint is within the detected target bounds.
    """
    # Get target bounds in original frame coordinates
    target_bounds = get_sheet_bounds_original(current_frame)
    
    # Work with original frames (no warping/resizing)
    if previous_frame.shape != current_frame.shape:
        previous_frame = cv2.resize(previous_frame, (current_frame.shape[1], current_frame.shape[0]))
    
    previous_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)

    previous_gray = cv2.GaussianBlur(previous_gray, (5, 5), 0)
    current_gray = cv2.GaussianBlur(current_gray, (5, 5), 0)

    diff = cv2.absdiff(previous_gray, current_gray)
    _, binary = cv2.threshold(diff, 40, 255, cv2.THRESH_BINARY)
    
    # Scale kernel based on actual frame size, not hardcoded 2000
    frame_height = current_frame.shape[0]
    kernel_size = max(1, frame_height // 200)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Detect edges and lines in original frame space
    edges = cv2.Canny(binary, 80, 200)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60, minLineLength=50, maxLineGap=25)
    
    line_segments = [] if lines is None else lines.reshape(-1, 4).tolist()
    
    # Filter lines: keep only those with at least one endpoint within target bounds
    if target_bounds is not None:
        filtered_lines = []
        for x1, y1, x2, y2 in line_segments:
            # At least one endpoint must be within target
            if _point_in_bounds((x1, y1), target_bounds) or _point_in_bounds((x2, y2), target_bounds):
                filtered_lines.append([x1, y1, x2, y2])
        line_segments = filtered_lines
    
    # Filter to keep only parallel lines (arrow shafts are parallel)
    line_segments = _filter_parallel_lines(line_segments, angle_tolerance=15.0)
    
    # Find the longest line (arrow shaft is one long object)
    max_line_length = 0.0
    if line_segments:
        for x1, y1, x2, y2 in line_segments:
            length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            max_line_length = max(max_line_length, length)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    diff_area = float(sum(cv2.contourArea(contour) for contour in contours if cv2.contourArea(contour) >= 80))
    
    return binary, diff_area, int(max_line_length), line_segments


def detect_shot_between_frames(previous_frame: ndarray, current_frame: ndarray) -> Dict[str, Any]:
    """
    Detect arrow appearance by analyzing frame differences in original space.
    Only validates lines that have at least one endpoint within detected target bounds.
    This ensures arrow detection is physically relevant to the actual target location.
    """
    diff_mask, diff_area, max_line_length, line_segments = _diff_metrics(previous_frame, current_frame)
    total_area = float(diff_mask.shape[0] * diff_mask.shape[1])
    diff_ratio = diff_area / total_area if total_area else 0.0
    
    # Arrow signature: one long line segment (the shaft)
    # Normalize line length: 50px = weak, 100px = medium, 200px+ = strong
    line_score = min(1.0, max(0.0, (max_line_length - 50) / 150.0))
    
    # Area must be reasonably localized
    # Allow up to 1% of frame to change (arrow is narrow)
    area_score = 1.0 if diff_ratio < 0.01 else max(0.0, 1.0 - diff_ratio / 0.02)
    
    # Confidence: 85% on line detection (arrow is about the shaft), 15% on localization
    confidence = round(min(1.0, 0.85 * line_score + 0.15 * area_score), 4)
    
    # Detect shot if:
    # - Found a reasonably long line (>= 50px) AND confidence >= 0.35
    # This catches single arrow appearances
    shot_detected = max_line_length >= 50 and confidence >= 0.60 and len(line_segments) > 15
    return {
        "shot_detected": shot_detected,
        "event_type": "SHOT_FIRED" if shot_detected else None,
        "confidence": confidence,
        "diff_area": round(diff_area, 2),
        "diff_ratio": round(diff_ratio, 6),
        "line_count": len(line_segments),
        "lines": line_segments,
        "diff_mask": diff_mask,
    }


def build_shot_event_payload(
    *,
    previous_frame_id: Optional[int],
    current_frame_id: Optional[int],
    previous_timestamp: Optional[float],
    current_timestamp: Optional[float],
    camera_id: Optional[str],
    competition_id: Optional[str],
    athlete_id: Optional[str],
    lane: Optional[int],
    analysis: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": "SHOT_FIRED",
        "event_type": "SHOT_FIRED",
        "camera_id": camera_id,
        "competition_id": competition_id,
        "athlete_id": athlete_id,
        "lane": lane,
        "frame_id": current_frame_id,
        "frame_timestamp": current_timestamp,
        "previous_frame_id": previous_frame_id,
        "previous_frame_timestamp": previous_timestamp,
        "confidence": analysis["confidence"],
        "raw_payload": {
            "shot_detected": analysis["shot_detected"],
            "diff_area": analysis["diff_area"],
            "diff_ratio": analysis["diff_ratio"],
            "line_count": analysis["line_count"],
            "lines": analysis["lines"],
            "previous_frame_id": previous_frame_id,
            "current_frame_id": current_frame_id,
        },
    }