"""Diffusion Art Generator — uses Stable Diffusion 1.5 + DreamShaper for AI art.

Takes a scene description from scene_composer and optionally a PIL sketch
from the Pareidolia renderer, then generates a painterly image via img2img.

Loads model on demand, generates, then fully unloads to free VRAM for Ollama.
"""
import gc
import json
import os
import sys
import time
from pathlib import Path

# Model ID — DreamShaper 8 for artistic/painterly output
MODEL_ID = "Lykon/dreamshaper-8"
GALLERY_DIR = Path("/home/user/cypherclaw/gallery/renders/")
NEGATIVE_PROMPT = (
    "photorealistic, photograph, sharp focus, hyperdetailed, CGI, 3D render, "
    "text, watermark, ugly, blurry, low quality, deformed"
)


def scene_to_prompt(scene_spec: dict) -> str:
    """Convert a SceneSpec dict into a diffusion prompt."""
    chars = scene_spec.get("characters", [])
    char_names = [c.get("name", "").replace("_", " ") for c in chars]
    weather = scene_spec.get("weather", {})
    mood = scene_spec.get("mood_tag", "calm")
    palette = scene_spec.get("palette_name", "day_calm")
    title = scene_spec.get("title", "")
    hour = scene_spec.get("hour", 12)

    # Time of day
    if hour < 6:
        tod = "deep night, moonlit"
    elif hour < 9:
        tod = "early morning, golden dawn light"
    elif hour < 12:
        tod = "morning, soft daylight"
    elif hour < 17:
        tod = "afternoon, warm sunlight"
    elif hour < 20:
        tod = "evening, golden hour, long shadows"
    else:
        tod = "night, blue-purple darkness, stars"

    # Weather
    weather_words = []
    if weather.get("rain", 0) > 0.1:
        weather_words.append("rainy")
    if weather.get("snow", 0) > 0.1:
        weather_words.append("snowy")
    if weather.get("fog", False):
        weather_words.append("foggy, misty")
    if weather.get("clouds", 0) >= 3:
        weather_words.append("overcast, grey sky")
    weather_str = ", ".join(weather_words) if weather_words else "clear sky"

    # Characters as abstract beings
    char_descriptions = []
    for name in char_names[:3]:
        if "heart" in name:
            char_descriptions.append("a pulsing organic form with rhythm")
        elif "eye" in name or "garden" in name:
            char_descriptions.append("a watchful presence among leaves")
        elif "window" in name:
            char_descriptions.append("light streaming through glass")
        elif "poet" in name:
            char_descriptions.append("a flowing figure writing in the air")
        elif "archivist" in name:
            char_descriptions.append("a geometric keeper of patterns")
        elif "claude" in name or "codex" in name or "gemini" in name:
            char_descriptions.append("a luminous digital spirit")
        elif "printer" in name:
            char_descriptions.append("marks appearing on paper")
        elif "speaker" in name:
            char_descriptions.append("waves of sound made visible")
        elif "basalt" in name:
            char_descriptions.append("a solid stone figure, ancient")
        elif "pebble" in name:
            char_descriptions.append("a small bright curious stone")
        elif "skin" in name:
            char_descriptions.append("a tactile surface sensing touch")
        else:
            char_descriptions.append("an abstract being")

    chars_str = ", ".join(char_descriptions) if char_descriptions else "abstract forms"

    prompt = (
        f"oil painting, {tod}, {weather_str}, "
        f"{chars_str}, "
        f"pareidolia, faces hidden in nature, "
        f"{mood} mood, painterly brush strokes, textured canvas, "
        f"atmospheric, Remedios Varo meets Studio Ghibli, "
        f"muted earth tones, moss green, deep blue, warm amber"
    )

    return prompt


def generate(prompt: str, init_image=None, strength: float = 0.7,
             steps: int = 20, guidance: float = 7.5,
             width: int = 512, height: int = 512) -> "Image":
    """Generate an image. Loads model, generates, fully unloads.

    If init_image is provided, uses img2img. Otherwise text2img.
    Returns a PIL Image.
    """
    import torch
    from diffusers import (
        StableDiffusionPipeline,
        StableDiffusionImg2ImgPipeline,
    )

    # Stop ALL Ollama models and wait for VRAM to free
    os.system("ollama stop qwen3.5:4b 2>/dev/null")
    os.system("ollama stop gemma3:4b 2>/dev/null")
    os.system("ollama stop chatmusician 2>/dev/null")
    os.system("ollama stop qwen3.5:9b 2>/dev/null")
    # Wait for Ollama to actually release VRAM
    import subprocess
    for _ in range(10):
        time.sleep(1)
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5)
            used_mb = int(r.stdout.strip())
            if used_mb < 1000:  # Less than 1GB used = Ollama released
                break
        except Exception:
            pass
    time.sleep(1)

    try:
        if init_image is not None:
            pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                MODEL_ID,
                torch_dtype=torch.float32,
                safety_checker=None,
            )
        else:
            pipe = StableDiffusionPipeline.from_pretrained(
                MODEL_ID,
                torch_dtype=torch.float32,
                safety_checker=None,
            )

        pipe.to("cuda")
        pipe.enable_attention_slicing()

        if init_image is not None:
            # Resize init image to target size
            init_image = init_image.convert("RGB").resize((width, height))
            result = pipe(
                prompt=prompt,
                image=init_image,
                strength=strength,
                guidance_scale=guidance,
                num_inference_steps=steps,
                negative_prompt=NEGATIVE_PROMPT,
            ).images[0]
        else:
            result = pipe(
                prompt=prompt,
                width=width,
                height=height,
                guidance_scale=guidance,
                num_inference_steps=steps,
                negative_prompt=NEGATIVE_PROMPT,
            ).images[0]

        return result

    finally:
        # FULLY unload to free VRAM for Ollama
        try:
            pipe.to("cpu")
        except Exception:
            pass
        try:
            del pipe
        except Exception:
            pass
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass


def generate_art_piece(gallery_dir: str = str(GALLERY_DIR)) -> str:
    """Full pipeline: compose scene -> render PIL sketch -> diffusion -> save.

    Returns path to the saved image.
    """
    sys.path.insert(0, "/home/user/cypherclaw/tools/senseweave")
    from scene_composer import compose_scene, render_composed_scene

    # 1. Compose scene
    spec = compose_scene()

    # 2. Render PIL sketch (Pareidolia)
    pil_sketch = render_composed_scene(spec)

    # 3. Convert scene to diffusion prompt
    prompt = scene_to_prompt(spec.__dict__ if hasattr(spec, '__dict__') else {})

    # 4. Generate via diffusion (text2img — more reliable than img2img on fp16)
    try:
        image = generate(prompt, init_image=None, strength=0.7, steps=20)
    except Exception as e:
        print(f"Diffusion failed ({e}), falling back to PIL sketch", flush=True)
        image = pil_sketch

    # 5. Save
    ts = time.strftime("%Y%m%d_%H%M%S")
    title = getattr(spec, 'title', '') if hasattr(spec, 'title') else f"piece_{ts}"
    safe_title = "".join(c if c.isalnum() or c in "_ -" else "_" for c in title)
    png_path = os.path.join(gallery_dir, f"art_{ts}_{safe_title}.png")
    json_path = png_path.replace(".png", ".json")

    os.makedirs(gallery_dir, exist_ok=True)
    image.save(png_path)

    meta = {
        "title": title,
        "prompt": prompt,
        "timestamp": ts,
        "method": "diffusion" if image != pil_sketch else "pareidolia",
        "visibility": "public",
        "generated_at": time.time(),
    }
    with open(json_path, "w") as f:
        json.dump(meta, f, indent=2)

    # Write state for face/gallery to pick up
    try:
        state = {"title": title, "generated_at": time.time(), "path": png_path}
        with open("/tmp/art_engine_state.json.tmp", "w") as f:
            json.dump(state, f)
        os.replace("/tmp/art_engine_state.json.tmp", "/tmp/art_engine_state.json")
    except Exception:
        pass

    print(f"Art: {title} -> {png_path}", flush=True)
    return png_path


if __name__ == "__main__":
    path = generate_art_piece()
    print(f"Generated: {path}")
