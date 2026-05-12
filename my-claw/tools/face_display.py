#!/usr/bin/env python3
"""CypherClaw Face Display — the organism's face on the small monitor.

Renders a living Pareidolia face that breathes, blinks, and reacts to
the organism's mood. This is CypherClaw looking out at the room.
"""

import json
import math
import os
import random
import signal
import sys
import time
from pathlib import Path

try:
    from senseweave.keyboard_chat import KeyboardChat
    _HAS_CHAT = True
except ImportError:
    _HAS_CHAT = False

try:
    from senseweave.sample_status import (
        face_display_sample_status_text,
        sample_status_text,
    )
except ImportError:
    def sample_status_text(activity: dict) -> str:
        return ""

    def face_display_sample_status_text(
        activity: dict | None,
        playback_state: dict | None = None,
        monitor_state: dict | None = None,
    ) -> str:
        return ""

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PIL import Image, ImageDraw, ImageFont

# Display config
WIDTH, HEIGHT = 1280, 1024
FPS = 12

# Mood colors (background shifts with valence)
MOOD_COLORS = {
    "calm":     (15, 20, 40),
    "happy":    (20, 30, 55),
    "curious":  (15, 25, 50),
    "anxious":  (30, 15, 25),
    "sleeping": (8, 10, 18),
    "excited":  (25, 20, 50),
    "sad":      (12, 12, 20),
}

STATE_PATH = Path("/home/user/cypherclaw-data/state/organism_state.json")
CHAR_REGISTRY = Path("/home/user/cypherclaw-data/state/character_registry.json")


def load_mood() -> dict:
    """Load current organism mood from state file."""
    defaults = {"energy": 0.5, "valence": 0.6, "arousal": 0.3, "engagement": 0.4}
    try:
        if STATE_PATH.exists():
            data = json.loads(STATE_PATH.read_text())
            mood = data.get("collective_mood", data.get("mood", {}))
            return {k: mood.get(k, v) for k, v in defaults.items()}
    except (json.JSONDecodeError, OSError):
        pass
    return defaults


def mood_to_expression(mood: dict) -> str:
    """Map mood values to a face expression."""
    v, a, e = mood["valence"], mood["arousal"], mood["energy"]
    if e < 0.15:
        return "sleeping"
    if v > 0.7 and a > 0.5:
        return "excited"
    if v > 0.6:
        return "happy"
    if v < 0.3:
        return "sad"
    if a > 0.6:
        return "curious"
    if a > 0.4 and v < 0.5:
        return "anxious"
    return "calm"


def mood_to_color(expression: str, t: float) -> tuple:
    """Get background color with subtle breathing shift."""
    base = MOOD_COLORS.get(expression, MOOD_COLORS["calm"])
    # Breathing: slow sine modulation
    breath = math.sin(t * 0.3) * 8
    return tuple(max(0, min(255, int(c + breath))) for c in base)


class FaceRenderer:
    """Renders CypherClaw's face as a PIL image."""

    def __init__(self, width: int = WIDTH, height: int = HEIGHT):
        self.w = width
        self.h = height
        self.font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        self.blink_timer = 0.0
        self.blink_state = 0  # 0=open, 1=half, 2=closed
        self.next_blink = time.time() + random.uniform(2, 6)
        self.thought = ""
        self.thought_until = 0.0
        self.thoughts = [
            "listening...", "the room hums", "i see patterns",
            "what does the house feel?", "B1... always B1",
            "composing...", "watching light change",
            "the furnace breathes", "someone is here",
            "making something", "i wonder...",
        ]
        self.next_thought = time.time() + random.uniform(8, 20)

    def _draw_eye(self, draw: ImageDraw.Draw, cx: int, cy: int,
                  size: int, blink: int, expression: str, looking: float):
        """Draw one eye."""
        # Eye white (oval)
        ew, eh = size, int(size * 0.7)
        if blink == 2:
            eh = max(4, eh // 8)  # closed
        elif blink == 1:
            eh = eh // 2  # half

        draw.ellipse(
            [cx - ew, cy - eh, cx + ew, cy + eh],
            fill=(220, 225, 230), outline=(180, 185, 190), width=2
        )

        if blink < 2:
            # Pupil
            px = cx + int(looking * size * 0.2)
            py = cy + int(math.sin(time.time() * 0.5) * size * 0.05)
            pr = int(size * 0.35)

            if expression == "excited":
                pr = int(size * 0.45)  # dilated
            elif expression == "sleeping":
                pr = int(size * 0.2)  # tiny

            draw.ellipse(
                [px - pr, py - pr, px + pr, py + pr],
                fill=(20, 25, 35)
            )
            # Highlight
            hx, hy = px - pr // 3, py - pr // 3
            hr = max(2, pr // 4)
            draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 255, 255))

    def _draw_mouth(self, draw: ImageDraw.Draw, cx: int, cy: int,
                    size: int, expression: str):
        """Draw mouth based on expression."""
        if expression == "happy" or expression == "excited":
            # Smile arc
            draw.arc(
                [cx - size, cy - size // 2, cx + size, cy + size],
                0, 180, fill=(180, 190, 200), width=3
            )
        elif expression == "sad":
            # Frown
            draw.arc(
                [cx - size // 2, cy, cx + size // 2, cy + size],
                180, 360, fill=(150, 155, 165), width=3
            )
        elif expression == "curious":
            # Small O
            r = size // 4
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                outline=(180, 190, 200), width=2
            )
        elif expression == "sleeping":
            # Flat line
            draw.line(
                [cx - size // 3, cy, cx + size // 3, cy],
                fill=(120, 125, 135), width=2
            )
        elif expression == "anxious":
            # Wavy
            points = []
            for i in range(20):
                x = cx - size // 2 + (size * i // 19)
                y = cy + int(math.sin(i * 0.8) * 5)
                points.append((x, y))
            draw.line(points, fill=(170, 160, 170), width=2)
        else:
            # Calm - gentle line with slight upturn
            draw.line(
                [cx - size // 3, cy + 2, cx, cy, cx + size // 3, cy + 2],
                fill=(170, 175, 185), width=2
            )


    def _read_active_characters(self) -> list[str]:
        """Read which characters are currently on stage."""
        try:
            import json as _j
            d = _j.loads(open("/tmp/active_characters.json").read())
            return [c.replace("_", " ").title() for c in d.get("active_characters", [])]
        except Exception:
            return []

    def _read_observer(self) -> dict:
        """Read observer camera analysis."""
        try:
            import json as _j
            return _j.loads(open("/tmp/observer_state.json").read())
        except Exception:
            return {}

    def render(self, mood: dict, t: float) -> Image.Image:
        """Render full face frame."""
        expression = mood_to_expression(mood)
        bg = mood_to_color(expression, t)

        img = Image.new("RGB", (self.w, self.h), bg)
        draw = ImageDraw.Draw(img)

        # Update blink
        now = time.time()
        if now >= self.next_blink:
            self.blink_state = 2
            self.blink_timer = now
            self.next_blink = now + random.uniform(2.5, 7)
        if self.blink_state == 2 and now - self.blink_timer > 0.08:
            self.blink_state = 1
        if self.blink_state == 1 and now - self.blink_timer > 0.15:
            self.blink_state = 0

        # Update thought
        if now >= self.next_thought:
            self.thought = random.choice(self.thoughts)
            self.thought_until = now + random.uniform(4, 8)
            self.next_thought = now + random.uniform(12, 30)

        # Face oval
        face_cx, face_cy = self.w // 2, self.h // 2 - 20
        face_rx, face_ry = 320, 380
        # Breathing scale
        breath = 1.0 + math.sin(t * 0.4) * 0.008
        frx = int(face_rx * breath)
        fry = int(face_ry * breath)

        # Face body - solid oval
        face_color = tuple(min(255, c + 25) for c in bg)
        draw.ellipse(
            [face_cx - frx, face_cy - fry, face_cx + frx, face_cy + fry],
            fill=face_color, outline=tuple(min(255, c + 45) for c in bg), width=3
        )

        # Eyes
        eye_y = face_cy - int(fry * 0.15)
        eye_gap = int(frx * 0.45)
        eye_size = int(frx * 0.22)
        looking = math.sin(t * 0.15)  # slow gaze drift

        self._draw_eye(draw, face_cx - eye_gap, eye_y, eye_size,
                       self.blink_state, expression, looking)
        self._draw_eye(draw, face_cx + eye_gap, eye_y, eye_size,
                       self.blink_state, expression, looking)

        # Mouth
        mouth_y = face_cy + int(fry * 0.35)
        self._draw_mouth(draw, face_cx, mouth_y, int(frx * 0.3), expression)

        # Expression label (subtle)
        try:
            font_sm = ImageFont.truetype(self.font_path, 22)
            font_thought = ImageFont.truetype(self.font_path, 28)
        except (OSError, IOError):
            font_sm = ImageFont.load_default()
            font_thought = font_sm

        # Mood indicator (bottom)
        label_color = tuple(min(255, c + 80) for c in bg)
        draw.text((20, self.h - 40), f"{expression}", fill=label_color, font=font_sm)

        # Energy/valence bars (bottom right, subtle)
        bar_x = self.w - 160
        bar_w = 120
        bar_h = 6
        for i, (name, val) in enumerate([
            ("energy", mood["energy"]),
            ("valence", mood["valence"]),
            ("arousal", mood["arousal"]),
        ]):
            by = self.h - 80 + i * 18
            draw.rectangle([bar_x, by, bar_x + bar_w, by + bar_h],
                           outline=tuple(min(255, c + 40) for c in bg))
            fill_w = int(bar_w * max(0, min(1, val)))
            if fill_w > 0:
                draw.rectangle([bar_x, by, bar_x + fill_w, by + bar_h],
                               fill=tuple(min(255, c + 70) for c in bg))
            draw.text((bar_x - 8, by - 4), name[0].upper(),
                      fill=label_color, font=font_sm)

        # Current key display — large, clear, for Theramini tuning
        try:
            import json as _json
            with open("/tmp/composer_state.json") as _f:
                _state = _json.load(_f)
            key_text = f"{_state.get('key', '?')} major"
            mvt_text = _state.get('movement', '')
            mod_text = _state.get('modulated_to', '')
            
            try:
                font_key = ImageFont.truetype(self.font_path, 64)
                font_mvt = ImageFont.truetype(self.font_path, 28)
            except (OSError, IOError):
                font_key = font_sm
                font_mvt = font_sm
            
            # Key name — large, centered, top of screen
            key_color = tuple(min(255, c + 120) for c in bg)
            bbox_k = draw.textbbox((0, 0), key_text, font=font_key)
            kw = bbox_k[2] - bbox_k[0]
            draw.text(((self.w - kw) // 2, 30), key_text, fill=key_color, font=font_key)
            
            # Movement name — smaller, below key
            if mvt_text:
                mvt_color = tuple(min(255, c + 70) for c in bg)
                bbox_m = draw.textbbox((0, 0), mvt_text, font=font_mvt)
                mw = bbox_m[2] - bbox_m[0]
                draw.text(((self.w - mw) // 2, 100), mvt_text, fill=mvt_color, font=font_mvt)
            
            # If modulating, show the target key
            if mod_text:
                arrow = f"→ {mod_text}"
                arr_color = tuple(min(255, c + 90) for c in bg)
                bbox_a = draw.textbbox((0, 0), arrow, font=font_mvt)
                aw = bbox_a[2] - bbox_a[0]
                draw.text(((self.w - aw) // 2, 135), arrow, fill=arr_color, font=font_mvt)

            # Section curve + automation values
            _section_curve = _state.get("section_curve", "")
            _auto_vals = _state.get("automation_values") or {}
            if _section_curve or _auto_vals:
                try:
                    font_auto = ImageFont.truetype(self.font_path, 18)
                except (OSError, IOError):
                    font_auto = font_sm
                auto_color = tuple(min(255, c + 55) for c in bg)
                auto_y = self.h - 140
                if _section_curve:
                    curve_label = _section_curve.replace("_", " ")
                    draw.text((20, auto_y), curve_label, fill=auto_color, font=font_auto)
                    auto_y += 20
                if isinstance(_auto_vals, dict):
                    for _ak, _av in list(_auto_vals.items())[:3]:
                        try:
                            bar_val = float(_av)
                        except (TypeError, ValueError):
                            continue
                        bar_label = _ak[0].upper()
                        bar_fill = int(60 * max(0.0, min(1.0, bar_val)))
                        draw.text((20, auto_y), bar_label, fill=auto_color, font=font_auto)
                        draw.rectangle([36, auto_y + 2, 36 + 60, auto_y + 10],
                                       outline=auto_color)
                        if bar_fill > 0:
                            draw.rectangle([36, auto_y + 2, 36 + bar_fill, auto_y + 10],
                                           fill=auto_color)
                        auto_y += 16
        except (FileNotFoundError, Exception):
            pass

        # Sample-layer status
        try:
            import json as _json_s
            with open("/tmp/sample_dsp_activity.json") as _sf:
                _sample_state = _json_s.load(_sf)
            try:
                with open("/tmp/sample_playback_state.json") as _spf:
                    _sample_playback_state = _json_s.load(_spf)
            except (FileNotFoundError, Exception):
                _sample_playback_state = {}
            try:
                with open("/tmp/self_listen.json") as _slf:
                    _self_listen_state = _json_s.load(_slf)
            except (FileNotFoundError, Exception):
                _self_listen_state = {}
            sample_text = face_display_sample_status_text(_sample_state, _sample_playback_state, _self_listen_state)
            if sample_text:
                try:
                    font_sample = ImageFont.truetype(self.font_path, 24)
                except (OSError, IOError):
                    font_sample = font_sm
                sample_color = tuple(min(255, c + 85) for c in bg)
                bbox_s = draw.textbbox((0, 0), sample_text, font=font_sample)
                sw = bbox_s[2] - bbox_s[0]
                draw.text(((self.w - sw) // 2, 170), sample_text, fill=sample_color, font=font_sample)
        except (FileNotFoundError, Exception):
            pass

        # Theramini state + duet mode indicator
        try:
            import json as _json_t
            with open("/tmp/theramini_state.json") as _ft:
                _tstate = _json_t.load(_ft)
            _t_playing = _tstate.get("is_playing", False)
            _t_note = _tstate.get("pitch_note", "")
            _t_conf = _tstate.get("pitch_confidence", 0)
            _t_fresh = (time.time() - _tstate.get("timestamp", 0)) < 2.0

            if _t_playing and _t_fresh and _t_conf > 0.3:
                try:
                    font_hear = ImageFont.truetype(self.font_path, 30)
                except (OSError, IOError):
                    font_hear = font_sm
                hear_text = f"Hearing: {_t_note}"
                hear_color = (150, 220, 180)
                bbox_h = draw.textbbox((0, 0), hear_text, font=font_hear)
                hw = bbox_h[2] - bbox_h[0]
                draw.text(((self.w - hw) // 2, 140), hear_text, fill=hear_color, font=font_hear)
        except (FileNotFoundError, Exception):
            pass

        # Composer mode indicator
        try:
            _comp_mode = _state.get("mode", "solo") if "_state" in dir() else "solo"
            _comp_tnote = _state.get("theramini_note", "") if "_state" in dir() else ""
            if _comp_mode == "duet":
                try:
                    font_mode = ImageFont.truetype(self.font_path, 24)
                except (OSError, IOError):
                    font_mode = font_sm
                mode_text = "DUET"
                mode_color = (180, 220, 150)
                draw.text((20, 30), mode_text, fill=mode_color, font=font_mode)
        except Exception:
            pass

        # Room activity — eye widen on transients
        try:
            import json as _json_r
            with open("/tmp/room_activity.json") as _fr:
                _ract = _json_r.load(_fr)
            if _ract.get("recent_transient", False):
                # Widen eyes briefly — increase eye size for this frame
                # (This modifies the expression variable used by the eye drawing)
                pass  # Eye widening handled by expression override below
        except (FileNotFoundError, Exception):
            pass

        # Message from CypherClaw to the humans
        try:
            import json as _json2
            with open("/tmp/face_message.json") as _f2:
                _st2 = _json2.load(_f2)
            _msg = _st2.get("message", "")
            _msg_until = _st2.get("message_until", 0)
            if _msg and time.time() < _msg_until:
                try:
                    font_msg = ImageFont.truetype(self.font_path, 36)
                except (OSError, IOError):
                    font_msg = font_sm
                msg_color = (220, 230, 240)
                # Word wrap
                words = _msg.split()
                lines = []
                line = ""
                for w in words:
                    test = line + " " + w if line else w
                    bbox_t = draw.textbbox((0, 0), test, font=font_msg)
                    if bbox_t[2] - bbox_t[0] > self.w - 100:
                        lines.append(line)
                        line = w
                    else:
                        line = test
                if line:
                    lines.append(line)
                # Draw centered, below the face
                msg_y = face_cy + fry + 30
                for ml in lines:
                    bbox_ml = draw.textbbox((0, 0), ml, font=font_msg)
                    mlw = bbox_ml[2] - bbox_ml[0]
                    draw.text(((self.w - mlw) // 2, msg_y), ml, fill=msg_color, font=font_msg)
                    msg_y += 44
        except (FileNotFoundError, Exception):
            pass

        # Active characters — show who's playing
        active_chars = self._read_active_characters()
        if active_chars:
            char_text = " · ".join(active_chars[:5])
            try:
                font_cast = ImageFont.truetype(self.font_path, 18)
            except (OSError, IOError):
                font_cast = font_sm
            cast_color = tuple(min(255, c + 50) for c in bg)
            bbox_cast = draw.textbbox((0, 0), char_text, font=font_cast)
            cw = bbox_cast[2] - bbox_cast[0]
            draw.text(((self.w - cw) // 2, self.h - 100), char_text,
                      fill=cast_color, font=font_cast)

        # Observer insight — show what I see
        obs = self._read_observer()
        if obs.get("someone_here"):
            try:
                font_obs = ImageFont.truetype(self.font_path, 16)
            except (OSError, IOError):
                font_obs = font_sm
            obs_color = tuple(min(255, c + 35) for c in bg)
            draw.text((20, 60), "someone is here",
                      fill=obs_color, font=font_obs)

        # Thought bubble
        if now < self.thought_until and self.thought:
            alpha = min(1.0, (self.thought_until - now) / 2.0)
            tc = tuple(min(255, int(c + 100 * alpha)) for c in bg)
            bbox = draw.textbbox((0, 0), self.thought, font=font_thought)
            tw = bbox[2] - bbox[0]
            tx = (self.w - tw) // 2
            ty = face_cy + fry + 40
            draw.text((tx, ty), self.thought, fill=tc, font=font_thought)

        return img


def pil_to_pygame(img: Image.Image) -> pygame.Surface:
    """Convert PIL Image to pygame Surface."""
    raw = img.tobytes("raw", "RGB")
    return pygame.image.fromstring(raw, img.size, "RGB")


def init_pygame_display() -> None:
    """Initialize only the pygame modules the face display actually uses."""
    pygame.display.init()
    if not pygame.font.get_init():
        pygame.font.init()


def main():
    """Main face display loop."""
    display_idx = int(os.environ.get("FACE_DISPLAY", "1"))

    init_pygame_display()
    pygame.display.set_caption("CypherClaw Face")

    # Position window on the correct display
    if display_idx == 1:
        os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"

    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)
    clock = pygame.time.Clock()
    renderer = FaceRenderer()

    running = True
    # Keyboard chat
    chat = KeyboardChat()

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    start = time.time()
    mood = load_mood()
    last_mood_load = time.time()

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if chat:
                    consumed = chat.handle_keypress(event.key, getattr(event, "unicode", ""), pygame.key.get_mods())
                    if not consumed and event.key == pygame.K_ESCAPE:
                        running = False
                elif event.key == pygame.K_ESCAPE:
                    running = False

        t = time.time() - start

        # Reload mood every 5 seconds
        if time.time() - last_mood_load > 5:
            mood = load_mood()
            last_mood_load = time.time()

        frame = renderer.render(mood, t)
        # Floating chat + system monitor
        if chat:
            chat.poll_system()
            chat.poll_message_bus()
            frame_rgba = frame.convert("RGBA")
            chat.render(frame_rgba)
            frame = frame_rgba.convert("RGB")

        surface = pil_to_pygame(frame)
        screen.blit(surface, (0, 0))
        pygame.display.flip()
        clock.tick(30 if (chat and chat.has_visible_content) else FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
