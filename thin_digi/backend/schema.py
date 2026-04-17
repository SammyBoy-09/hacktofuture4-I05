from pydantic import BaseModel, Field
from typing import Literal, List, Optional

class RobotStep(BaseModel):
    action_type: Literal["verify_vision", "actuate_joints"] = Field(...)
    
    # --- Absolute Hardware States ---
    gripper_angle: int = Field(default=0, ge=0, le=90)
    body_tilt: int = Field(default=90, ge=30, le=110)

class RoboticSequence(BaseModel):
    task_name: str = Field(...)
    steps: List[RobotStep] = Field(...)