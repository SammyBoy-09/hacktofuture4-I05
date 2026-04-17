#!/usr/bin/env python3
"""
TWINK3.0: Dual-servo controller with both CLI commands and Blender UDP input.

Profiles used:
- BODY uses servo1.0.py mapping on GPIO 20 with servo1_calibration.json
- ARM  uses servo2.0.py mapping on GPIO 21 with servo2_calibration.json

Calibration editing commands are intentionally omitted here.
Use servo1.0.py and servo2.0.py when you want to recalibrate endpoints.
"""

import json
import os
import socket
import threading
import time

import pigpio


# ---------------------------------------------------------------------------
# Hardware + files
# ---------------------------------------------------------------------------
BODY_SERVO_PIN = 21
ARM_SERVO_PIN = 20

BODY_CONFIG_PATH = "servo2_calibration.json"
ARM_CONFIG_PATH = "servo1_calibration.json"


# ---------------------------------------------------------------------------
# UDP input (from Blender)
# ---------------------------------------------------------------------------
UDP_IP = "0.0.0.0"
UDP_PORT = 5005
UDP_BUFFER_SIZE = 2048
UDP_TIMEOUT_SEC = 0.2


# ---------------------------------------------------------------------------
# Shared motion constants
# ---------------------------------------------------------------------------
HARD_MIN_US = 500
HARD_MAX_US = 2500

ANGLE_MIN = 0.0
ANGLE_MAX = 180.0

MOVE_STEP_DEG = 1.0
MOVE_STEP_DELAY = 0.02
SETTLE_DELAY = 0.12
TARGET_EPSILON = 0.35
IDLE_LOOP_DELAY = 0.01

# Direct control mode removes motion interpolation for lower latency.
DIRECT_APPLY_MODE = True
INPUT_DEADBAND_DEG = 0.2


# ---------------------------------------------------------------------------
# Servo2 profile (from servo2.0.py)
# ---------------------------------------------------------------------------
SERVO2_DEFAULT_MIN_US = 1000
SERVO2_DEFAULT_MAX_US = 2000


# ---------------------------------------------------------------------------
# Servo1 profile (from servo1.0.py)
# ---------------------------------------------------------------------------
LEGACY_SIGNAL_AT_PHYS_0 = 109.0
LEGACY_SIGNAL_AT_PHYS_180 = 30.0
ZERO_OFFSET_LIMIT_US = 500


def clamp(value, low, high):
	return max(low, min(high, value))


def signal_angle_to_pulse_us(signal_angle):
	signal_angle = clamp(float(signal_angle), 0.0, 180.0)
	pulse = 500.0 + (signal_angle / 180.0) * 2000.0
	return int(round(clamp(pulse, HARD_MIN_US, HARD_MAX_US)))


SERVO1_DEFAULT_MIN_US = signal_angle_to_pulse_us(LEGACY_SIGNAL_AT_PHYS_180)
SERVO1_DEFAULT_MAX_US = signal_angle_to_pulse_us(LEGACY_SIGNAL_AT_PHYS_0)
SERVO1_DEFAULT_REVERSE = True
SERVO1_DEFAULT_ZERO_OFFSET_US = 0


def apply_pulse(pi, gpio, pulse_us):
	pulse_us = int(clamp(pulse_us, HARD_MIN_US, HARD_MAX_US))
	pi.set_servo_pulsewidth(gpio, pulse_us)


# ---------------------------------------------------------------------------
# Servo2 config + mapping
# ---------------------------------------------------------------------------
def load_servo2_config(path):
	config = {
		"min_us": SERVO2_DEFAULT_MIN_US,
		"max_us": SERVO2_DEFAULT_MAX_US,
		"reverse": False,
		"current_angle": 90.0,
	}

	if not os.path.exists(path):
		return config

	try:
		with open(path, "r", encoding="utf-8") as f:
			data = json.load(f)
		config["min_us"] = int(clamp(data.get("min_us", config["min_us"]), HARD_MIN_US, HARD_MAX_US))
		config["max_us"] = int(clamp(data.get("max_us", config["max_us"]), HARD_MIN_US, HARD_MAX_US))
		config["reverse"] = bool(data.get("reverse", config["reverse"]))
		config["current_angle"] = float(
			clamp(data.get("current_angle", config["current_angle"]), ANGLE_MIN, ANGLE_MAX)
		)
	except (OSError, ValueError, TypeError):
		print("Warning: could not read servo2 calibration file. Using defaults.")

	if config["min_us"] == config["max_us"]:
		config["max_us"] = config["min_us"] + 1

	return config


def save_servo2_config(path, cfg):
	data = {
		"min_us": int(cfg["min_us"]),
		"max_us": int(cfg["max_us"]),
		"reverse": bool(cfg["reverse"]),
		"current_angle": float(cfg["current_angle"]),
	}
	with open(path, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=2)


def servo2_logical_to_pulse_us(angle, cfg):
	angle = clamp(float(angle), ANGLE_MIN, ANGLE_MAX)
	mapped = (ANGLE_MAX - angle) if cfg["reverse"] else angle
	span = cfg["max_us"] - cfg["min_us"]
	pulse = cfg["min_us"] + (mapped / ANGLE_MAX) * span
	return int(round(clamp(pulse, HARD_MIN_US, HARD_MAX_US)))


# ---------------------------------------------------------------------------
# Servo1 config + mapping
# ---------------------------------------------------------------------------
def normalize_servo1_center(cfg):
	low = min(cfg["min_us"], cfg["max_us"])
	high = max(cfg["min_us"], cfg["max_us"])
	if "center_us" not in cfg:
		cfg["center_us"] = int(round((low + high) / 2.0))
	cfg["center_us"] = int(clamp(cfg["center_us"], low, high))


def load_servo1_config(path):
	config = {
		"min_us": SERVO1_DEFAULT_MIN_US,
		"max_us": SERVO1_DEFAULT_MAX_US,
		"center_us": int(round((SERVO1_DEFAULT_MIN_US + SERVO1_DEFAULT_MAX_US) / 2.0)),
		"zero_offset_us": SERVO1_DEFAULT_ZERO_OFFSET_US,
		"reverse": SERVO1_DEFAULT_REVERSE,
		"current_angle": 90.0,
	}

	if not os.path.exists(path):
		return config

	try:
		with open(path, "r", encoding="utf-8") as f:
			data = json.load(f)
		config["min_us"] = int(clamp(data.get("min_us", config["min_us"]), HARD_MIN_US, HARD_MAX_US))
		config["max_us"] = int(clamp(data.get("max_us", config["max_us"]), HARD_MIN_US, HARD_MAX_US))
		default_center = int(round((config["min_us"] + config["max_us"]) / 2.0))
		config["center_us"] = int(data.get("center_us", default_center))
		config["zero_offset_us"] = int(
			clamp(data.get("zero_offset_us", config["zero_offset_us"]), -ZERO_OFFSET_LIMIT_US, ZERO_OFFSET_LIMIT_US)
		)
		config["reverse"] = bool(data.get("reverse", config["reverse"]))
		config["current_angle"] = float(
			clamp(data.get("current_angle", config["current_angle"]), ANGLE_MIN, ANGLE_MAX)
		)
	except (OSError, ValueError, TypeError):
		print("Warning: could not read servo1 calibration file. Using defaults.")

	if config["min_us"] == config["max_us"]:
		config["max_us"] = config["min_us"] + 1
	normalize_servo1_center(config)
	return config


def save_servo1_config(path, cfg):
	data = {
		"min_us": int(cfg["min_us"]),
		"max_us": int(cfg["max_us"]),
		"center_us": int(cfg["center_us"]),
		"zero_offset_us": int(cfg["zero_offset_us"]),
		"reverse": bool(cfg["reverse"]),
		"current_angle": float(cfg["current_angle"]),
	}
	with open(path, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=2)


def servo1_logical_to_pulse_us(angle, cfg):
	angle = clamp(float(angle), ANGLE_MIN, ANGLE_MAX)
	mapped = (ANGLE_MAX - angle) if cfg["reverse"] else angle

	if mapped <= 90.0:
		pulse = cfg["min_us"] + (mapped / 90.0) * (cfg["center_us"] - cfg["min_us"])
	else:
		pulse = cfg["center_us"] + ((mapped - 90.0) / 90.0) * (cfg["max_us"] - cfg["center_us"])

	if angle <= 90.0:
		zero_factor = (90.0 - angle) / 90.0
		pulse += cfg["zero_offset_us"] * zero_factor

	return int(round(clamp(pulse, HARD_MIN_US, HARD_MAX_US)))


# ---------------------------------------------------------------------------
# Motion worker helpers (latest-value-wins)
# ---------------------------------------------------------------------------
def set_latest_target(servo, angle):
	angle = clamp(float(angle), ANGLE_MIN, ANGLE_MAX)
	with servo["lock"]:
		old_target = servo["motion"]["target_angle"]
		servo["motion"]["target_angle"] = angle
	return old_target, angle


def set_target_immediate(pi, servo, angle, deadband_deg=0.0):
	angle = clamp(float(angle), ANGLE_MIN, ANGLE_MAX)
	with servo["lock"]:
		old_target = servo["motion"]["target_angle"]
		if abs(angle - old_target) <= float(deadband_deg):
			pulse_us = servo["mapper"](old_target, servo["cfg"])
			return old_target, old_target, pulse_us, False

		servo["motion"]["target_angle"] = angle
		servo["motion"]["current_angle"] = angle
		servo["cfg"]["current_angle"] = angle
		pulse_us = servo["mapper"](angle, servo["cfg"])

	apply_pulse(pi, servo["gpio"], pulse_us)
	return old_target, angle, pulse_us, True


def wait_for_target(servo, stop_event, desired_angle):
	desired_angle = clamp(float(desired_angle), ANGLE_MIN, ANGLE_MAX)
	while not stop_event.is_set():
		with servo["lock"]:
			current = servo["motion"]["current_angle"]
			target = servo["motion"]["target_angle"]
		if abs(current - desired_angle) <= TARGET_EPSILON and abs(target - desired_angle) <= TARGET_EPSILON:
			return True
		time.sleep(IDLE_LOOP_DELAY)
	return False


def motion_worker(pi, servo, stop_event):
	while not stop_event.is_set():
		with servo["lock"]:
			current = servo["motion"]["current_angle"]
			target = servo["motion"]["target_angle"]

		if abs(target - current) <= TARGET_EPSILON:
			time.sleep(IDLE_LOOP_DELAY)
			continue

		step = MOVE_STEP_DEG if target > current else -MOVE_STEP_DEG
		next_angle = current + step
		if (step > 0 and next_angle > target) or (step < 0 and next_angle < target):
			next_angle = target

		with servo["lock"]:
			pulse_us = servo["mapper"](next_angle, servo["cfg"])

		apply_pulse(pi, servo["gpio"], pulse_us)

		with servo["lock"]:
			servo["motion"]["current_angle"] = next_angle
			servo["cfg"]["current_angle"] = next_angle

		time.sleep(MOVE_STEP_DELAY)


def run_sweep(pi, servo, stop_event):
	print(f"Sweeping {servo['name']} 0 -> 180 -> 0")
	for desired in (0, 180, 0):
		if DIRECT_APPLY_MODE:
			set_target_immediate(pi, servo, desired)
			time.sleep(SETTLE_DELAY)
		else:
			set_latest_target(servo, desired)
			if not wait_for_target(servo, stop_event, desired):
				break
	time.sleep(SETTLE_DELAY)


# ---------------------------------------------------------------------------
# Servo model + printing
# ---------------------------------------------------------------------------
def build_servo(name, gpio, profile, cfg_path):
	if profile == "servo1":
		cfg = load_servo1_config(cfg_path)
		mapper = servo1_logical_to_pulse_us
		saver = save_servo1_config
	else:
		cfg = load_servo2_config(cfg_path)
		mapper = servo2_logical_to_pulse_us
		saver = save_servo2_config

	current_angle = clamp(float(cfg.get("current_angle", 90.0)), ANGLE_MIN, ANGLE_MAX)
	cfg["current_angle"] = current_angle

	return {
		"name": name,
		"gpio": gpio,
		"profile": profile,
		"cfg_path": cfg_path,
		"cfg": cfg,
		"mapper": mapper,
		"saver": saver,
		"lock": threading.Lock(),
		"motion": {
			"current_angle": current_angle,
			"target_angle": current_angle,
		},
	}


def print_servo_cal(servo):
	with servo["lock"]:
		cfg = dict(servo["cfg"])

	p0 = servo["mapper"](0.0, cfg)
	p90 = servo["mapper"](90.0, cfg)
	p180 = servo["mapper"](180.0, cfg)

	print(f"\n[{servo['name']}] mapping ({servo['profile']})")
	print("-" * 56)
	if servo["profile"] == "servo1":
		print(f"  min_us: {cfg['min_us']} us")
		print(f"  center_us: {cfg['center_us']} us")
		print(f"  max_us: {cfg['max_us']} us")
		print(f"  zero_offset_us: {cfg['zero_offset_us']} us")
		print(f"  reverse: {cfg['reverse']}")
	else:
		print(f"  min_us: {cfg['min_us']} us")
		print(f"  max_us: {cfg['max_us']} us")
		print(f"  reverse: {cfg['reverse']}")
	print(f"  map: 0 -> {p0} us | 90 -> {p90} us | 180 -> {p180} us")
	print("-" * 56)


def print_pos(servo):
	with servo["lock"]:
		current = servo["motion"]["current_angle"]
		target = servo["motion"]["target_angle"]
		pulse_target = servo["mapper"](target, servo["cfg"])
	print(f"{servo['name']}: current={current:.1f} deg target={target:.1f} deg ({pulse_target} us)")


def save_one(servo):
	with servo["lock"]:
		cfg_copy = dict(servo["cfg"])
	servo["saver"](servo["cfg_path"], cfg_copy)


def build_state(servos):
	state = {}
	for key, servo in servos.items():
		with servo["lock"]:
			current = float(servo["motion"]["current_angle"])
			target = float(servo["motion"]["target_angle"])
			cfg = dict(servo["cfg"])
		state[key] = {
			"current_angle": current,
			"target_angle": target,
			"current_pulse_us": int(servo["mapper"](current, cfg)),
			"target_pulse_us": int(servo["mapper"](target, cfg)),
			"gpio": servo["gpio"],
			"profile": servo["profile"],
		}
	state["timestamp"] = time.time()
	return state


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------
def resolve_servo_token(token):
	tok = token.strip().lower()
	if tok in ("body", "servo1", "s1"):
		return "body"
	if tok in ("arm", "servo2", "s2"):
		return "arm"
	if tok in ("both", "all"):
		return "both"
	return None


def selected_servos(servos, token, allow_both=True):
	key = resolve_servo_token(token)
	if key is None:
		return None
	if key == "both":
		return [servos["body"], servos["arm"]] if allow_both else None
	return [servos[key]]


def print_help():
	print("\nCommands")
	print("-" * 72)
	print("  g <body|arm> <angle>             Set latest target angle 0..180")
	print("  g both <body_angle> <arm_angle>  Set both target angles")
	print("  pos [body|arm|both]              Show position(s)")
	print("  center [body|arm|both]           Move target to 90")
	print("  sweep [body|arm|both]            Sweep 0 -> 180 -> 0")
	print("  us <body|arm> <pulse_us>         Send raw pulse width (500..2500)")
	print("  reverse <body|arm|both>          Toggle reverse mapping")
	print("  reverse <body|arm|both> on|off   Set reverse mapping")
	print("  off [body|arm|both]              Stop servo pulses")
	print("  save [body|arm|all]              Save calibration file(s)")
	print("  help                             Show commands")
	print("  q                                Quit")
	print("-" * 72)
	print("Calibration editing commands are disabled in twink3.0.")


def udp_receiver_loop(sock, pi, servos, stop_event):
	while not stop_event.is_set():
		try:
			data, addr = sock.recvfrom(UDP_BUFFER_SIZE)
		except socket.timeout:
			continue
		except OSError:
			break

		try:
			payload = json.loads(data.decode("utf-8"))
		except (UnicodeDecodeError, json.JSONDecodeError):
			continue

		if not isinstance(payload, dict):
			continue

		updates = []

		if "body" in payload:
			try:
				if DIRECT_APPLY_MODE:
					old_target, new_target, _, changed = set_target_immediate(
						pi,
						servos["body"],
						float(payload["body"]),
						deadband_deg=INPUT_DEADBAND_DEG,
					)
					if changed:
						updates.append(f"body {old_target:.1f}->{new_target:.1f}")
				else:
					old_target, new_target = set_latest_target(servos["body"], float(payload["body"]))
					updates.append(f"body {old_target:.1f}->{new_target:.1f}")
			except (TypeError, ValueError):
				pass

		if "arm" in payload:
			try:
				if DIRECT_APPLY_MODE:
					old_target, new_target, _, changed = set_target_immediate(
						pi,
						servos["arm"],
						float(payload["arm"]),
						deadband_deg=INPUT_DEADBAND_DEG,
					)
					if changed:
						updates.append(f"arm {old_target:.1f}->{new_target:.1f}")
				else:
					old_target, new_target = set_latest_target(servos["arm"], float(payload["arm"]))
					updates.append(f"arm {old_target:.1f}->{new_target:.1f}")
			except (TypeError, ValueError):
				pass

		command = str(payload.get("command", "")).strip().lower()
		if command == "off":
			for servo in servos.values():
				with servo["lock"]:
					servo["motion"]["target_angle"] = servo["motion"]["current_angle"]
				pi.set_servo_pulsewidth(servo["gpio"], 0)
				updates.append(f"{servo['name']} off")

		if payload.get("request_state", False):
			response = {
				"ok": True,
				"state": build_state(servos),
			}
			reply_addr = addr
			if "reply_port" in payload:
				try:
					port = int(payload["reply_port"])
					if 1 <= port <= 65535:
						reply_addr = (addr[0], port)
				except (TypeError, ValueError):
					pass
			try:
				sock.sendto(json.dumps(response).encode("utf-8"), reply_addr)
			except OSError:
				pass

		if updates:
			print(f"UDP {addr}: " + " | ".join(updates))


def main():
	print("Connecting to pigpio daemon...")
	pi = pigpio.pi()
	if not pi.connected:
		raise RuntimeError("pigpio daemon not running. Start with: sudo pigpiod")

	servos = {
		"body": build_servo("body", ARM_SERVO_PIN, "servo1", ARM_CONFIG_PATH),
		"arm": build_servo("arm", BODY_SERVO_PIN, "servo2", BODY_CONFIG_PATH),
	}

	for servo in servos.values():
		with servo["lock"]:
			startup_angle = servo["motion"]["current_angle"]
			startup_pulse = servo["mapper"](startup_angle, servo["cfg"])
		apply_pulse(pi, servo["gpio"], startup_pulse)

	stop_event = threading.Event()

	workers = []
	if not DIRECT_APPLY_MODE:
		for servo in servos.values():
			worker = threading.Thread(target=motion_worker, args=(pi, servo, stop_event), daemon=True)
			worker.start()
			workers.append(worker)

	udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	udp_sock.bind((UDP_IP, UDP_PORT))
	udp_sock.settimeout(UDP_TIMEOUT_SEC)

	udp_thread = threading.Thread(target=udp_receiver_loop, args=(udp_sock, pi, servos, stop_event), daemon=True)
	udp_thread.start()

	print("=" * 72)
	print("TWINK3.0 DUAL SERVO CONTROLLER (CLI + BLENDER UDP)")
	print("=" * 72)
	print(f"Body: GPIO {ARM_SERVO_PIN}, profile servo1, cfg {ARM_CONFIG_PATH}")
	print(f"Arm:  GPIO {BODY_SERVO_PIN}, profile servo2, cfg {BODY_CONFIG_PATH}")
	print(f"UDP input: {UDP_IP}:{UDP_PORT}")
	if DIRECT_APPLY_MODE:
		print(f"Motion mode: direct apply (deadband {INPUT_DEADBAND_DEG:.2f} deg)")
	else:
		print("Motion mode: latest-value-wins")
	print_servo_cal(servos["body"])
	print_servo_cal(servos["arm"])
	print_help()

	try:
		while True:
			try:
				cmd = input("\n> ").strip().lower()
			except EOFError:
				break

			if not cmd:
				continue

			parts = cmd.split()
			head = parts[0]

			if head == "q":
				break

			if head == "help":
				print_help()
				continue

			if head == "save":
				target = "all" if len(parts) == 1 else parts[1]
				selected = selected_servos(servos, target, allow_both=True)
				if selected is None:
					print("Usage: save [body|arm|all]")
					continue
				for servo in selected:
					try:
						save_one(servo)
						print(f"Saved {servo['name']} calibration -> {servo['cfg_path']}")
					except OSError:
						print(f"Could not save {servo['name']} calibration")
				continue

			if head == "pos":
				target = "both" if len(parts) == 1 else parts[1]
				selected = selected_servos(servos, target, allow_both=True)
				if selected is None:
					print("Usage: pos [body|arm|both]")
					continue
				for servo in selected:
					print_pos(servo)
				continue

			if head == "g":
				if len(parts) < 3:
					print("Usage: g <body|arm> <angle> | g both <body_angle> <arm_angle>")
					continue

				target = resolve_servo_token(parts[1])
				if target is None:
					print("Usage: g <body|arm> <angle> | g both <body_angle> <arm_angle>")
					continue

				if target == "both":
					if len(parts) != 4:
						print("Usage: g both <body_angle> <arm_angle>")
						continue
					try:
						body_angle = float(parts[2])
						arm_angle = float(parts[3])
					except ValueError:
						print("Angles must be numbers")
						continue

					if DIRECT_APPLY_MODE:
						old_b, new_b, pulse_b, _ = set_target_immediate(pi, servos["body"], body_angle)
						old_a, new_a, pulse_a, _ = set_target_immediate(pi, servos["arm"], arm_angle)
						print(
							f"body target {old_b:.1f} -> {new_b:.1f} deg ({pulse_b} us) | "
							f"arm target {old_a:.1f} -> {new_a:.1f} deg ({pulse_a} us)"
						)
					else:
						old_b, new_b = set_latest_target(servos["body"], body_angle)
						old_a, new_a = set_latest_target(servos["arm"], arm_angle)
						print(
							f"body target {old_b:.1f} -> {new_b:.1f} deg | "
							f"arm target {old_a:.1f} -> {new_a:.1f} deg"
						)
				else:
					if len(parts) != 3:
						print("Usage: g <body|arm> <angle>")
						continue
					try:
						angle = float(parts[2])
					except ValueError:
						print("Angle must be a number")
						continue

					servo = servos[target]
					if DIRECT_APPLY_MODE:
						old_target, new_target, pulse, _ = set_target_immediate(pi, servo, angle)
					else:
						old_target, new_target = set_latest_target(servo, angle)
						with servo["lock"]:
							pulse = servo["mapper"](new_target, servo["cfg"])
					print(f"{target} target {old_target:.1f} -> {new_target:.1f} deg ({pulse} us)")
				continue

			if head == "center":
				target = "both" if len(parts) == 1 else parts[1]
				selected = selected_servos(servos, target, allow_both=True)
				if selected is None:
					print("Usage: center [body|arm|both]")
					continue
				for servo in selected:
					if DIRECT_APPLY_MODE:
						old_target, new_target, _, _ = set_target_immediate(pi, servo, 90.0)
					else:
						old_target, new_target = set_latest_target(servo, 90.0)
					print(f"{servo['name']} target {old_target:.1f} -> {new_target:.1f} deg")
				continue

			if head == "sweep":
				target = "both" if len(parts) == 1 else parts[1]
				selected = selected_servos(servos, target, allow_both=True)
				if selected is None:
					print("Usage: sweep [body|arm|both]")
					continue
				for servo in selected:
					run_sweep(pi, servo, stop_event)
				continue

			if head == "off":
				target = "both" if len(parts) == 1 else parts[1]
				selected = selected_servos(servos, target, allow_both=True)
				if selected is None:
					print("Usage: off [body|arm|both]")
					continue
				for servo in selected:
					with servo["lock"]:
						servo["motion"]["target_angle"] = servo["motion"]["current_angle"]
					pi.set_servo_pulsewidth(servo["gpio"], 0)
					print(f"{servo['name']} pulses stopped")
				continue

			if head == "us":
				if len(parts) != 3:
					print("Usage: us <body|arm> <pulse_us>")
					continue
				target = resolve_servo_token(parts[1])
				if target is None or target == "both":
					print("Usage: us <body|arm> <pulse_us>")
					continue
				try:
					pulse = int(float(parts[2]))
				except ValueError:
					print("Pulse must be a number")
					continue
				if not (HARD_MIN_US <= pulse <= HARD_MAX_US):
					print("Pulse must be in range 500..2500")
					continue
				apply_pulse(pi, servos[target]["gpio"], pulse)
				print(f"Applied raw pulse on {target}: {pulse} us")
				continue

			if head == "reverse":
				if len(parts) < 2 or len(parts) > 3:
					print("Usage: reverse <body|arm|both> [on|off]")
					continue
				selected = selected_servos(servos, parts[1], allow_both=True)
				if selected is None:
					print("Usage: reverse <body|arm|both> [on|off]")
					continue

				explicit = None
				if len(parts) == 3:
					if parts[2] not in ("on", "off"):
						print("Usage: reverse <body|arm|both> [on|off]")
						continue
					explicit = parts[2] == "on"

				for servo in selected:
					with servo["lock"]:
						if explicit is None:
							servo["cfg"]["reverse"] = not servo["cfg"]["reverse"]
						else:
							servo["cfg"]["reverse"] = explicit
						print(f"{servo['name']} reverse is now {servo['cfg']['reverse']}")
					print_servo_cal(servo)
				continue

			if head == "cal":
				print("Calibration commands are disabled in twink3.0. Use servo1.0.py / servo2.0.py.")
				continue

			print("Unknown command. Type help")

	except KeyboardInterrupt:
		print("\nStopped by user")
	finally:
		stop_event.set()

		try:
			udp_sock.close()
		except OSError:
			pass

		udp_thread.join(timeout=1.0)

		for worker in workers:
			worker.join(timeout=1.0)

		for servo in servos.values():
			try:
				save_one(servo)
			except OSError:
				print(f"Warning: could not save {servo['name']} calibration")
			pi.set_servo_pulsewidth(servo["gpio"], 0)

		pi.stop()
		print("GPIO cleanup complete")


if __name__ == "__main__":
	main()
