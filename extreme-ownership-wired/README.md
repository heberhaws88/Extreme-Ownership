# Extreme Ownership: Wired — setup guide

One weekly episode covers **both** sister companies — Horsepower Electric (electrical) and Wells Cutting Edge (landscaping) — as two back-to-back stories under the same chapter and perspective. This mirrors the pattern you used for Come Follow Lead inside BOM-Study: a second podcast living in its own folder in the same repo, sharing your existing GitHub Pages hosting.

## How the schedule works

- One episode airs every Monday, roughly 30–40 minutes.
- Each episode = one book chapter + one perspective role, told twice: once as an Electric story, once as a Landscape story, with a shared lesson explained once in between.
- Weekly perspective rotation: Apprentice → Journeyman → Lead → Foreman, repeating every 4 weeks.
- Chapter changes monthly (4 weeks per chapter, matching the perspective rotation).
- On 5-Monday months, a bonus episode covers an outside perspective — Project Manager, Owner, or Supplier — rotating across the year.
- Full 12-chapter cycle = 52 episodes, Sept 7, 2026 → Aug 30, 2027, then loops back to Chapter 1.

## Suggested repo layout

```
BOM-Study/
├── (existing BOM Study files)
├── come-follow-lead/
│   └── (existing files)
└── extreme-ownership-wired/
    ├── calendar.md              ← human-readable schedule (this package)
    ├── calendar.json            ← machine-readable schedule the script reads (this package)
    ├── system-prompt.md         ← script-writing instructions, both trade contexts (this package)
    ├── generate_episode.py      ← weekly generator (this package)
    └── episodes/                ← generated scripts + mp3s land here (created automatically)
```

Copy the four files above into a new `extreme-ownership-wired/` folder in BOM-Study. Copy `weekly-workflow.yml` into `.github/workflows/` (rename it to something like `extreme-ownership-wired.yml` alongside your existing workflow files — no changes needed to the workflow itself, it already just runs the generator every Monday).

## Before you turn it on

1. **Confirm secrets** — `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` should already exist as repo secrets from BOM-Study; the new workflow reuses them.
2. **Wire up publishing** — `generate_episode.py` has a `TODO` where it should hook into whatever you're already doing in BOM-Study to update the RSS feed and push audio live on GitHub Pages. Since I can't see your existing publish step, copy that logic over from your BOM-Study script.
3. **Pick the narrator voice** — `NARRATOR_VOICE = "onyx"` in `generate_episode.py` is a placeholder. OpenAI TTS voices: alloy, echo, fable, onyx, nova, shimmer — worth generating a couple of test clips to see which reads humor best across two back-to-back stories.
4. **Test before the first Monday** — run the workflow manually via `workflow_dispatch` (or run `generate_episode.py` locally with today's date matched against a test calendar entry) so you're not debugging on Sept 7 morning. Given each episode is now doing double duty (two full stories at 30–40 min), it's worth reading the first couple of generated scripts closely to make sure the trade sections stay cleanly separated and neither story runs too long at the other's expense.
5. **Audio stitching** — OpenAI's TTS API caps input at 4,096 characters per call, and a 30–40 minute script runs well past that. `generate_episode.py` now splits the script into paragraph-safe chunks, synthesizes each separately, and stitches them into one mp3 with `pydub` (which needs `ffmpeg` installed — already added to the workflow). If you run this locally, install ffmpeg first (`brew install ffmpeg` on Mac, `apt install ffmpeg` on Linux).
6. **Cron timing** — same lesson as BOM-Study: leave the schedule trigger untouched through one full overnight cycle before trusting it fires on its own.

## If you want to tweak the humor calibration

Everything about tone, length, and story structure — including both trade-context blocks and the 8-beat structure — lives in `system-prompt.md`. If an episode comes back too tame, too broad, runs long, or if landscaping and electrical details start bleeding into each other, that's the file to edit — no code changes needed.
