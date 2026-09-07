#!/usr/bin/env python3
"""
Extreme Ownership: Wired — weekly episode generator.

One episode per Monday covers BOTH sister companies (Horsepower Electric and
Wells Cutting Edge) in the same script — same chapter, same perspective,
two back-to-back trade-specific stories. Pulls this week's slot from
calendar.json, generates a script via the Anthropic API, converts it to audio
via OpenAI TTS (chunked to stay under the ~4096 char input limit), writes the
result into episodes/, then appends it to the manifest and rebuilds feed.xml
via feed_builder.py — same pattern as the Daily show, but fully self-contained
to this folder so it never touches Daily's data, feed, or episodes.

Env vars required (set as GitHub Actions secrets, already shared repo-wide):
  ANTHROPIC_API_KEY
  OPENAI_API_KEY
"""

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import anthropic
from openai import OpenAI
from pydub import AudioSegment  # requires ffmpeg installed; pip install pydub

REPO_ROOT = Path(__file__).resolve().parent
CALENDAR_PATH = REPO_ROOT / "calendar.json"
SYSTEM_PROMPT_PATH = REPO_ROOT / "system-prompt.md"
EPISODES_DIR = REPO_ROOT / "episodes"

# OpenAI TTS caps input at 4096 characters per request. Episodes at 30-40 min
# (~4,500-6,000 words / ~25,000-35,000 characters) need to be chunked and
# stitched back together.
TTS_CHAR_LIMIT = 3500  # matches Daily's safety margin under the hard 4096 cap
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
    import io

    chunks = chunk_script(script_text)
    print(f"  Script split into {len(chunks)} TTS chunk(s) (limit {TTS_CHAR_LIMIT} chars each)")

    combined = AudioSegment.empty()
    for chunk in chunks:
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=NARRATOR_VOICE,
            input=chunk,
        )
        audio_bytes = response.read() if hasattr(response, "read") else response.content
        segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        combined += segment
        # small pause between chunks, especially useful right at the
        # Electric -> Landscape transition
        combined += AudioSegment.silent(duration=250)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(out_path, format="mp3")


def main() -> None:
    today = date.today()
    slot = load_this_weeks_slot(today)

    EPISODES_DIR.mkdir(exist_ok=True)
    slug = f"ep{slot['episode_num']:03d}-{slot['perspective'].lower()}"
    script_path = EPISODES_DIR / f"{slug}.txt"
    audio_path = EPISODES_DIR / f"{slug}.mp3"

    print(f"Generating script for episode {slot['episode_num']} "
          f"({slot['chapter']} / {slot['perspective']})...")
    script_text = generate_script(slot)
    script_path.write_text(script_text, encoding="utf-8")

    print("Synthesizing audio...")
    synthesize_audio(script_text, audio_path)

    file_size_bytes = audio_path.stat().st_size
    duration_seconds = int(len(AudioSegment.from_file(audio_path)) / 1000)

    sys.path.insert(0, str(REPO_ROOT))
    import feed_builder

    config = feed_builder.load_config()
    title = f"Ep. {slot['episode_num']:03d} — {slot['chapter']} ({slot['perspective']})"
    description = (
        f"This week's Extreme Ownership principle applied to both Horsepower Electric "
        f"and Wells Cutting Edge, through the {slot['perspective']} perspective."
    )
    pub_date = datetime.now(timezone.utc)

    entry = {
        "guid": f"{config['site_base_url']}/episodes/{slug}",
        "title": title,
        "description": description,
        "pub_date": pub_date.isoformat(),
        "audio_url": f"{config['site_base_url']}/episodes/{audio_path.name}",
        "file_size_bytes": file_size_bytes,
        "duration_seconds": duration_seconds,
        "mp3_filename": audio_path.name,
    }
    manifest = feed_builder.append_episode(entry)
    feed_builder.build_feed(manifest=manifest, config=config)

    print(f"Done: {script_path.name}, {audio_path.name} "
          f"({file_size_bytes} bytes, ~{duration_seconds}s), feed.xml rebuilt.")


if __name__ == "__main__":
    sys.exit(main())
