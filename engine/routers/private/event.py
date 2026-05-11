from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.target_detection import (
    build_shot_event_payload,
    decode_image_data,
    detect_shot_between_frames,
    get_sheet_coordinates,
)

router = APIRouter()


class FramePayload(BaseModel):
    frame_id: Optional[int] = None
    timestamp: Optional[float] = None
    image_data: str = Field(..., min_length=1)


class FramePairRequest(BaseModel):
    camera_id: Optional[str] = None
    competition_id: Optional[str] = None
    athlete_id: Optional[str] = None
    lane: Optional[int] = None
    subscriptions: Optional[List[str]] = None
    previous_frame: FramePayload
    current_frame: FramePayload


class DetectionSummary(BaseModel):
    shot_detected: bool
    confidence: float
    diff_area: float
    diff_ratio: float
    line_count: int
    lines: List[List[int]]


@router.post("/pending")
def detect_target(request: FramePairRequest) -> List[Dict[str, Any]]:
    try:
        # If caller indicates there are no subscriptions for SHOT_FIRED, skip heavy detection.
        if request.subscriptions is not None and "SHOT_FIRED" not in request.subscriptions:
            return []
        previous_image = decode_image_data(request.previous_frame.image_data)
        current_image = decode_image_data(request.current_frame.image_data)

        analysis = detect_shot_between_frames(previous_image, current_image)
        if not analysis["shot_detected"]:
            return []

        return [
            build_shot_event_payload(
                previous_frame_id=request.previous_frame.frame_id,
                current_frame_id=request.current_frame.frame_id,
                previous_timestamp=request.previous_frame.timestamp,
                current_timestamp=request.current_frame.timestamp,
                camera_id=request.camera_id,
                competition_id=request.competition_id,
                athlete_id=request.athlete_id,
                lane=request.lane,
                analysis=analysis,
            )
        ]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid frame pair: {exc}") from exc


@router.post("/process", response_model=DetectionSummary)
def target_score(request: FramePairRequest) -> DetectionSummary:
    try:
        if request.subscriptions is not None and "SHOT_FIRED" not in request.subscriptions:
            return DetectionSummary(
                shot_detected=False,
                confidence=0.0,
                diff_area=0.0,
                diff_ratio=0.0,
                line_count=0,
                lines=[],
            )
        previous_image = decode_image_data(request.previous_frame.image_data)
        current_image = decode_image_data(request.current_frame.image_data)
        analysis = detect_shot_between_frames(previous_image, current_image)
        return DetectionSummary(
            shot_detected=analysis["shot_detected"],
            confidence=analysis["confidence"],
            diff_area=analysis["diff_area"],
            diff_ratio=analysis["diff_ratio"],
            line_count=analysis["line_count"],
            lines=analysis["lines"],
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid frame pair: {exc}") from exc
