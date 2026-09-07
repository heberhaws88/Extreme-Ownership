#!/usr/bin/env python3
"""
Extreme Ownership: Wired — weekly episode generator.

One episode per Monday covers BOTH sister companies (Horsepower Electric and
Wells Cutting Edge) in the same script — same chapter, same perspective,
two back-to-back trade-specific stories. Pulls this week's slot from
calendar.json, generates a script via the Anthropic API, converts it to audio
via OpenAI TTS, and writes the output for GitHub Pages / RSS publishing.

Env vars required (set as GitHub Actions secrets):
  ANTHROPIC_API_KEY
  OPENAI_API_KEY
"""

import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

import anthropic
from openai import OpenAI
from pydub import AudioSegment  # requires ffmpeg installed; pip install pydub

# OpenAI TTS caps input at 4096 characters per request. Episodes at 30-40 min
# (~4,500-6,000 words / ~25,000-35,000 characters) need to be chunked and
# stitched back together.
TTS_CHAR_LIMIT = 4000  # leave a small safety margin under the hard 4096 cap

REPO_ROOT = Path(__file__).resolve().parent
CALENDAR_PATH = REPO_ROOT / "calendar.json"
SYSTEM_PROMPT_PATH = REPO_ROOT / "system-prompt.md"
OUTPUT_DIR = REPO_ROOT / "episodes"
NARRATOR_VOICE = "onyx"  # single consistent narrator voice across both companies

anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def load_this_weeks_slot(today: date) -> dict:
    """Find the calendar entry matching today's date (run via cron each Monday)."""
    with open(CALENDAR_PATH) as f:
        slots = json.load(f)
    for slot in slots:
        if datetime.strptime(slot["air_date"], "%Y-%m-%d").date() == today:
            return slot
    raise SystemExit(f"No episode scheduled for {today.isoformat()} — check calendar.json")


def build_prompt(slot: dict) -> str:
    template = SYSTEM_PROMPT_PATH.read_text()
    return (
        template.replace("{{CHAPTER}}", slot["chapter"])
        .replace("{{PERSPECTIVE}}", slot["perspective"])
        .replace("{{EPISODE_NUM}}", str(slot["episode_num"]))
    )


def generate_script(slot: dict) -> str:
    system_prompt = build_prompt(slot)
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=9000,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write episode {slot['episode_num']} of Extreme Ownership: Wired, covering "
                    f"both Horsepower Electric and Wells Cutting Edge. Chapter: {slot['chapter']}. "
                    f"Perspective: {slot['perspective']}."
                ),
            }
        ],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def chunk_script(script_text: str, limit: int = TTS_CHAR_LIMIT) -> list[str]:
    """Split into TTS-safe chunks on paragraph boundaries so we never cut mid-sentence."""
    paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # a single paragraph longer than the limit (rare) gets hard-split
            if len(para) > limit:
                for i in range(0, len(para), limit):
                    chunks.append(para[i:i + limit])
                current = ""
            else:
                current = para
    if current:
        chunks.append(current)
    return chunks


def synthesize_audio(script_text: str, out_path: Path) -> None:
    chunks = chunk_script(script_text)
    print(f"  Script split into {len(chunks)} TTS chunk(s) (limit {TTS_CHAR_LIMIT} chars each)")

    with tempfile.TemporaryDirectory() as tmpdir:
        combined = AudioSegment.empty()
        for i, chunk in enumerate(chunks):
            chunk_path = Path(tmpdir) / f"chunk_{i:03d}.mp3"
            with openai_client.audio.speech.with_streaming_response.create(
                model="tts-1-hd",
                voice=NARRATOR_VOICE,
                input=chunk,
            ) as response:
                response.stream_to_file(chunk_path)
            combined += AudioSegment.from_mp3(chunk_path)
            # small pause between chunks so stitched joins don't sound abrupt,
            # especially useful right at the Electric -> Landscape transition
            combined += AudioSegment.silent(duration=250)

        combined.export(out_path, format="mp3")


def main() -> None:
    today = date.today()
    slot = load_this_weeks_slot(today)

    OUTPUT_DIR.mkdir(exist_ok=True)
    slug = f"ep{slot['episode_num']:02d}-{slot['perspective'].lower()}"
    script_path = OUTPUT_DIR / f"{slug}.txt"
    audio_path = OUTPUT_DIR / f"{slug}.mp3"

    print(f"Generating script for episode {slot['episode_num']} "
          f"({slot['chapter']} / {slot['perspective']})...")
    script_text = generate_script(slot)
    script_path.write_text(script_text)

    print("Synthesizing audio...")
    synthesize_audio(script_text, audio_path)

    print(f"Done: {script_path.name}, {audio_path.name}")
    # TODO: hook into your existing RSS-feed-update + GitHub Pages publish step,
    # same as BOM-Study's publish stage.


if __name__ == "__main__":
    sys.exit(main())
