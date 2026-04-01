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

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: google-genai package not installed. Run: pip install google-genai", file=sys.stderr)
    sys.exit(1)


OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "images"
MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")


def generate_image(prompt: str) -> Path:
    """Generate an image from a text prompt and save it to OUTPUT_DIR."""
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

    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            ext = part.inline_data.mime_type.split("/")[-1]
            image_path = OUTPUT_DIR / f"gen_{timestamp}.{ext}"
            image_path.write_bytes(base64.b64decode(part.inline_data.data) if isinstance(part.inline_data.data, str) else part.inline_data.data)
        elif part.text:
            text_parts.append(part.text)

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
