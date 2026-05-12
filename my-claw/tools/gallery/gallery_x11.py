#!/usr/bin/env python3
"""Gallery display for X11 — runs fullscreen on the Sceptre 4K monitor."""
import json
import os
import signal
import sys
import time
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 3840, 2160
ART_DIR = Path("/home/user/cypherclaw/gallery/renders/")
DURATION = 15  # seconds per piece


def gallery_window_position(display: str | None = None) -> str:
    """Choose a sane SDL window origin for combined or split X screens."""
    override = os.environ.get("GALLERY_WINDOW_POS")
    if override:
        return override

    target_display = display if display is not None else os.environ.get("DISPLAY", "")
    if target_display.endswith(".1"):
        return "0,0"
    return "1280,0"


def load_playlist() -> list[Path]:
    """Load all public art PNGs."""
    pieces = []
    if not ART_DIR.exists():
        return pieces
    for p in ART_DIR.iterdir():
        if p.suffix.lower() != ".png":
            continue
        sidecar = p.with_suffix(".json")
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text())
                if meta.get("visibility") == "public":
                    pieces.append(p)
            except (json.JSONDecodeError, OSError):
                continue
    pieces.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return pieces


def render_art(path: Path, screen_size: tuple) -> pygame.Surface:
    """Load and scale art to fill screen."""
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        img = Image.new("RGB", screen_size, (15, 20, 40))

    # Scale to fit
    sw, sh = screen_size
    iw, ih = img.size
    scale = min(sw / iw, sh / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)

    canvas = Image.new("RGB", screen_size, (0, 0, 0))
    canvas.paste(img, ((sw - nw) // 2, (sh - nh) // 2))

    raw = canvas.tobytes("raw", "RGB")
    return pygame.image.fromstring(raw, screen_size, "RGB")



def render_overlay(surface: pygame.Surface) -> None:
    """Draw live status overlay on the gallery — characters, key, mood."""
    import json
    
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        font = pygame.font.Font(font_path, 36)
        font_sm = pygame.font.Font(font_path, 28)
        font_xs = pygame.font.Font(font_path, 22)
    except Exception:
        font = pygame.font.SysFont(None, 36)
        font_sm = font
        font_xs = font
    
    y = HEIGHT - 200
    
    # Music state
    try:
        cs = json.loads(open("/tmp/composer_state.json").read())
        key_text = f"{cs.get('key', '?')} major — {cs.get('movement', '')}"
        surf = font.render(key_text, True, (180, 190, 220, 180))
        surface.blit(surf, (40, y))
        y += 45
    except Exception:
        pass

    # Active characters — draw their Pareidolia visuals
    try:
        ac = json.loads(open("/tmp/active_characters.json").read())
        chars = ac.get("active_characters", [])
        if chars:
            # Draw small character icons along the bottom
            import sys as _sys
            _sys.path.insert(0, "/home/user/cypherclaw/tools/senseweave")
            from character_visuals import (
                draw_window, draw_heartbeat, draw_skin, draw_garden_eye,
                draw_poet, draw_printer, draw_speakers, draw_gallery_face,
                draw_face_eye, draw_porch_eye, draw_archivist,
                draw_voice_claude, draw_voice_codex, draw_voice_gemini,
                draw_perform_ve, draw_pet,
            )
            from PIL import Image as _Img, ImageDraw as _IDraw
            
            _char_draw_map = {
                "sense_window": draw_window, "sense_heartbeat": draw_heartbeat,
                "sense_skin": draw_skin, "sense_garden_eye": draw_garden_eye,
                "sense_face_eye": draw_face_eye, "sense_porch_eye": draw_porch_eye,
                "voice_poet": draw_poet, "voice_archivist": draw_archivist,
                "voice_claude": draw_voice_claude, "voice_codex": draw_voice_codex,
                "voice_gemini": draw_voice_gemini, "output_printer": draw_printer,
                "output_speakers": draw_speakers, "output_gallery": draw_gallery_face,
                "output_perform_ve": draw_perform_ve,
                "basalt": lambda d, x, y: draw_pet(d, x, y, "cypherclaw", "Adult"),
                "pebble": lambda d, x, y: draw_pet(d, x, y, "claude", "Baby"),
            }
            
            # Render each character as a small icon
            icon_size = 120
            spacing = 160
            start_x = 40
            for i, cid in enumerate(chars[:6]):
                draw_fn = _char_draw_map.get(cid)
                if draw_fn:
                    # Draw character on a small PIL image, convert to pygame
                    icon = _Img.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
                    icon_draw = _IDraw.Draw(icon)
                    try:
                        draw_fn(icon_draw, icon_size // 2, icon_size // 2)
                    except Exception:
                        pass
                    # Convert to pygame surface
                    raw = icon.tobytes("raw", "RGBA")
                    icon_surf = pygame.image.fromstring(raw, (icon_size, icon_size), "RGBA")
                    surface.blit(icon_surf, (start_x + i * spacing, y - 10))
                
                # Name label below icon
                name = cid.replace("_", " ").replace("sense ", "").replace("voice ", "").replace("output ", "").replace("pet ", "")
                name_surf = font_xs.render(name, True, (140, 155, 185))
                surface.blit(name_surf, (start_x + i * spacing, y + icon_size))
            y += icon_size + 30
    except Exception:
        pass
    
    # Garden/outdoor state
    try:
        gs = json.loads(open("/tmp/garden_state.json").read())
        light = gs.get("light", "?")
        season = gs.get("season", "?")
        surf = font_xs.render(f"{season} · {light}", True, (130, 150, 170, 120))
        surface.blit(surf, (40, y))
    except Exception:
        pass


def init_pygame_display() -> None:
    """Initialize only the pygame modules the gallery display actually uses."""
    pygame.display.init()
    if not pygame.font.get_init():
        pygame.font.init()


def main():
    os.environ["SDL_VIDEO_WINDOW_POS"] = gallery_window_position()
    init_pygame_display()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)
    pygame.display.set_caption("CypherClaw Gallery")
    pygame.mouse.set_visible(False)

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    playlist = load_playlist()
    idx = 0
    last_switch = time.time()
    last_scan = time.time()
    current_surface = None

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        now = time.time()

        # Rescan every 60s
        if now - last_scan > 60:
            playlist = load_playlist()
            last_scan = now

        # Switch piece
        if now - last_switch > DURATION or current_surface is None:
            if playlist:
                current_surface = render_art(playlist[idx % len(playlist)], (WIDTH, HEIGHT))
                idx = (idx + 1) % len(playlist) if playlist else 0
            else:
                # No art — show waiting screen
                img = Image.new("RGB", (WIDTH, HEIGHT), (15, 20, 40))
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 80)
                except OSError:
                    font = ImageFont.load_default()
                draw.text((WIDTH // 2 - 400, HEIGHT // 2), "Composing...",
                          fill=(100, 110, 130), font=font)
                raw = img.tobytes("raw", "RGB")
                current_surface = pygame.image.fromstring(raw, (WIDTH, HEIGHT), "RGB")
            last_switch = now

        if current_surface:
            screen.blit(current_surface, (0, 0))
            render_overlay(screen)
        pygame.display.flip()
        pygame.time.wait(100)

    pygame.quit()


if __name__ == "__main__":
    main()
