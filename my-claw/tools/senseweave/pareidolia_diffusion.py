"""Pareidolia + Diffusion — PIL sketch as starting point, DreamShaper paints it.

Flow:
1. scene_composer generates SceneSpec
2. pareidolia renders PIL sketch (geometric characters + weather)
3. diffusion_art refines it into a painting via img2img
4. Falls back to PIL sketch if GPU is busy or OOM

Mutes audio during GPU model swap to prevent pops.
"""
import json, os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scene_composer import compose_scene, render_composed_scene

GALLERY_DIR = "/home/user/cypherclaw/gallery/renders/"


def _mute():
    subprocess.run(["amixer", "-D", "hw:USB", "sset", "Line 01 Mute", "on"],
                   capture_output=True, timeout=2)
    subprocess.run(["amixer", "-D", "hw:USB", "sset", "Line 02 Mute", "on"],
                   capture_output=True, timeout=2)

def _unmute():
    subprocess.run(["amixer", "-D", "hw:USB", "sset", "Line 01 Mute", "off"],
                   capture_output=True, timeout=2)
    subprocess.run(["amixer", "-D", "hw:USB", "sset", "Line 02 Mute", "off"],
                   capture_output=True, timeout=2)


def scene_to_prompt(spec) -> str:
    """Convert SceneSpec to a diffusion prompt."""
    chars = getattr(spec, "characters", [])
    char_names = [c.get("name", "").replace("_", " ") for c in chars]
    weather = getattr(spec, "weather", {})
    mood = getattr(spec, "mood_tag", "calm")
    hour = getattr(spec, "hour", 12)

    if hour < 6: tod = "deep night, moonlit"
    elif hour < 9: tod = "early morning, golden dawn"
    elif hour < 12: tod = "morning, soft daylight"
    elif hour < 17: tod = "afternoon, warm sunlight"
    elif hour < 20: tod = "evening, golden hour"
    else: tod = "night, blue-purple darkness"

    weather_words = []
    if weather.get("rain", 0) > 0.1: weather_words.append("rainy")
    if weather.get("snow", 0) > 0.1: weather_words.append("snowy")
    if weather.get("fog"): weather_words.append("foggy misty")
    if weather.get("clouds", 0) >= 3: weather_words.append("overcast")
    weather_str = ", ".join(weather_words) if weather_words else "clear sky"

    char_desc = []
    for name in char_names[:3]:
        if "heart" in name: char_desc.append("a pulsing organic form")
        elif "eye" in name or "garden" in name: char_desc.append("a watchful presence among leaves")
        elif "window" in name: char_desc.append("light streaming through glass")
        elif "poet" in name: char_desc.append("a flowing figure")
        elif "claude" in name or "codex" in name or "gemini" in name: char_desc.append("a luminous spirit")
        elif "basalt" in name: char_desc.append("a solid ancient stone figure")
        elif "pebble" in name: char_desc.append("a small bright curious stone")
        else: char_desc.append("an abstract being")

    chars_str = ", ".join(char_desc) if char_desc else "abstract forms"

    return (
        f"oil painting, {tod}, {weather_str}, "
        f"{chars_str}, "
        f"pareidolia, faces hidden in nature, "
        f"{mood} mood, painterly brush strokes, textured canvas, "
        f"atmospheric, muted earth tones"
    )


def generate_art_piece(use_diffusion=True) -> str:
    """Full pipeline: compose -> PIL sketch -> diffusion painting -> save."""
    spec = compose_scene()
    pil_sketch = render_composed_scene(spec)

    image = pil_sketch  # fallback
    method = "pareidolia"

    if use_diffusion:
        try:
            prompt = scene_to_prompt(spec)
            _mute()
            try:
                from diffusion_art import generate
                image = generate(prompt, init_image=None, steps=20)
                method = "diffusion"
            except Exception as e:
                print(f"Diffusion failed ({e}), using PIL sketch", flush=True)
                image = pil_sketch
                method = "pareidolia"
            finally:
                _unmute()
        except Exception:
            _unmute()

    # Save
    ts = time.strftime("%Y%m%d_%H%M%S")
    title = getattr(spec, "title", f"piece_{ts}")
    safe_title = "".join(c if c.isalnum() or c in "_ -" else "_" for c in title)
    png_path = os.path.join(GALLERY_DIR, f"art_{ts}_{safe_title}.png")
    json_path = png_path.replace(".png", ".json")

    os.makedirs(GALLERY_DIR, exist_ok=True)
    image.save(png_path)

    meta = {
        "title": title,
        "mood_tag": getattr(spec, "mood_tag", ""),
        "hour": getattr(spec, "hour", 0),
        "palette_name": getattr(spec, "palette_name", ""),
        "characters": [c.get("name") for c in getattr(spec, "characters", [])],
        "elements": [e.get("type") for e in getattr(spec, "elements", [])],
        "weather": getattr(spec, "weather", {}),
        "method": method,
        "timestamp": ts,
        "visibility": "public",
        "generated_at": time.time(),
    }
    with open(json_path, "w") as f:
        json.dump(meta, f, indent=2)

    # State for face/gallery
    try:
        state = {"title": title, "generated_at": time.time(), "path": png_path, "method": method}
        with open("/tmp/art_engine_state.json.tmp", "w") as f:
            json.dump(state, f)
        os.replace("/tmp/art_engine_state.json.tmp", "/tmp/art_engine_state.json")
    except Exception:
        pass

    print(f"Art [{method}]: {title} -> {png_path}", flush=True)
    return png_path


def generate_sticker(width=456, height=254) -> str:
    """Generate a sticker-sized Pareidolia scene."""
    from PIL import Image
    spec = compose_scene()
    full = render_composed_scene(spec)
    sticker = full.resize((width, height), Image.LANCZOS)

    ts = time.strftime("%Y%m%d_%H%M%S")
    title = getattr(spec, "title", "sticker")
    safe_title = "".join(c if c.isalnum() or c in "_ -" else "_" for c in title)
    path = f"/home/user/cypherclaw/gallery/stickers/pareidolia_{ts}_{safe_title}.png"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sticker.save(path)
    print(f"Sticker: {path}", flush=True)
    return path


def run_art_cycle(interval=1800, use_diffusion=True):
    """Daemon loop: generate art + sticker every interval seconds."""
    print(f"Pareidolia+Diffusion art cycle started (interval={interval}s)", flush=True)
    while True:
        try:
            # Check if inner life requests art
            try:
                req = json.loads(open("/tmp/art_request.json").read())
                if req.get("requested_at", 0) > time.time() - 120:
                    print("Art requested by inner life", flush=True)
                    os.remove("/tmp/art_request.json")
            except Exception:
                pass

            generate_art_piece(use_diffusion=use_diffusion)

            # Also generate a sticker every other cycle
            if int(time.time() / interval) % 2 == 0:
                generate_sticker()

        except Exception as e:
            print(f"Art cycle error: {e}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-diffusion", action="store_true")
    parser.add_argument("--interval", type=int, default=1800)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if args.once:
        generate_art_piece(use_diffusion=not args.no_diffusion)
    else:
        run_art_cycle(interval=args.interval, use_diffusion=not args.no_diffusion)
