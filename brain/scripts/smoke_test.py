"""Smoke-test the local brain endpoint with an image + grounding prompt.

Generates a synthetic UI screenshot (a window with a Submit button), sends it
to the OpenAI-compatible endpoint, and prints the request summary + response.
Run with the repo venv: .venv\\Scripts\\python.exe brain\\scripts\\smoke_test.py
"""

import base64
import io
import json
import os
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env_base() -> str:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("LOCAL_MODEL_BASE="):
                return line.split("=", 1)[1].strip()
    return "http://localhost:8000/v1"


def make_test_image() -> str:
    img = Image.new("RGB", (800, 600), "#f0f0f0")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 800, 40], fill="#2d2d44")  # title bar
    d.text((10, 12), "Invoice Form", fill="white")
    d.rectangle([100, 120, 500, 150], outline="#888")  # text field
    d.text((110, 128), "Vendor name...", fill="#999")
    d.rectangle([340, 480, 460, 520], fill="#3366cc")  # button
    d.text((368, 492), "Submit", fill="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def main() -> int:
    base = load_env_base()
    model = os.environ.get("LOCAL_MODEL_NAME", "ui-tars-1.5-7b")
    prompt = (
        "You see a screenshot of a Windows application. "
        "Locate the Submit button and describe where it is on the screen, "
        "including approximate pixel coordinates."
    )
    payload = {
        "model": model,
        "max_tokens": 300,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{make_test_image()}"},
                    },
                ],
            }
        ],
    }
    print(f"POST {base}/chat/completions  model={model}")
    print(f"Prompt: {prompt}")
    resp = requests.post(f"{base}/chat/completions", json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    print("\n--- Response ---")
    print(data["choices"][0]["message"]["content"])
    print("\n--- Usage ---")
    print(json.dumps(data.get("usage", {}), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
