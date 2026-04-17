import bpy
import math
import socket
import json
import time

# ==========================================
# CONFIGURATION VARIABLES
# ==========================================
ARMATURE_NAME = "Armature"

# --- Network Settings: HARDWARE ---
RPI_IP = "10.35.41.165"  # <<< CHANGE THIS TO YOUR RASPBERRY PI'S IP ADDRESS
UDP_PORT = 5005

# --- Network Settings: DASHBOARD RELAY ---
DASHBOARD_IP = "10.43.148.27" # Send to the relay script running on the same PC
DASHBOARD_PORT = 5006

# --- Body Bone Settings ---
BODY_BONE_NAME = "Bone"
BODY_ROTATION_AXIS = 0      # 0 for X, 1 for Y, 2 for Z
BODY_INVERT_DEGREE = False  # Set to True to invert output (+/-)

# --- Arm Bone Settings ---
ARM_BONE_NAME = "Bone.005"
ARM_ROTATION_AXIS = 2       # 0 for X, 1 for Y, 2 for Z
ARM_INVERT_DEGREE = True    # Set to True to invert output (+/-)

# Servo absolute angle when Blender bone angle is 0 deg.
# Keep arm zero-mapped so raw arm 0 deg sends logical arm 0 deg.
BODY_SERVO_AT_BONE_ZERO = 90.0
ARM_SERVO_AT_BONE_ZERO = 0.0

# Network/jitter controls
SEND_RATE_HZ = 40.0
SEND_DEADBAND_DEG = 0.2
SMOOTHING_ALPHA = 0.45

def clamp(value, low, high):
    return max(low, min(high, value))


def to_absolute_servo_angle(angle_deg, servo_at_bone_zero):
    absolute = float(servo_at_bone_zero) + float(angle_deg)
    return clamp(absolute, 0.0, 180.0)


def low_pass(prev_value, new_value, alpha):
    if prev_value is None:
        return float(new_value)
    a = clamp(float(alpha), 0.0, 1.0)
    return float(prev_value) + a * (float(new_value) - float(prev_value))


# Dedicated sockets for hardware and dashboard.
hardware_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

dashboard_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

last_send_monotonic = 0.0
last_sent_body = None
last_sent_arm = None
filtered_body = None
filtered_arm = None

# Blender API state-reply handling is disabled for now.
# def read_latest_hardware_state():
#     latest_state = None
#     while True:
#         try:
#             packet, _ = hardware_sock.recvfrom(8192)
#         except BlockingIOError:
#             break
#         except OSError:
#             break
#
#         try:
#             message = json.loads(packet.decode("utf-8"))
#         except (UnicodeDecodeError, json.JSONDecodeError):
#             continue
#
#         if isinstance(message, dict) and message.get("ok") and isinstance(message.get("state"), dict):
#             latest_state = message["state"]
#
#     return latest_state

def get_bone_angle_degrees(armature_eval, bone_name, axis, invert):
    bone = armature_eval.pose.bones.get(bone_name)
    if not bone: return None
    if bone.rotation_mode == 'QUATERNION':
        euler_rot = bone.rotation_quaternion.to_euler('XYZ')
    else:
        euler_rot = bone.rotation_euler
    angle_deg = math.degrees(euler_rot[axis])
    if invert: angle_deg = -angle_deg
    return angle_deg

def send_bone_angles(scene, depsgraph):
    """Calculates angles and sends them to the Raspberry Pi AND Dashboard over UDP."""
    global last_send_monotonic, last_sent_body, last_sent_arm, filtered_body, filtered_arm

    armature = bpy.data.objects.get(ARMATURE_NAME)
    if not armature or armature.type != 'ARMATURE': return
    armature_eval = armature.evaluated_get(depsgraph)

    body_angle = get_bone_angle_degrees(armature_eval, BODY_BONE_NAME, BODY_ROTATION_AXIS, BODY_INVERT_DEGREE)
    arm_angle = get_bone_angle_degrees(armature_eval, ARM_BONE_NAME, ARM_ROTATION_AXIS, ARM_INVERT_DEGREE)

    # Send via UDP if we have data
    if body_angle is not None and arm_angle is not None:
        body_unclamped = BODY_SERVO_AT_BONE_ZERO + float(body_angle)
        arm_unclamped = ARM_SERVO_AT_BONE_ZERO + float(arm_angle)

        body_absolute = to_absolute_servo_angle(body_angle, BODY_SERVO_AT_BONE_ZERO)
        arm_absolute = to_absolute_servo_angle(arm_angle, ARM_SERVO_AT_BONE_ZERO)

        filtered_body = low_pass(filtered_body, body_absolute, SMOOTHING_ALPHA)
        filtered_arm = low_pass(filtered_arm, arm_absolute, SMOOTHING_ALPHA)

        now = time.monotonic()
        min_interval = 1.0 / max(SEND_RATE_HZ, 1.0)
        if now - last_send_monotonic < min_interval:
            return

        tx_body = filtered_body
        tx_arm = filtered_arm

        if (
            last_sent_body is not None
            and abs(tx_body - last_sent_body) < SEND_DEADBAND_DEG
            and abs(tx_arm - last_sent_arm) < SEND_DEADBAND_DEG
        ):
            return

        payload = {
            "body": tx_body,
            "arm": tx_arm,
            "source": "blender",
        }

        encoded_payload = json.dumps(payload).encode('utf-8')

        # 1. Send JSON packet to Hardware (Raspberry Pi)
        hardware_sock.sendto(encoded_payload, (RPI_IP, UDP_PORT))

        # 2. Send JSON packet to Dashboard (Relay Server)
        dashboard_sock.sendto(encoded_payload, (DASHBOARD_IP, DASHBOARD_PORT))

        last_send_monotonic = now
        last_sent_body = tx_body
        last_sent_arm = tx_arm

        # Blender API state sync print disabled for now.
        body_clip = " [CLAMP]" if abs(body_absolute - body_unclamped) > 1e-6 else ""
        arm_clip = " [CLAMP]" if abs(arm_absolute - arm_unclamped) > 1e-6 else ""
        print(
            f"Sent -> Body raw {body_angle:>6.2f}° => {body_absolute:>6.2f}°{body_clip} -> tx {tx_body:>6.2f}° | "
            f"Arm raw {arm_angle:>6.2f}° => {arm_absolute:>6.2f}°{arm_clip} -> tx {tx_arm:>6.2f}°"
        )

# ==========================================
# REGISTER HANDLER
# ==========================================
bpy.app.handlers.depsgraph_update_post.clear()
bpy.app.handlers.depsgraph_update_post.append(send_bone_angles)
print(
    f"Started monitoring and streaming to Hardware ({RPI_IP}:{UDP_PORT}) "
    f"and Dashboard ({DASHBOARD_IP}:{DASHBOARD_PORT})!"
)