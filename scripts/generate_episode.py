#!/usr/bin/env python3
"""
Generates one episode of the Extreme Ownership Daily show:
  1. Figures out today's principle + lens from state.json
  2. Asks Claude (Anthropic API) to write a spoken-word script
  3. Sends that script to OpenAI TTS (chunked) and stitches the audio
  4. Writes the mp3 + a text transcript into episodes/
  5. Appends the episode to the manifest and rebuilds feed.xml
  6. Advances state.json to the next episode

Run with --dry-run to test the rotation math, prompt construction, and file
plumbing WITHOUT calling any paid API or requiring API keys. Dry-run writes
a placeholder script and a short silent mp3 so the rest of the pipeline
(feed building, state advancement) can be verified end to end.

Run with --print-schedule N to just print what the next N episodes would be
(principle + lens + pass) without generating or touching anything.
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
EPISODES_DIR = REPO_ROOT / "episodes"

STATE_PATH = DATA_DIR / "state.json"
PRINCIPLES_PATH = DATA_DIR / "principles.json"
LENSES_PATH = DATA_DIR / "lenses.json"
CONFIG_PATH = DATA_DIR / "show_config.json"

MAX_TTS_CHARS = 3500  # stay comfortably under OpenAI's ~4096 char input limit


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def compute_slot(episode_number: int, num_principles: int, num_lenses: int):
    """
    episode_number is 1-indexed.
    Returns (principle_index, lens_index, pass_number, repeat_number).
    pass_number: 0-indexed count of full passes through all principles.
    repeat_number: how many times we've been through THIS lens before
                   (0 = first time through this lens).
    """
    zero_indexed = episode_number - 1
    principle_index = zero_indexed % num_principles
    pass_number = zero_indexed // num_principles
    lens_index = pass_number % num_lenses
    repeat_number = pass_number // num_lenses
    return principle_index, lens_index, pass_number, repeat_number


def build_prompts(principle: dict, lens: dict, repeat_number: int, config: dict):
    lo, hi = config["target_minutes"]
    wpm = config["words_per_minute_estimate"]
    word_lo, word_hi = lo * wpm, hi * wpm

    repeat_guidance = ""
    if repeat_number > 0:
        repeat_guidance = (
            f"\n\nThis is not the first time through this lens — this is pass "
            f"number {repeat_number + 1} using the {lens['label']} lens on this "
            f"principle. Briefly acknowledge that you've walked this ground before "
            f"(a sentence or two, not a big deal), then go somewhere fresher and "
            f"deeper than a first-pass listener would need — assume real growth "
            f"and new situations since last time, not a rerun of the same story."
        )

    system_prompt = f"""You are writing tonight's episode script for a daily spoken-word podcast \
called "{config['show_title']}". The host is one real person, speaking directly \
to the listener in first person. This script will be fed directly into \
text-to-speech, so it must read as natural spoken language:

- No markdown, no headers, no bullet points, no asterisks, no stage directions, \
no bracketed sound cues, no "[pause]" markers.
- Use punctuation (periods, commas, em dashes, occasional ellipses) to carry \
natural spoken rhythm and pauses instead.
- Write numbers, and anything else awkward when read aloud, the way you'd say \
them out loud.
- Return ONLY the spoken script itself. No title line, no episode number, no \
meta-commentary before or after it.

THE HOST'S IDENTITY (all four are always true of him — today's lens just \
decides which one is centerstage):
- A disciple of Jesus Christ, a member of The Church of Jesus Christ of \
Latter-day Saints.
- A Warrant Officer and engineer in the Army National Guard.
- An electrician who owns his own electrical contracting business.
- A husband, and a father of two boys and a girl.

HARD RULES:
- Never use real names for family members, soldiers, coworkers, employees, or \
clients. Use relational terms only: "my wife," "my oldest," "my daughter," "one \
of my apprentices," "a guy on my crew," "the officer I answer to," and so on.
- Every story or scenario from the Guard, the business, or home is an original, \
plausible, composite illustration of the principle — never claim it as a literal \
verbatim account, never invent real unit designations, real classified/ \
operational detail, or real named clients.
- Do not quote the book Extreme Ownership at length or reproduce its text. You \
may name the book and its authors, Jocko Willink and Leif Babin, and describe a \
principle's core idea briefly in your own original words — the bulk of the \
episode should be original application and story, not book summary.
- Be honest about failure and struggle, not just tidy resolutions. Extreme \
Ownership is fundamentally about owning what went wrong — a script that only \
tells stories where the host already had it figured out misses the point.
- Tone: direct, unflinching, practical, warm, occasionally dry-humored. Never \
preachy, never a sermon, never falsely triumphant.

LOOSE STRUCTURE (flex this naturally, don't make it feel like a template every \
time):
1. A short cold-open hook rooted in today's lens.
2. Name tonight's Extreme Ownership principle and explain its core idea in your \
own original words (not a book quote).
3. A brief beat (a minute or two) connecting the principle to following Jesus \
Christ — this stays present even on non-discipleship-lens nights, because faith \
is the constant underneath everything else for this host.
4. The main body: a specific, original story or scenario in tonight's lens that \
puts the principle to work, including real struggle or failure, not just a win.
5. A concrete, specific action or question the listener can carry into tomorrow.
6. A short close.

LENGTH: aim for {word_lo:.0f} to {word_hi:.0f} words — spoken at a natural pace \
this lands at roughly {lo} to {hi} minutes."""

    user_prompt = f"""Tonight's principle (chapter {principle['chapter']} of \
Extreme Ownership): {principle['title']}

Core idea: {principle['theme']}

Tonight's lens: {lens['label']}
Lens framing: {lens['framing']}
Voice notes for this lens: {lens['voice_notes']}

Some seed questions you can draw from (use, adapt, or ignore as fits the \
episode naturally): {" / ".join(principle['seed_questions'])}
{repeat_guidance}

Write tonight's full episode script now."""

    return system_prompt, user_prompt


def generate_script_text(system_prompt: str, user_prompt: str, config: dict) -> str:
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    message = client.messages.create(
        model=config["anthropic"]["model"],
        max_tokens=config["anthropic"]["max_tokens"],
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text").strip()


def placeholder_script_text(principle: dict, lens: dict, config: dict) -> str:
    lo, hi = config["target_minutes"]
    wpm = config["words_per_minute_estimate"]
    target_words = int(((lo + hi) / 2) * wpm)
    filler = (
        f"This is a dry run placeholder script for the principle {principle['title']} "
        f"through the {lens['label']} lens. "
    )
    words_so_far = 0
    parts = []
    while words_so_far < target_words:
        parts.append(filler)
        words_so_far += len(filler.split())
    return " ".join(parts)


def chunk_text(text: str, max_chars: int) -> list:
    """Split on sentence boundaries, keeping chunks under max_chars."""
    sentences = text.replace("\n", " ").split(". ")
    chunks, current = [], ""
    for i, sentence in enumerate(sentences):
        piece = sentence if sentence.endswith(".") else sentence + "."
        if len(current) + len(piece) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current:
        chunks.append(current.strip())
    return chunks


def synthesize_audio(script_text: str, config: dict, out_path: Path) -> None:
    from openai import OpenAI
    from pydub import AudioSegment
    import io

    client = OpenAI()  # reads OPENAI_API_KEY from env
    tts_cfg = config["tts"]
    chunks = chunk_text(script_text, MAX_TTS_CHARS)

    combined = AudioSegment.empty()
    for chunk in chunks:
        response = client.audio.speech.create(
            model=tts_cfg["model"],
            voice=tts_cfg["voice"],
            input=chunk,
        )
        audio_bytes = response.read() if hasattr(response, "read") else response.content
        segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        combined += segment

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(out_path, format="mp3")


def synthesize_silent_placeholder(config: dict, out_path: Path) -> int:
    """Dry-run stand-in: writes a short silent mp3 so duration/size plumbing
    can be tested without an API key or ffmpeg producing real speech.
    Returns duration in seconds."""
    from pydub import AudioSegment

    lo, hi = config["target_minutes"]
    duration_ms = int(((lo + hi) / 2) * 60 * 1000)
    # Keep the placeholder file itself short (5s) to avoid bloating the repo
    # during testing, but report the *intended* duration for feed metadata.
    silent = AudioSegment.silent(duration=5000)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    silent.export(out_path, format="mp3")
    return duration_ms // 1000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Skip real API calls; use placeholder script/audio.")
    parser.add_argument("--print-schedule", type=int, default=0,
                         help="Print the next N episodes' principle/lens plan and exit.")
    args = parser.parse_args()

    principles = load_json(PRINCIPLES_PATH)
    lenses = load_json(LENSES_PATH)
    config = load_json(CONFIG_PATH)
    state = load_json(STATE_PATH)

    if args.print_schedule:
        n = state["next_episode_number"]
        for ep in range(n, n + args.print_schedule):
            p_idx, l_idx, pass_no, repeat_no = compute_slot(ep, len(principles), len(lenses))
            print(f"Ep {ep:04d}: {principles[p_idx]['title']}  |  "
                  f"lens={lenses[l_idx]['label']}  |  pass={pass_no}  |  "
                  f"repeat_of_lens={repeat_no}")
        return

    episode_number = state["next_episode_number"]
    p_idx, l_idx, pass_no, repeat_no = compute_slot(episode_number, len(principles), len(lenses))
    principle = principles[p_idx]
    lens = lenses[l_idx]

    print(f"Generating episode {episode_number}: '{principle['title']}' "
          f"through the {lens['label']} lens (pass {pass_no}, "
          f"repeat #{repeat_no} of this lens). dry_run={args.dry_run}")

    system_prompt, user_prompt = build_prompts(principle, lens, repeat_no, config)

    slug = f"{episode_number:04d}-{lens['key']}-{principle['title'].lower().replace(' ', '-').replace(',', '')}"
    mp3_path = EPISODES_DIR / f"{slug}.mp3"
    transcript_path = EPISODES_DIR / f"{slug}.txt"

    if args.dry_run:
        script_text = placeholder_script_text(principle, lens, config)
        duration_seconds = synthesize_silent_placeholder(config, mp3_path)
    else:
        script_text = generate_script_text(system_prompt, user_prompt, config)
        synthesize_audio(script_text, config, mp3_path)
        from pydub import AudioSegment
        duration_seconds = int(len(AudioSegment.from_file(mp3_path)) / 1000)

    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(script_text, encoding="utf-8")

    file_size_bytes = mp3_path.stat().st_size
    title = f"Ep. {episode_number:04d} — {principle['title']} (through the {lens['label']})"
    description = (
        f"{principle['theme']} Tonight's lens: {lens['label']}."
    )
    audio_url = f"{config['site_base_url']}/episodes/{mp3_path.name}"
    pub_date = datetime.now(timezone.utc)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import feed_builder

    entry = {
        "guid": f"{config['site_base_url']}/episodes/{slug}",
        "title": title,
        "description": description,
        "pub_date": pub_date.isoformat(),
        "audio_url": audio_url,
        "file_size_bytes": file_size_bytes,
        "duration_seconds": duration_seconds,
        "mp3_filename": mp3_path.name,
    }
    manifest = feed_builder.append_episode(entry)
    feed_builder.build_feed(manifest=manifest, config=config)

    if state.get("show_started") is None:
        state["show_started"] = pub_date.isoformat()
    state["next_episode_number"] = episode_number + 1
    state["last_run_date"] = pub_date.isoformat()
    save_json(STATE_PATH, state)

    print(f"Done. Wrote {mp3_path.name} ({file_size_bytes} bytes, "
          f"~{duration_seconds}s), updated feed.xml, advanced state to "
          f"episode {state['next_episode_number']}.")


if __name__ == "__main__":
    main()
