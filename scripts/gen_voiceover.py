#!/usr/bin/env python3
"""Generate the demo-video voiceover with qwen3-tts-flash (DashScope intl).

Reads the 9 VO lines, synthesizes each to WAV, downloads them, and concatenates
into one voiceover track (with a short gap between lines) via ffmpeg.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
KEY = os.environ["QWEN_API_KEY"]
URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "scratch_video"
OUT.mkdir(parents=True, exist_ok=True)

VOICE = "Cherry"
GAP_SEC = 0.7

LINES = [
    "Selling software across the US–China border means turning every inquiry email into a bilingual quote, by hand. QuotePilot does it on autopilot.",
    "Read the ask, often in Chinese. Look up pricing. Convert US dollars to yuan at today's rate. Get the arbitration and tax clauses right. One to two hours per inquiry, and the mistakes are the expensive kind.",
    "Paste an inquiry, English or Chinese, and hand it to the agent.",
    "A six-stage pipeline runs on Alibaba Cloud Function Compute. Three Qwen models split the work: a flash model extracts, a coder model maps the catalog, and qwen-max writes the bilingual draft. Live exchange rates come from a keyless feed.",
    "Then it stops, for exactly one human decision. It surfaces the risk flags it found, like a customer asking for a Chinese VAT invoice a US entity can't issue, and shows the full bilingual quote.",
    "The operator stays in control: adjust quantities, prices, or discounts. The server re-prices with exact decimal math and re-renders. The model never touches the numbers.",
    "Approve, and out come a formal bilingual quotation and a ready-to-send reply email, with a full audit trail. The whole run cost a few thousand Qwen tokens.",
    "One more thing. QuotePilot isn't just powered by Qwen, it was largely written by Qwen. A small harness dispatched coding tasks to Qwen models while a supervising agent reviewed every output. Total build cost: under one dollar.",
    "The rule that makes it trustworthy: language to the models, ledgers to the code. QuotePilot, powered by Qwen, on Alibaba Cloud.",
]


def synth(text: str, dest: Path) -> None:
    body = {"model": "qwen3-tts-flash", "input": {"text": text, "voice": VOICE, "language_type": "English"}}
    for attempt in range(3):
        r = httpx.post(URL, headers={"Authorization": f"Bearer {KEY}"}, json=body, timeout=90)
        r.raise_for_status()
        audio = r.json().get("output", {}).get("audio", {})
        url = audio.get("url")
        if url:
            wav = httpx.get(url, timeout=90).content
            dest.write_bytes(wav)
            return
        time.sleep(2 ** attempt)
    raise RuntimeError(f"no audio url for: {text[:40]}")


def main() -> None:
    parts = []
    total_chars = 0
    for i, line in enumerate(LINES, 1):
        dest = OUT / f"vo_{i:02d}.wav"
        print(f"[{i}/{len(LINES)}] synth {len(line)} chars…", flush=True)
        synth(line, dest)
        total_chars += len(line)
        parts.append(dest)

    # build a silence clip matching the first file's format
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=sample_rate,channels", "-of", "json", str(parts[0])],
        capture_output=True, text=True)
    info = json.loads(probe.stdout)["streams"][0]
    sr, ch = info["sample_rate"], info["channels"]
    silence = OUT / "gap.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    f"anullsrc=r={sr}:cl={'mono' if ch==1 else 'stereo'}",
                    "-t", str(GAP_SEC), str(silence)], check=True, capture_output=True)

    # concat list with gaps between lines
    listfile = OUT / "concat.txt"
    with listfile.open("w") as fh:
        for i, p in enumerate(parts):
            fh.write(f"file '{p.name}'\n")
            if i < len(parts) - 1:
                fh.write(f"file '{silence.name}'\n")
    out_wav = OUT / "voiceover.wav"
    out_mp3 = OUT / "voiceover.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                    "-c", "copy", str(out_wav)], check=True, capture_output=True, cwd=OUT)
    subprocess.run(["ffmpeg", "-y", "-i", str(out_wav), "-b:a", "192k", str(out_mp3)],
                   check=True, capture_output=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nk=1:nw=1", str(out_wav)], capture_output=True, text=True).stdout.strip()
    print(f"\n✓ voiceover: {out_mp3}  ({float(dur):.1f}s, {total_chars} chars)")
    print(f"  per-line WAVs in {OUT}")


if __name__ == "__main__":
    main()
