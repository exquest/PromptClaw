"""Observer — PIL fast analysis every 15s, gemma3 vision every 2 min.

Fast loop: brightness, motion, color via PIL (cheap).
Slow loop: scene understanding via gemma3:4b vision (loads on demand).
"""
import base64, json, math, os, subprocess, time, urllib.request
from PIL import Image

FRAME = "/tmp/observer_frame.jpg"
STATE = "/tmp/observer_state.json"
OLLAMA_URL = "http://localhost:11434/api/chat"
FAST_INTERVAL = 15
VISION_INTERVAL = 120  # gemma3 every 2 min

prev_pixels = None
last_vision = 0
last_description = ""

PROMPT = (
    "You are CypherClaw, an AI art installation looking at your room. "
    "Describe what you see in under 30 words. "
    "Note people, lighting, your face monitor, anything interesting."
)

def capture():
    subprocess.run(
        ["ffmpeg", "-y", "-f", "v4l2", "-video_size", "640x480",
         "-i", "/dev/video2", "-frames:v", "1", "-update", "1", FRAME],
        capture_output=True, timeout=10)
    return os.path.exists(FRAME) and os.path.getsize(FRAME) > 1000

def fast_analyze(frame_path):
    global prev_pixels
    img = Image.open(frame_path)
    small = img.resize((80, 60))
    gray = small.convert("L")
    pixels = list(gray.getdata())
    brightness = sum(pixels) / (len(pixels) * 255.0)
    rgb = small.convert("RGB")
    rgb_data = list(rgb.getdata())
    r_avg = sum(p[0] for p in rgb_data) / len(rgb_data)
    g_avg = sum(p[1] for p in rgb_data) / len(rgb_data)
    b_avg = sum(p[2] for p in rgb_data) / len(rgb_data)
    if max(r_avg, g_avg, b_avg) < 30: dominant = "dark"
    elif r_avg > g_avg and r_avg > b_avg: dominant = "warm"
    elif b_avg > r_avg and b_avg > g_avg: dominant = "cool"
    elif g_avg > r_avg: dominant = "natural"
    else: dominant = "neutral"
    motion = False
    motion_amount = 0.0
    if prev_pixels and len(prev_pixels) == len(pixels):
        diff = sum(abs(a - b) for a, b in zip(pixels, prev_pixels))
        motion_amount = diff / (len(pixels) * 255.0)
        motion = motion_amount > 0.02
    someone_here = brightness > 0.08 and (motion or brightness > 0.2)
    if brightness < 0.05: lighting = "dark"
    elif brightness < 0.15: lighting = "dim"
    elif brightness < 0.4: lighting = "moderate"
    else: lighting = "bright"
    prev_pixels = pixels
    return {"brightness": brightness, "lighting": lighting, "dominant_color": dominant,
            "motion": motion, "motion_amount": motion_amount, "someone_here": someone_here,
            "rgb_avg": [int(r_avg), int(g_avg), int(b_avg)]}

def vision_analyze(frame_path):
    with open(frame_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    payload = json.dumps({
        "model": "gemma3:4b", "messages": [{"role": "user", "content": PROMPT, "images": [img_b64]}],
        "stream": False, "options": {"num_predict": 60},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=90)
    return json.loads(resp.read()).get("message", {}).get("content", "").strip()

def write_state(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f: json.dump(state, f)
    os.replace(tmp, STATE)

print("Observer (PIL + gemma3 vision) started", flush=True)
while True:
    try:
        if capture():
            result = fast_analyze(FRAME)
            now = time.time()
            # Vision analysis on slower cadence
            if now - last_vision > VISION_INTERVAL:
                try:
                    last_description = vision_analyze(FRAME)
                    last_vision = now
                    print(f"Vision: {last_description[:60]}", flush=True)
                except Exception as e:
                    last_description = f"(vision unavailable: {str(e)[:40]})"
            state = {"timestamp": now, "ok": True, "frame_path": FRAME,
                     "description": last_description, **result}
        else:
            state = {"timestamp": time.time(), "ok": False, "error": "capture_failed"}
        write_state(state)
    except Exception as e:
        write_state({"timestamp": time.time(), "ok": False, "error": str(e)[:80]})
    time.sleep(FAST_INTERVAL)
