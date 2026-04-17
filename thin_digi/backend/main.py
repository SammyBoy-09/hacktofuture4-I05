import asyncio
import json
import socket
import time
import base64
import os
import cv2
import math
import numpy as np
from ultralytics import YOLO
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Dict, Any
from pydantic import BaseModel
from agent import generate_robot_instruction

# Load YOLO Model for side view
try:
    side_model = YOLO("models/best_body.pt")
    print("YOLO side_model loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load YOLO side_model: {e}")
    side_model = None

# Load YOLO Model for top view
try:
    top_model = YOLO("models/best_arms.pt")
    print("YOLO top_model loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load YOLO top_model: {e}")
    top_model = None

# Load YOLO Model for box detection
try:
    box_model = YOLO("models/best_box.pt")
    print("YOLO box_model loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load YOLO box_model: {e}")
    box_model = None

# --- Network Settings: HARDWARE ---
RPI_IP = "10.35.41.165"  # <<< RASPBERRY PI'S IP ADDRESS
UDP_PORT = 5005

# --- Network Settings: DASHBOARD RELAY ---
DASHBOARD_IP = "10.43.148.27"
DASHBOARD_PORT = 5006

# Servo absolute angle when bone angle is 0 deg.
BODY_SERVO_AT_BONE_ZERO = 90.0
# The arm UI sends -90 to 0. If it expects to stay strictly above zero, it needs a valid offset like 90 or 180.
# Assuming zero bone is 180 servo, so -90 bone = 90 servo.
ARM_SERVO_AT_BONE_ZERO = 0.0

# Network/jitter controls
SEND_RATE_HZ = 40.0
SEND_DEADBAND_DEG = 0.2
SMOOTHING_ALPHA = 0.45

def clamp(value, low, high):
    return max(low, min(high, value))

def low_pass(prev_value, new_value, alpha):
    if prev_value is None:
        return float(new_value)
    a = clamp(float(alpha), 0.0, 1.0)
    return float(prev_value) + a * (float(new_value) - float(prev_value))

# Dedicated sockets for hardware and dashboard.
hardware_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# Set broadcast optionally if testing
# hardware_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

dashboard_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Global variables for filtering and rate limiting
browser_connected = False
target_body = BODY_SERVO_AT_BONE_ZERO
target_arm = ARM_SERVO_AT_BONE_ZERO
filtered_body = BODY_SERVO_AT_BONE_ZERO
filtered_arm = ARM_SERVO_AT_BONE_ZERO
last_sent_body = None
last_sent_arm = None

async def continuous_udp_streamer():
    """Background task that runs at 40Hz to smoothly interpolate and send commands.
    This fixes the 'jerky' movement by stepping the low_pass filter continuously
    even if the WebSocket only sends sparse updates."""
    global filtered_body, filtered_arm, last_sent_body, last_sent_arm
    
    while True:
        # Interpolate towards the target independently of frontend packet rate
        filtered_body = low_pass(filtered_body, target_body, SMOOTHING_ALPHA)
        filtered_arm = low_pass(filtered_arm, target_arm, SMOOTHING_ALPHA)
        
        # Check deadband against last sent
        if (
            last_sent_body is None
            or abs(filtered_body - last_sent_body) >= SEND_DEADBAND_DEG
            or abs(filtered_arm - last_sent_arm) >= SEND_DEADBAND_DEG
        ):
            udp_payload = {
                "body": filtered_body,
                "arm": filtered_arm,
                "source": "frontend_override"
            }
            encoded_payload = json.dumps(udp_payload).encode('utf-8')
            
            # Broadcast the manual override bounds
            hardware_sock.sendto(encoded_payload, (RPI_IP, UDP_PORT))
            dashboard_sock.sendto(encoded_payload, (DASHBOARD_IP, DASHBOARD_PORT))
            
            last_sent_body = filtered_body
            last_sent_arm = filtered_arm
                
        await asyncio.sleep(1.0 / SEND_RATE_HZ)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the background interpolation loop
    task = asyncio.create_task(continuous_udp_streamer())
    yield
    # Shutdown: Cancel the loop
    task.cancel()

app = FastAPI(title="Thin Edge Backend", lifespan=lifespan)

# We want the frontend anywhere to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/teleop")
async def teleop_endpoint(websocket: WebSocket):
    global browser_connected, target_body, target_arm
    
    await websocket.accept()
    
    # LOCK ENABLED: Browser asserts dominance. 
    # (If Blender is routing through FastAPI, it should respect this flag and ignore Blender UDPs)
    browser_connected = True
    print("Operator assumed teleop control. Locked out other sources.")
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                
                body_angle = payload.get("body")
                arm_angle = payload.get("r-arm")
                
                if body_angle is not None and arm_angle is not None:
                    # Update TARGETS, letting the background task do the heavy smoothing
                    tx_body = float(body_angle)
                    tx_arm = -float(arm_angle)
                    
                    target_body = clamp(BODY_SERVO_AT_BONE_ZERO + tx_body, 0.0, 180.0)
                    target_arm = clamp(ARM_SERVO_AT_BONE_ZERO + tx_arm, 0.0, 180.0)

            except json.JSONDecodeError:
                pass
            except Exception as e:
                print("Error processing payload", e)
    
    except WebSocketDisconnect:
        # LOCK RELEASED: Disconnected, normal routing resumes
        browser_connected = False
        print("Operator released teleop control. Normal routing resumed.")

frontend_camera_clients = {
    "top": [],
    "side": []
}

@app.websocket("/ws/camera_in/{view}")
async def camera_in_endpoint(websocket: WebSocket, view: str):
    await websocket.accept()
    if view not in frontend_camera_clients:
        await websocket.close()
        return
        
    print(f"Mobile Camera App ({view} view) Connected!")
    frame_count = 0
    last_processed_angle = None
    last_processed_image = None
    last_box_flag = False
    last_box_detect_time = 0.0
    last_process_time = 0.0
    TARGET_FPS = 8.0 # Lowered FPS limit to process fewer frames to improve CPU constraints
    FRAME_TIME = 1.0 / TARGET_FPS
    
    try:
        while True:
            # Receive base64 frame from Android
            frame_base64 = await websocket.receive_text()
            frame_count += 1
            current_time = time.time()
            
            if frame_count % 30 == 0:
                print(f"[{view}] Received {frame_count} frames...")
            
            # Default to passing the raw frame (or the last annotated frame if available)
            current_image_out = last_processed_image if last_processed_image else frame_base64
            out_message = json.dumps({"image": current_image_out, "angle": last_processed_angle})
            
            # --- SIDE VIEW INFERENCE ---
            if view == "side" and side_model is not None:
                # Time-based throttling to enforce a specific FPS limit
                if current_time - last_process_time >= FRAME_TIME:
                    last_process_time = current_time
                    try:
                        if "," in frame_base64:
                            header, encoded = frame_base64.split(",", 1)
                        else:
                            header, encoded = "", frame_base64
                        
                        if encoded:
                            img_data = base64.b64decode(encoded)
                            np_arr = np.frombuffer(img_data, np.uint8)
                            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                            if img is not None:
                                # Run inference with higher imgsz to accurately detect pose
                                results = side_model.predict(img, imgsz=640, conf=0.35, verbose=False, device="cpu")
                                annotated_img = img.copy()
                                
                                if results and len(results) > 0 and results[0].keypoints is not None and len(results[0].keypoints.xy) > 0:
                                    pts = results[0].keypoints.xy[0].cpu().numpy()
                                    if len(pts) >= 5:
                                        # index 2=body, 3=tail (vertex), 4=top
                                        p_body = pts[2]
                                        p_tail = pts[3]
                                        p_top = pts[4]
                                        
                                        # Only process if the keypoints are actually found and not returned as (0, 0) fallbacks
                                        if (p_body[0] > 0 or p_body[1] > 0) and \
                                           (p_tail[0] > 0 or p_tail[1] > 0) and \
                                           (p_top[0] > 0 or p_top[1] > 0):
                                           
                                            # Calculate vector angles starting from body (index 2) as the vertex (Red dot)
                                            ang1 = math.atan2(p_tail[1] - p_body[1], p_tail[0] - p_body[0])
                                            ang2 = math.atan2(p_top[1] - p_body[1], p_top[0] - p_body[0])
                                            
                                            angle = abs(math.degrees(ang1 - ang2))
                                            if angle > 180:
                                                angle = 360 - angle
                                            angle = 180.0 - angle - 20
                                                
                                            # Apply exponential smoothing to ignore sudden outlier jumps
                                            if last_processed_angle is None:
                                                last_processed_angle = angle
                                            else:
                                                # If it jumps more than 50 degrees in one frame, heavily dampen it, otherwise smooth normally
                                                if abs(angle - last_processed_angle) > 50:
                                                    last_processed_angle = (last_processed_angle * 0.9) + (angle * 0.1)
                                                else:
                                                    last_processed_angle = (last_processed_angle * 0.85) + (angle * 0.15)

                                # Optimize video feed: resize for frontend broadcast
                                display_img = cv2.resize(annotated_img, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_LINEAR)
                                # Encode the image back to base64
                                ret, buffer = cv2.imencode('.jpg', display_img, [cv2.IMWRITE_JPEG_QUALITY, 50])
                                if ret:
                                    out_base64 = base64.b64encode(buffer).decode('utf-8')
                                    annotated_frame_base64 = f"{header},{out_base64}" if header else out_base64
                                    last_processed_image = annotated_frame_base64
                                    
                                    out_message = json.dumps({
                                        "image": annotated_frame_base64,
                                        "angle": last_processed_angle
                                    })
                            else:
                                print(f"[{view}] cv2.imdecode returned None")
                    except Exception as e:
                        print(f"[{view}] Error during YOLO processing: {e}")

            # --- TOP VIEW INFERENCE ---
            elif view == "top" and top_model is not None:
                if current_time - last_process_time >= FRAME_TIME:
                    last_process_time = current_time
                    try:
                        if "," in frame_base64:
                            header, encoded = frame_base64.split(",", 1)
                        else:
                            header, encoded = "", frame_base64
                        
                        if encoded:
                            img_data = base64.b64decode(encoded)
                            np_arr = np.frombuffer(img_data, np.uint8)
                            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                            if img is not None:
                                # Run inference for top view keypoints
                                results = top_model.predict(img, imgsz=640, conf=0.35, verbose=False, device="cpu")
                                annotated_img = img.copy()
                                
                                C_GRIPPER = (0, 140, 255)   # orange
                                C_LEFT    = (0, 255, 0)     # green
                                C_RIGHT   = (0, 0, 255)     # red
                                KP_COLOR  = (255, 0, 0)     # blue-ish

                                if results and len(results) > 0:
                                    res = results[0]
                                    
                                    # Draw bounding boxes
                                    left_arm_data = None
                                    right_arm_data = None
                                    
                                    if res.boxes is not None and len(res.boxes) > 0:
                                        for b in res.boxes:
                                            cls = int(b.cls[0]) if b.cls is not None else -1
                                            x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                                            
                                            # Calculate top-center tip of the box
                                            tip_x = int((x1 + x2) / 2)
                                            tip_y = int(y1)
                                            
                                            # Using the logic from snippet for left/right arms
                                            if cls == 0:
                                                inner_x = x2
                                                inner_y = y2
                                                left_arm_data = (tip_x, tip_y, inner_x, inner_y)
                                            elif cls == 1:
                                                inner_x = x1
                                                inner_y = y2
                                                right_arm_data = (tip_x, tip_y, inner_x, inner_y)
                                            else:
                                                inner_x = int((x1 + x2) / 2)
                                                inner_y = y2
                                                        
                                        # Merge lower points and calculate bounding box angle if both arms are detected
                                        if left_arm_data and right_arm_data:
                                            merged_x = int((left_arm_data[2] + right_arm_data[2]) / 2)
                                            merged_y = int((left_arm_data[3] + right_arm_data[3]) / 2)
                                            p_merged = (merged_x, merged_y)
                                            p_left_tip = (left_arm_data[0], left_arm_data[1])
                                            p_right_tip = (right_arm_data[0], right_arm_data[1])
                                            
                                            # Calculate angle
                                            ang1 = math.atan2(p_left_tip[1] - merged_y, p_left_tip[0] - merged_x)
                                            ang2 = math.atan2(p_right_tip[1] - merged_y, p_right_tip[0] - merged_x)
                                            arms_angle = abs(math.degrees(ang1 - ang2))
                                            if arms_angle > 180:
                                                arms_angle = 360 - arms_angle
                                                        
                                            # Apply exponential smoothing to ignore sudden outlier jumps
                                            if last_processed_angle is None:
                                                last_processed_angle = arms_angle
                                            else:
                                                if abs(arms_angle - last_processed_angle) > 50:
                                                    last_processed_angle = (last_processed_angle * 0.9) + (arms_angle * 0.1)
                                                else:
                                                    last_processed_angle = (last_processed_angle * 0.85) + (arms_angle * 0.15)
                                                        
                                    # Calculate keypoints (without drawing)
                                    if res.keypoints is not None and len(res.keypoints.xy) > 0:
                                        pts = res.keypoints.xy[0].cpu().numpy()
                                        
                                        if len(pts) >= 5:
                                            # SAME point logic: 2=body, 3=tail (vertex), 4=top
                                            p_body = pts[2]
                                            p_tail = pts[3]
                                            p_top = pts[4]
                                            
                                            # Safety check for (0,0) phantom points
                                            if (p_body[0] > 0 or p_body[1] > 0) and \
                                               (p_tail[0] > 0 or p_tail[1] > 0) and \
                                               (p_top[0] > 0 or p_top[1] > 0):
                                               
                                                # Use point 2 (body) as the vertex for the angle
                                                ang1 = math.atan2(p_tail[1] - p_body[1], p_tail[0] - p_body[0])
                                                ang2 = math.atan2(p_top[1] - p_body[1], p_top[0] - p_body[0])
                                                
                                                angle = abs(math.degrees(ang1 - ang2))
                                                if angle > 180:
                                                    angle = 360 - angle
                                                angle = 180.0 - angle
                                                    
                                                # Optional: Only override using keypoints if bounding box arms failed
                                                if not left_arm_data or not right_arm_data:
                                                    if last_processed_angle is None:
                                                        last_processed_angle = angle
                                                    else:
                                                        if abs(angle - last_processed_angle) > 50:
                                                            last_processed_angle = (last_processed_angle * 0.9) + (angle * 0.1)
                                                        else:
                                                            last_processed_angle = (last_processed_angle * 0.85) + (angle * 0.15)

                                # Run box detection model for gripper and box detection in top view
                                if box_model is not None and frame_count % 3 == 0:
                                    new_box_flag = False
                                    box_results = box_model.predict(img, imgsz=640, conf=0.35, verbose=False, device="cpu")
                                    if box_results and len(box_results) > 0:
                                        box_res = box_results[0]
                                        
                                        # First find the gripper box
                                        gripper_box = None
                                        if box_res.boxes is not None and len(box_res.boxes) > 0:
                                            for b in box_res.boxes:
                                                if int(b.cls[0]) == 2: # gripper
                                                    gx1, gy1, gx2, gy2 = map(int, b.xyxy[0].tolist())
                                                    gripper_box = (gx1, gy1, gx2, gy2)
                                                    break
                                            
                                            for b in box_res.boxes:
                                                cls = int(b.cls[0]) if b.cls is not None else -1
                                                conf = float(b.conf[0]) if b.conf is not None else -1
                                                bx1, by1, bx2, by2 = map(int, b.xyxy[0].tolist())
                                                
                                                box_name = f"obj_{cls}"
                                                box_color = (0, 165, 255) # Orange default
                                                if cls == 0:
                                                    box_name = "bbox"
                                                    box_color = (255, 0, 255)
                                                elif cls == 1:
                                                    box_name = "eraser"
                                                    box_color = (0, 255, 255)
                                                elif cls == 2:
                                                    box_name = "gripper"
                                                    box_color = (0, 255, 0)
                                                elif cls == 3:
                                                    box_name = "match"
                                                    box_color = (0, 0, 255)
                                                    
                                                # Check collision if it's an object
                                                if cls in [0, 1, 3] and gripper_box:
                                                    gx1, gy1, gx2, gy2 = gripper_box
                                                    # Centroid of object inside gripper bbox bounds
                                                    cx = (bx1 + bx2) / 2
                                                    cy = (by1 + by2) / 2
                                                    if gx1 <= cx <= gx2 and gy1 <= cy <= gy2:
                                                        new_box_flag = True
                                                        
                                    if new_box_flag:
                                        last_box_detect_time = current_time
                                        
                                    # Hold detection flag for 1.5 seconds to smooth out flicker/outliers
                                    last_box_flag = (current_time - last_box_detect_time) < 1.5
                                                    
                                                # Draw bounding box and label for gripper/box detection
                                                # Removed to speed up feed and stop cluttering the top view
                                                # cv2.rectangle(annotated_img, (bx1, by1), (bx2, by2), box_color, 2)
                                                # cv2.putText(annotated_img, f"{box_name} {conf:.2f}", (bx1, max(20, by1-8)),
                                                #             cv2.FONT_HERSHEY_SIMPLEX, 0.7, box_color, 2)

                                # Optimize video feed: resize for frontend broadcast
                                display_img = cv2.resize(annotated_img, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_LINEAR)
                                # Encode the image back to base64
                                ret, buffer = cv2.imencode('.jpg', display_img, [cv2.IMWRITE_JPEG_QUALITY, 50])
                                if ret:
                                    out_base64 = base64.b64encode(buffer).decode('utf-8')
                                    annotated_frame_base64 = f"{header},{out_base64}" if header else out_base64
                                    last_processed_image = annotated_frame_base64
                                    
                                    out_message = json.dumps({
                                        "image": annotated_frame_base64,
                                        "angle": last_processed_angle,
                                        "box_flag": last_box_flag
                                    })
                            else:
                                print(f"[{view}] cv2.imdecode returned None")
                    except Exception as e:
                        print(f"[{view}] Error during YOLO processing: {e}")

            # Broadcast to any active Frontend dashboards
            for client in frontend_camera_clients[view].copy():
                try:
                    await client.send_text(out_message)
                except:
                    frontend_camera_clients[view].remove(client)
                    
            # TODO: Future YOLOv8 Inference hook goes here!
            
    except WebSocketDisconnect:
        print(f"Mobile Camera App ({view} view) Disconnected")

@app.websocket("/ws/camera_out/{view}")
async def camera_out_endpoint(websocket: WebSocket, view: str):
    await websocket.accept()
    if view not in frontend_camera_clients:
        await websocket.close()
        return
        
    frontend_camera_clients[view].append(websocket)
    print(f"Frontend Dashboard ({view} view) Connected!")
    try:
        while True:
            await websocket.receive_text() # Keep connection alive
    except WebSocketDisconnect:
        if websocket in frontend_camera_clients[view]:
            frontend_camera_clients[view].remove(websocket)
        print(f"Frontend Dashboard ({view} view) Disconnected")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Thin Edge Backend is running"}

class UserRequest(BaseModel):
    prompt: str
    sequence_time: float = 1.0

class ExecuteRequest(BaseModel):
    sequence: dict
    sequence_time: float

@app.post("/api/plan-movement")
async def plan_movement(request: UserRequest):
    # Generates the sequential plan
    sequence_json = generate_robot_instruction(request.prompt)
    
    # Store JSON history
    history_file = "ai_history.json"
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history = json.load(f)
        except Exception:
            pass
            
    history.insert(0, sequence_json.dict()) # Insert at beginning (newest first)
    
    with open(history_file, "w") as f:
        json.dump(history, f, indent=4)
    
    return {
        "status": "success", 
        "sequence": sequence_json,
        "sequence_time": request.sequence_time
    }

@app.get("/api/ai-history")
async def get_ai_history():
    history_file = "ai_history.json"
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history = json.load(f)
        except Exception:
            pass
    return {"history": history}

@app.post("/api/execute-movement")
async def execute_movement(request: ExecuteRequest):
    global target_body, target_arm, browser_connected

    # Ensure frontend telemetry loop doesn't fight this by asserting control
    browser_connected = True 
    print(f"\n--- EXECUTING AI SEQUENCE ON REAL MACHINE ({request.sequence_time}s per step) ---")
    
    try:
        steps = request.sequence.get("steps", [])
        for i, step in enumerate(steps):
            action = step.get("action_type")
            if action == "verify_vision":
                print(f"Step {i+1}: Verifying Vision...")
                await asyncio.sleep(request.sequence_time)
                continue
            
            # Map LLM states to physical 0-180 limits using our logic
            llm_body = step.get("body_tilt", 90)
            llm_gripper = step.get("gripper_angle", 0)

            # Map to target bounds
            # body: 90=upright(0), 45=forward(45). mapped tx_body = body_tilt - 90 = 45 - 90 = -45
            # Then physical = clamp(BODY_SERVO_AT_BONE_ZERO + tx_body, 0.0, 180.0)
            tx_body = float(llm_body) - 90.0
            # gripper: 0=closed(0 tx_arm), 85=open(85 tx_arm)
            tx_arm = float(llm_gripper)

            target_body = clamp(BODY_SERVO_AT_BONE_ZERO + tx_body, 0.0, 180.0)
            target_arm = clamp(ARM_SERVO_AT_BONE_ZERO + tx_arm, 0.0, 180.0)
            print(f"Step {i+1}: Mapped to Physical Body {target_body}, Arm {target_arm}")
            
            await asyncio.sleep(request.sequence_time)

        print("--- Sequence complete ---")
        return {"status": "success", "message": "Sequence executed on real machine"}
    except Exception as e:
        print(f"Execution Error: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
