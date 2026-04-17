<div align="center">

# 🤖 Obsidian - I05
### AI-Driven Digital-Twin Dashboard

[![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](#)
[![Vite](https://img.shields.io/badge/Vite-B73BFE?style=for-the-badge&logo=vite&logoColor=FFD62E)](#)
[![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white)](#)
[![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)](#)
<br>
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![Three.js](https://img.shields.io/badge/ThreeJs-black?style=for-the-badge&logo=three.js&logoColor=white)](#)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-A22846?style=for-the-badge&logo=Raspberry%20Pi&logoColor=white)](#)
[![YOLO](https://img.shields.io/badge/YOLO-Ultralytics-blue?style=for-the-badge)](#)
[![Gemini](https://img.shields.io/badge/Google_Gemini-8E75B2?style=for-the-badge&logo=googlebard&logoColor=white)](#)

*An AI-native Digital Twin platform delivering real-time system monitoring, interactive simulation, and experiential learning, bridging education and industry through a unified digital environment.*

<!-- Placeholder for a main dashboard hero screenshot
![Main Dashboard Hero Outline](https://via.placeholder.com/900x450/1f2937/FFFFFF?text=Dashboard+Screenshot+Here)
-->

---

</div>

## 🎯 Problem Statement / Idea

### ❓ What is the problem?
> "Lack of safe, scalable, real-time experimentation environments limits students and industries with real-time visibility, restricting their ability to simulate, analyse, and understand operational conditions—impacting learning, and innovation."

### ❗ Why is it important?
| Area | Impact |
| :---: | :--- |
| 👩‍🎓 **Learning** | Limits hands-on learning and real-world system understanding. |
| 🛡️ **Safety** | Restricts safe experimentation and exploration of different scenarios. |
| 👁️ **Visibility** | Prevents accurate risk anticipation and operational optimization. |
| 📉 **Scalability** | Increases costs, safety risks, and limits scalable innovation. |

### 👥 Who are the target users?
- 🎓 **Education sector**
- 🏭 **Industries**

---

## 💡 Proposed Solution & Uniqueness

**What are you building?** 
An AI-native Digital Twin platform delivering real-time system monitoring, interactive simulation, and experiential learning, bridging education and industry through a unified digital environment.

### 🛠️ How does it solve the problem?
- **Hands-on Experience:** Enables hands-on learning through interactive digital replicas of real systems without requiring full physical lab setups.
- **Safe Execution:** Allows safe execution of experiments and "what-if" scenarios to improve conceptual understanding.
- **On-Demand Access:** Removes dependency on limited lab time and expensive hardware by providing anytime, scalable access to simulations.
- **Real-Time Observability:** Provides real-time monitoring of machines and processes for better operational visibility.
- **Proactive Simulation:** Enables simulation of operational conditions to test scenarios, improve decision-making, and reduce risk before real-world execution.

### ✨ What makes your solution unique?
1. 📷 **Edge Computer Vision:** Uses cameras as smart sensors, reducing hardware complexity and cost.
2. 🔄 **Real-Time Orchestration:** Enables continuous synchronization between physical and digital systems.
3. 🧠 **Intelligent Telemetry:** Converts live machine data into meaningful insights through AI analysis.
4. 🔮 **Predictive Capability:** Anticipates failures before they happen, improving efficiency and reliability.
5. 🔗 **Unified Architecture:** Integrates multiple technologies into one seamless system instead of fragmented tools.
6. 📈 **Scalable & Adaptable:** Works across different industries and environments without major redesign.
7. 🤖 **AI-Native Core:** Built with intelligence from the ground up for real-time understanding and decisions.

---

## ✨ Features Array

<details>
<summary><b>⏪ Predicting the Past — Data Replay</b></summary>
<br>

- Replays historical 3D system behavior to uncover hidden patterns, inefficiencies, and gradual mechanical drift.
</details>

<details open>
<summary><b>▶️ Monitoring the Present — Real-Time Observability</b></summary>
<br>

- 👁️ **Markerless Spatial Tracking:** Uses edge AI and computer vision for real-time analysis, eliminating dependence on complex sensor setups.  
- ⏱️ **Bidirectional Synchronization:** Maintains a low-latency connection between physical systems and the digital twin for seamless interaction.  
- 🩺 **Live Health Monitoring:** Streams critical parameters like torque, temperature, and system latency to ensure safe and stable operations.  
</details>

<details>
<summary><b>⏩ Predicting the Future — Simulation & Predictive Intelligence</b></summary>
<br>

- 🚀 **Risk-Free Simulation:** Tests different operational scenarios in a virtual environment before applying them to real systems.  
- 🛠️ **Predictive Maintenance:** Uses machine learning on live telemetry to forecast failures and prevent unplanned downtime.  
- 🛡️ **Adaptive Safety Intelligence:** Anticipates potential risks such as collisions or system errors and proactively prevents them.  
</details>

---

## 🛠️ Tech Stack & Systems Architecture

### 🌐 Frontend
- **Core Library:** React (with React Router for navigation)
- **3D Rendering:** Three.js, React Three Fiber (`@react-three/fiber`), and React Three Drei (used for rendering the `body.glb` 3D model)
- **Styling:** Tailwind CSS (v4)
- **Build Tool:** Vite

### ⚙️ Backend
- **Framework:** FastAPI (Python)
- **Server:** Uvicorn (ASGI web server)
- **Communication:**
  - **WebSockets:** Used for real-time bidirectional teleop control and streaming video feeds from the Android/Mobile camera to the dashboard.
  - **UDP Sockets:** Used for fast, low-latency streaming of servo coordinates directly to the hardware.

### 🧠 Computer Vision & AI
- **Vision Models:** Ultralytics YOLO (for side-view body pose detection, top-view arm/gripper detection, and bounding box detection)
- **Image Processing:** OpenCV (`cv2`) (decodes base64 frames, annotates them, and re-encodes them to broadcast back to the frontend)
- **Large Language Model (LLM):** Google GenAI (using the `gemini-2.0-flash` model) to translate human text prompts into sequential, hardware-locked robotic instructions.
- **LLM Structuring:** Instructor (forces the Gemini LLM to return validated JSON matching specific Pydantic schemas).

### 🤖 Hardware Integration
- **Target Device:** Raspberry Pi (receives UDP payloads on IP `10.35.41.165` to drive physical servos).
- **Physical Control:** `pigpio` (Raspberry Pi hardware-timed PWM library for precise, jitter-free servo movement).

### 🧰 Other Tools / Libraries
- **Pydantic:** Data validation and schemas for the FastAPI endpoints and the LLM response definitions.
- **Blender:** Python scripting (`bpy`) is used for external kinesthetic tracking, capturing 3D armature coordinates and broadcasting them over low-latency UDP streams.

---

## 🚀 Project Setup Instructions

This project is divided into multiple coordinated systems. Follow these instructions to get everything up and running across your devices.

### 1. Clone the repository
```bash
git clone https://github.com/Obsidian-SMP/thin_digi.git
cd Digi-Twin
```

### 2. Backend Setup (FastAPI & AI)
Ensure you have Python 3.10+ installed and run these commands from the `Digi-Twin` folder.
```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```
Create a `.env` file in the `backend/` directory and add your Gemini API Key for the NLP agent instructions:
```env
GEMINI_API_KEY=your_google_gemini_api_key
```
Start the server (by default it will start on port 8000):
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup (React Dashboard)
Open a new terminal, navigate to the `Digi-Twin` folder, and run:
```bash
cd frontend
npm install
npm run dev
```

### 4. Hardware Setup (Raspberry Pi)
From your Raspberry Pi terminal:
1. Ensure `pigpio` and its Python bindings are installed:
   ```bash
   sudo apt-get update
   sudo apt-get install pigpio python3-pigpio
   ```
2. Copy `twink3.0.py` and any associated calibration JSON files into your working directory on the Pi.
3. Launch the `pigpiod` daemon (required for hardware PWM timing):
   ```bash
   sudo pigpiod
   ```
4. Run the local robot controller script:
   ```bash
   python3 twink3.0.py
   ```

### 5. Blender Setup (Optional Kinesthetic Tracking)
If mapping and injecting 3D tracker info directly from Blender:
1. Open your `.blend` file containing your Armature/model.
2. Load `blender.py` into the Scripting workspace.
3. Update `RPI_IP` and `DASHBOARD_IP` at the top of the script to match the respective IP addresses on your local network.
4. Click "Run Script" within Blender to begin broadcasting live UDP coordinate frames to the Pi and Dashboard.

<br>
<p align="center">Made with ❤️ for HackToFuture 4.0</p>
