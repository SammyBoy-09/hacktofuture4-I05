import os
from dotenv import load_dotenv

load_dotenv()

import instructor
from google import genai
from schema import RoboticSequence

# 1. Check for the API Key
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is missing! Check your .env file.")

# 2. Initialize the GenAI Client
gemini_client = genai.Client()

# 3. Wrap the client with Instructor
client = instructor.from_genai(gemini_client)

def generate_robot_instruction(user_prompt: str) -> RoboticSequence:
    """Translates human English into a sequential, hardware-locked plan."""
    
    print(f"Asking Gemini to process: '{user_prompt}'...")
    
    try:
        # 4. Call the LLM
        instruction = client.chat.completions.create(
            model="gemini-2.0-flash",
            response_model=RoboticSequence,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the reasoning engine for an industrial robotic arm.\n"
                        "HARDWARE RULES:\n"
                        "- Gripper: 0 is closed (grab). 85 is open (release).\n"
                        "- Body Tilt: 45 is leaning forward. 90 is upright. 110 is leaning back.\n\n"
                        "CRITICAL PHYSICS & LOGIC RULES:\n"
                        "1. VISION RULE: ONLY use 'verify_vision' if the user asks to interact with a specific object. If the user just asks to move or drop an item, DO NOT use 'verify_vision'.\n"
                        "2. STATE MEMORY: If you move one joint, you MUST copy the exact angle of the other joint from the previous step. Do not let it reset to 0 unless you intend to move it to 0.\n"
                        "3. ONE AT A TIME: Never change the gripper angle and the body tilt in the same step.\n"
                        "4. CLEARANCE & PLACEMENT: If the gripper is empty, it must be fully open (85) before tilting forward. However, if you are holding an object (gripper is 0), you ARE allowed to tilt forward to place it on the table.\n\n"
                        "EXAMPLE 1: OBJECT INTERACTION ('Pick up the box'):\n"
                        "Step 1: verify_vision (Ensure box is there. gripper: 0, body: 90)\n"
                        "Step 2: open gripper. (gripper changes to 85. body STAYS at 90)\n"
                        "Step 3: tilt forward. (gripper STAYS at 85. body changes to 45)\n"
                        "Step 4: close gripper. (gripper changes to 0. body STAYS at 45)\n"
                        "Step 5: tilt upright. (gripper STAYS at 0. body changes to 90)\n\n"
                        "EXAMPLE 2: PURE MOVEMENT ('Bend forward and come back'):\n"
                        "Step 1: open gripper. (Clearance rule! gripper changes to 85, body STAYS at 90)\n"
                        "Step 2: tilt forward. (gripper STAYS at 85, body changes to 45)\n"
                        "Step 3: tilt upright. (gripper STAYS at 85, body changes to 90)\n"
                        "Step 4: close gripper. (Return to default. gripper changes to 0, body STAYS at 90)\n\n"
                        "EXAMPLE 3: PLACING/DROPPING ('Put the box down' or 'Please drop it'):\n"
                        "Step 1: tilt forward. (Lower the object to the table. gripper STAYS at 0, body changes to 45)\n"
                        "Step 2: open gripper. (Release the object. gripper changes to 85, body STAYS at 45)\n"
                        "Step 3: tilt upright. (Return to neutral. gripper STAYS at 85, body changes to 90)"
                    )
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        )
        
        return instruction
    except Exception as e:
        print(f"Gemini API Error (Likely Rate Limit): {e}")
        from schema import RobotStep
        return RoboticSequence(
            task_name="Demo Fallback Task (Rate Limit)",
            steps=[
                RobotStep(action_type="actuate_joints", gripper_angle=0, body_tilt=90),
                RobotStep(action_type="actuate_joints", gripper_angle=85, body_tilt=90),
                RobotStep(action_type="actuate_joints", gripper_angle=0, body_tilt=90)
            ]
        )

# --- Test the Agent in the Terminal ---
if __name__ == "__main__":
    prompt = "Please drop what the gripper is holding."
    
    try:
        result = generate_robot_instruction(prompt)
        print("\n--- GEMINI OUTPUT (HARDWARE SEQUENCE) ---")
        print(result.model_dump_json(indent=2))
    except Exception as e:
        print(f"\nError: {e}")