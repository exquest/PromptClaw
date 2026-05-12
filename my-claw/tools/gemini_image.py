#!/usr/bin/env python3
"""Gemini image generation tool for CypherClaw.

Reads a prompt from a file (passed as first arg) or stdin,
calls Gemini's native image generation, saves the result,
and prints the output path to stdout.

Requires:
    pip install google-genai
    export GEMINI_API_KEY=<your key>
"""

import base64
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]


OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "images"
MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")


def _response_parts(response: Any) -> list[Any]:
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return []

    first_candidate = candidates[0]
    content = getattr(first_candidate, "content", None)
    parts = getattr(content, "parts", None)
    if not parts:
        return []
    return list(parts)


def _inline_bytes(part: Any) -> bytes | None:
    inline_data = getattr(part, "inline_data", None)
    if inline_data is None:
        return None

    data = getattr(inline_data, "data", None)
    if isinstance(data, str):
        return base64.b64decode(data)
    if isinstance(data, bytes):
        return data
    return None


def _inline_extension(part: Any) -> str:
    inline_data = getattr(part, "inline_data", None)
    mime_type = getattr(inline_data, "mime_type", "") if inline_data is not None else ""
    if isinstance(mime_type, str) and "/" in mime_type:
        return mime_type.split("/")[-1]
    return "png"


def generate_image(prompt: str) -> Path:
    """Generate an image from a text prompt and save it to OUTPUT_DIR."""
    if genai is None or types is None:
        print("ERROR: google-genai package not installed. Run: pip install google-genai", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        ),
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    text_parts = []
    image_path = None

    for part in _response_parts(response):
        image_bytes = _inline_bytes(part)
        if image_bytes is not None:
            ext = _inline_extension(part)
            image_path = OUTPUT_DIR / f"gen_{timestamp}.{ext}"
            image_path.write_bytes(image_bytes)
        else:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text:
                text_parts.append(text)

    if not image_path:
        print("WARNING: No image returned by the model.", file=sys.stderr)
        if text_parts:
            print("\n".join(text_parts))
        sys.exit(1)

    # Print structured output for the orchestrator
    print(f"image_path: {image_path.resolve()}")
    if text_parts:
        print(f"caption: {' '.join(text_parts)}")
    return image_path


def main():
    # Read prompt from file arg or stdin
    if len(sys.argv) > 1:
        prompt_file = Path(sys.argv[1])
        if prompt_file.exists():
            prompt = prompt_file.read_text().strip()
        else:
            # Treat args as the prompt itself
            prompt = " ".join(sys.argv[1:])
    else:
        prompt = sys.stdin.read().strip()

    if not prompt:
        print("ERROR: No prompt provided.", file=sys.stderr)
        sys.exit(1)

    generate_image(prompt)


if __name__ == "__main__":
    main()
