#!/usr/bin/env python3
"""GlyphWeave Art Engine — generates art via LLM + Canvas DSL, renders to gallery.

Minimal art generation cycle:
1. Pick a theme/mood (round-robin from theme list)
2. Call local LLM (Ollama) to generate GlyphWeave Canvas DSL code
3. Execute the DSL in a subprocess sandbox
4. Render output to text + PNG image
5. Save to gallery/renders/ with metadata sidecar
6. Push to framebuffer for physical monitor
7. Gallery display auto-picks it up via ArtWatcher
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Ensure tools/ is in path
TOOLS_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOLS_DIR))

from glyphweave.dsl import (  # noqa: E402
    PALETTE_CUTE,
    PALETTE_DRAGON,
    PALETTE_NIGHT,
    PALETTE_SPACE,
    PALETTE_UI,
    PALETTE_WATER,
)

THEMES = [
    ("ocean depths", "water", "A mysterious underwater scene with sea creatures"),
    ("starfield", "space", "A cosmic scene with stars, planets, and nebulae"),
    ("cozy garden", "cute", "A peaceful garden with small animals and flowers"),
    ("dragon's lair", "dragon", "A dramatic scene with a dragon and treasure"),
    ("moonlit forest", "night", "A quiet forest bathed in moonlight"),
    ("cyber city", "ui", "A futuristic cityscape with neon lights"),
    ("sunrise mountain", "dragon", "Dawn breaking over mountain peaks"),
    ("underwater cave", "water", "A bioluminescent cave deep underwater"),
    ("space station", "space", "Life aboard an orbiting space station"),
    ("autumn path", "cute", "A winding path through autumn leaves"),
    ("storm at sea", "water", "A ship battling waves in a storm"),
    ("crystal cavern", "night", "A cavern filled with glowing crystals"),
]

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
GALLERY_DIR = Path(os.environ.get("GALLERY_DIR", "/home/user/cypherclaw/gallery/renders"))

# Models to rotate through (round-robin calibration)
MODELS = ["qwen3.5:9b", "qwen3.5:4b", "gemma3:4b", "llama3.2:3b"]

GENERATION_PROMPT = """You are a GlyphWeave artist. Generate ASCII+emoji hybrid art using Python code.

You have access to:
- Canvas(width, height) -- creates a grid
- canvas.place(x, y, char) -- place single ASCII char
- canvas.place_emoji(x, y, emoji) -- place an emoji (takes 2 cells wide)
- canvas.place_text(x, y, text) -- place a string
- canvas.fill_row(y, char) -- fill entire row
- canvas.fill_region(x, y, w, h, char) -- fill rectangle
- canvas.to_string() -- returns the final string

Available emoji palettes:
- WATER: {water}
- SPACE: {space}
- CUTE: {cute}
- DRAGON: {dragon}
- NIGHT: {night}
- UI: {ui}

RULES:
- Canvas size: 24 wide, 12 tall (small grids work best)
- Mix ASCII characters and emoji creatively
- Use the {palette_name} palette primarily
- Emojis take 2 cells of width -- account for this
- Output ONLY valid Python code, no explanation
- The code must end with: print(canvas.to_string())
- Be creative and expressive!

THEME: {theme}
DESCRIPTION: {description}

Generate the Python code now:"""


def _get_cycle_state():
    """Track which model/theme to use next."""
    state_path = GALLERY_DIR / ".art_engine_state.json"
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except Exception:
            pass
    return {"cycle": 0, "model_index": 0, "theme_index": 0}


def _save_cycle_state(state):
    state_path = GALLERY_DIR / ".art_engine_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))


def call_ollama(prompt, model="qwen3.5:9b"):
    """Call Ollama to generate art code."""
    resp = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.8, "num_predict": 1024},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def extract_python(text):
    """Extract Python code from LLM response."""
    if "```python" in text:
        code = text.split("```python")[1].split("```")[0]
    elif "```" in text:
        code = text.split("```")[1].split("```")[0]
    else:
        code = text

    lines = []
    for line in code.strip().split("\n"):
        if line.strip().startswith("from glyphweave") or line.strip().startswith("import glyphweave"):
            continue
        lines.append(line)
    return "\n".join(lines)


def execute_art_code(code):
    """Execute GlyphWeave code in a subprocess sandbox. Returns rendered text or None."""
    full_code = (
        f'import sys\n'
        f'sys.path.insert(0, "{TOOLS_DIR}")\n'
        f'from glyphweave.dsl import Canvas, Animation, Motif\n'
        f'from glyphweave.dsl import PALETTE_WATER, PALETTE_SPACE, PALETTE_CUTE, PALETTE_DRAGON, PALETTE_NIGHT, PALETTE_UI\n'
        f'Canvas.render = Canvas.to_string\n'
        f'\n{code}'
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", full_code],
            capture_output=True, text=True, timeout=10,
            cwd=str(TOOLS_DIR),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            print(f"[art_engine] Code execution failed: {result.stderr[:300]}", file=sys.stderr)
            return None
    except subprocess.TimeoutExpired:
        print("[art_engine] Code execution timed out", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[art_engine] Execution error: {e}", file=sys.stderr)
        return None


def render_to_image(text_art, output_path):
    """Render text art to PNG image using PIL."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        lines = text_art.split("\n")
        max_width = max(len(line) for line in lines) if lines else 20
        char_w, char_h = 14, 24
        padding = 40

        img_w = max_width * char_w + padding * 2
        img_h = len(lines) * char_h + padding * 2

        img = Image.new("RGB", (img_w, img_h), (15, 15, 25))
        draw = ImageDraw.Draw(img)

        font = None
        for font_path in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]:
            if os.path.exists(font_path):
                try:
                    font = ImageFont.truetype(font_path, 18)
                    break
                except Exception:
                    continue
        if font is None:
            font = ImageFont.load_default()

        y = padding
        for line in lines:
            draw.text((padding, y), line, fill=(220, 220, 230), font=font)
            y += char_h

        img.save(str(output_path), "PNG")
        return True
    except Exception as e:
        print(f"[art_engine] Image render failed: {e}", file=sys.stderr)
        return False


def render_to_framebuffer(image_path):
    """Push image to /dev/fb0 for physical monitor display."""
    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from gallery.fb_renderer import FramebufferRenderer
        fb = FramebufferRenderer()
        if fb.available:
            fb.render_image(str(image_path))
            return True
        return False
    except Exception as e:
        print(f"[art_engine] Framebuffer render failed: {e}", file=sys.stderr)
        return False


def generate_art(model=None, theme=None):
    """Generate one piece of GlyphWeave art. Returns result dict."""
    state = _get_cycle_state()
    cycle = state["cycle"]

    if model is None:
        model = MODELS[state["model_index"] % len(MODELS)]
        state["model_index"] += 1

    if theme is None:
        theme_data = THEMES[state["theme_index"] % len(THEMES)]
        state["theme_index"] += 1
    else:
        theme_data = next((t for t in THEMES if t[0] == theme), THEMES[0])

    theme_name, palette_name, description = theme_data

    state["cycle"] = cycle + 1
    _save_cycle_state(state)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    art_id = f"art_{timestamp}_{hashlib.md5(f'{cycle}{model}{theme_name}'.encode()).hexdigest()[:6]}"

    result = {
        "success": False,
        "art_id": art_id,
        "cycle": cycle,
        "model": model,
        "theme": theme_name,
        "palette": palette_name,
        "description": description,
        "text_art": None,
        "image_path": None,
        "error": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    prompt = GENERATION_PROMPT.format(
        water=PALETTE_WATER, space=PALETTE_SPACE, cute=PALETTE_CUTE,
        dragon=PALETTE_DRAGON, night=PALETTE_NIGHT, ui=PALETTE_UI,
        palette_name=palette_name, theme=theme_name, description=description,
    )

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            print(f"[art_engine] Generating with {model}, theme={theme_name}, attempt {attempt+1}/{max_attempts}")
            raw = call_ollama(prompt, model=model)
            code = extract_python(raw)

            if not code.strip():
                print(f"[art_engine] Empty code from {model}, retrying...")
                continue

            text_art = execute_art_code(code)
            if text_art and any(line.strip() for line in text_art.splitlines()):
                result["text_art"] = text_art
                result["success"] = True

                GALLERY_DIR.mkdir(parents=True, exist_ok=True)
                txt_path = GALLERY_DIR / f"{art_id}.txt"
                txt_path.write_text(text_art)

                png_path = GALLERY_DIR / f"{art_id}.png"
                if render_to_image(text_art, png_path):
                    result["image_path"] = str(png_path)

                sidecar = {
                    "art_id": art_id,
                    "cycle": cycle,
                    "model": model,
                    "theme": theme_name,
                    "palette": palette_name,
                    "description": description,
                    "attempt": attempt + 1,
                    "generated_at": result["generated_at"],
                }
                (GALLERY_DIR / f"{art_id}.json").write_text(json.dumps(sidecar, indent=2))

                if result["image_path"]:
                    render_to_framebuffer(Path(result["image_path"]))

                print(f"[art_engine] Success: {art_id} ({model}, {theme_name})")
                break
            else:
                print(f"[art_engine] Bad output from {model}, retrying...")

        except Exception as e:
            result["error"] = str(e)
            print(f"[art_engine] Attempt {attempt+1} failed: {e}", file=sys.stderr)

    return result


def run_cycle():
    """Run one art generation cycle. Called by scheduler."""
    print(f"[art_engine] Starting art cycle at {datetime.now()}")
    result = generate_art()
    if result["success"]:
        print(f"[art_engine] Cycle complete: {result['art_id']} -- {result['theme']} by {result['model']}")
    else:
        print(f"[art_engine] Cycle failed: {result.get('error', 'unknown')}")
    return result


if __name__ == "__main__":
    result = run_cycle()
    if result["success"]:
        print(f"\nGenerated: {result['art_id']}")
        print(f"Theme: {result['theme']} | Model: {result['model']}")
        print(f"Saved to: {result.get('image_path', 'text only')}")
        if result["text_art"]:
            print(f"\n{result['text_art']}")
    else:
        print(f"\nFailed: {result.get('error', 'unknown')}")
        sys.exit(1)
