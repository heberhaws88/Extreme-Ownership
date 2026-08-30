# Extreme Ownership Daily — setup guide

A weekday podcast that works through the 12 principles of *Extreme
Ownership* (Jocko Willink & Leif Babin), one principle per episode, on a
15–20 minute run time. Every 12-episode pass through the book applies the
principles through a different lens, always in this order:

1. Disciple of Jesus Christ
2. Warrant Officer / Army National Guard Engineer
3. Business Owner / Electrician
4. Husband and Father

...then it loops back to lens 1 and goes around again, indefinitely. No
real names are used for family, soldiers, employees, or clients anywhere in
the generated scripts.

This is a **standalone repo**, separate from any other show you run — its
own GitHub Pages feed, its own Actions schedule, its own API key secrets.
Everything in this bundle is already laid out the way a repo root should
look, so setup is mostly "create an empty repo, put these files in it."

## What's in this bundle

```
.github/workflows/
  extreme-ownership-daily.yml   the weekday automation — already in the right place
data/
  principles.json               the 12 chapters, in original (non-quoted) language
  lenses.json                   the 4 lenses and their framing/voice notes
  show_config.json              podcast metadata — YOU NEED TO EDIT THIS
  state.json                    tracks which episode comes next (starts at 1)
  episodes_manifest.json        created automatically on first run
scripts/
  generate_episode.py           the main pipeline: writes + voices + publishes one episode
  feed_builder.py               rebuilds feed.xml from the manifest
episodes/                       generated .mp3 + .txt transcripts land here
feed/                           feed.xml (the podcast RSS feed) lands here
artwork/                        put your cover art image here (see Step 5)
requirements.txt
README.md                       this file
```

## Step 1 — Create the new repo

On github.com, click **New repository**. Suggested name: `extreme-ownership-daily`
(you can use anything — just keep track of it, you'll need it in Step 2).

Make it **Public** — GitHub Pages' free tier requires a public repo to
serve the feed for free. "Public" just means someone with the exact URL
could find it; it isn't listed or promoted anywhere. Don't initialize it
with a README, .gitignore, or license — leave it empty so there's nothing
to conflict with when you add these files.

## Step 2 — Get these files into the repo

**If you have git installed:** clone the new empty repo, copy everything
from this unzipped bundle into that folder (so `.github/`, `data/`,
`scripts/`, etc. end up at the repo root, not nested inside another
folder), then:

```bash
git add .
git commit -m "Initial Extreme Ownership Daily setup"
git push
```

**If you don't have git installed / prefer the browser:**

1. Unzip this bundle. You should see `.github`, `data`, `scripts`,
   `episodes`, `feed`, `artwork`, `requirements.txt`, and `README.md`
   sitting next to each other (not inside one more wrapping folder — if
   your unzip tool created an extra outer folder, go inside it first).
2. On your new repo's page, click **Add file → Upload files**, then drag
   all of those files and folders in at once (drag them together, not the
   parent folder). Modern GitHub keeps folder structure on drag-and-drop,
   including the `.github/workflows` path. Commit.
3. Double check afterward that the workflow file really landed at
   `.github/workflows/extreme-ownership-daily.yml` in the repo — click
   into the `.github` folder on GitHub to confirm. Some browsers are
   inconsistent about uploading dot-folders; if it didn't come through,
   use **Add file → Create new file**, type the exact path
   `.github/workflows/extreme-ownership-daily.yml` as the filename (GitHub
   creates the folders for you), and paste in that file's contents from
   your unzipped copy.

## Step 3 — Fill in `data/show_config.json`

Click into the file on GitHub and use the pencil icon to edit, or edit
locally before your commit. Replace every `REPLACE_...` placeholder:

- `author_name`, `author_email` — shown in podcast app "About this show"
- `cover_image_url` and `site_base_url` — for a repo named
  `extreme-ownership-daily` owned by `yourname`, GitHub Pages serves it at:
  `https://yourname.github.io/extreme-ownership-daily`
  so `site_base_url` becomes exactly that, and `cover_image_url` becomes
  that plus `/artwork/cover.jpg`. (This assumes GitHub Pages is set to
  serve from the repo root — confirm that in Step 6.)

The `tts` block defaults to OpenAI's `tts-1-hd` model with the `onyx`
voice (a deep, steady voice) — change it if you'd rather use a different
OpenAI TTS voice.

## Step 4 — Add your API key secrets

Go to **Settings → Secrets and variables → Actions** on this new repo and
add two repository secrets:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`

These are new secrets for this new repo — they don't carry over from any
other repo automatically.

## Step 5 — Add cover art

Podcast apps require square artwork, ideally 3000x3000px (minimum
1400x1400px), JPG or PNG. Upload a file to `artwork/cover.jpg` in the
repo (drag it in via **Add file → Upload files** while inside the
`artwork` folder), matching whatever `cover_image_url` points to in Step 3.

## Step 6 — Enable GitHub Pages

Go to **Settings → Pages**. Under "Build and deployment," set Source to
"Deploy from a branch," pick your default branch (usually `main`) and
folder `/ (root)`. Save. GitHub will show you the live URL once it's
built — confirm it matches what you put in `site_base_url`.

## Step 7 — Test it before trusting it

From a local clone, with `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` set in
your shell:

```bash
pip install -r requirements.txt
python scripts/generate_episode.py --dry-run
```

`--dry-run` skips both paid APIs entirely — it writes a placeholder
transcript and a short silent mp3, but runs every other part of the
pipeline for real (prompt construction, feed.xml rebuilding, state.json
advancement). Good for making sure the plumbing works before spending
anything.

You can also preview the upcoming rotation without generating anything:

```bash
python scripts/generate_episode.py --print-schedule 15
```

Once the workflow file is pushed, trigger it manually from the repo's
**Actions** tab (find "Extreme Ownership Daily Episode" → **Run
workflow** → you can check the "dry run" box there too) before letting
the weekday schedule take over. Expect the first live run to possibly
need a small fix — that's normal, not a sign something is fundamentally
wrong.

## Step 8 — Subscribe

Once a real (non-dry-run) episode or two has published, the feed is live
at:

```
<site_base_url>/feed/feed.xml
```

Paste that URL into any podcast app that supports adding a show by RSS
URL (Apple Podcasts, Overcast, Pocket Casts, etc. — not Audible).

## How the rotation actually works

`data/state.json` stores one number: `next_episode_number`. Everything
else is computed from it:

- `principle_index = (episode_number - 1) % 12` — which of the 12
  chapters plays today
- `pass_number = (episode_number - 1) // 12` — how many full 12-episode
  passes have happened
- `lens_index = pass_number % 4` — which of the 4 lenses this pass uses
- `repeat_number = pass_number // 4` — how many times we've already been
  through this exact lens before

So episodes 1–12 are all through the Disciple lens (one per principle),
13–24 are Warrant Officer, 25–36 are Business Owner, 37–48 are
Husband/Father, then 49–60 goes back to Disciple for a second pass — and
on repeat passes, the prompt explicitly tells the model to acknowledge
returning to this ground and go deeper rather than repeating itself. This
means the show can run indefinitely on weekdays without ever needing you
to intervene, and you can jump ahead with
`python scripts/generate_episode.py --print-schedule N` to sanity-check
what's coming.

## Editing the voice/style later

Almost all of the show's personality lives in one place:
`build_prompts()` inside `scripts/generate_episode.py`. If episodes come
back too preachy, too generic, too long/short, or missing something you
want covered every time, that function — not the data files — is what to
edit.

`data/lenses.json` is the next most useful edit point: each lens has a
`framing` field (what this lens should focus on) and a `voice_notes` field
(tone). Adjust those directly if, say, the Warrant Officer episodes should
lean into a specific kind of scenario more.

## Costs

A few cents per episode from Claude for the script, a few cents from
OpenAI TTS for ~15–20 minutes of audio. Five episodes a week, well under
$2–3/month total. GitHub, GitHub Pages, and GitHub Actions are free at
this scale on a public repo.
