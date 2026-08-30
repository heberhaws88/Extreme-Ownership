"""
Builds/rebuilds the podcast RSS feed (feed.xml) from the episode manifest.

Design choices:
  - Rather than parsing and mutating an existing XML file each run (fragile),
    we keep a simple JSON manifest of every published episode and regenerate
    the *entire* feed.xml from that manifest on every run. Cheap at this
    scale (a handful to a few hundred episodes) and much harder to corrupt
    than incremental XML surgery.
  - RSS/iTunes XML is hand-built with the standard library (string
    templating + proper escaping) instead of a third-party feed library.
    One less dependency that could go stale or fail to install, for a
    format that's small and well-documented enough to own directly.
"""

import json
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "data" / "episodes_manifest.json"
CONFIG_PATH = REPO_ROOT / "data" / "show_config.json"
FEED_OUTPUT_PATH = REPO_ROOT / "feed" / "feed.xml"


def load_manifest() -> list:
    if not MANIFEST_PATH.exists():
        return []
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest: list) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def append_episode(entry: dict) -> list:
    """
    entry expects keys:
      guid, title, description, pub_date (ISO string, tz-aware),
      audio_url, file_size_bytes, duration_seconds, mp3_filename
    Returns the updated manifest.
    """
    manifest = load_manifest()
    manifest.append(entry)
    save_manifest(manifest)
    return manifest


def _seconds_to_hhmmss(total_seconds) -> str:
    total_seconds = int(total_seconds)
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _rfc2822(pub_date) -> str:
    if isinstance(pub_date, str):
        pub_date = datetime.fromisoformat(pub_date)
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    return format_datetime(pub_date)


def _render_item(ep: dict) -> str:
    return f"""    <item>
      <title>{escape(ep['title'])}</title>
      <description>{escape(ep['description'])}</description>
      <guid isPermaLink="false">{escape(ep['guid'])}</guid>
      <pubDate>{_rfc2822(ep['pub_date'])}</pubDate>
      <enclosure url="{escape(ep['audio_url'])}" length="{int(ep['file_size_bytes'])}" type="audio/mpeg" />
      <itunes:duration>{_seconds_to_hhmmss(ep['duration_seconds'])}</itunes:duration>
      <itunes:explicit>no</itunes:explicit>
    </item>"""


def build_feed(manifest: list = None, config: dict = None) -> str:
    """Regenerates feed.xml from the manifest (newest episode first). Returns
    the path written."""
    if manifest is None:
        manifest = load_manifest()
    if config is None:
        config = load_config()

    # Newest first, per podcast RSS convention.
    ordered = sorted(
        manifest,
        key=lambda ep: ep["pub_date"] if isinstance(ep["pub_date"], str) else ep["pub_date"].isoformat(),
        reverse=True,
    )
    items_xml = "\n".join(_render_item(ep) for ep in ordered)
    last_build = _rfc2822(ordered[0]["pub_date"]) if ordered else _rfc2822(datetime.now(timezone.utc))

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(config['show_title'])}</title>
    <link>{escape(config['site_base_url'])}</link>
    <atom:link href="{escape(config['site_base_url'])}/feed/feed.xml" rel="self" type="application/rss+xml" />
    <description>{escape(config['show_description'])}</description>
    <language>{escape(config.get('language', 'en-us'))}</language>
    <lastBuildDate>{last_build}</lastBuildDate>
    <itunes:author>{escape(config['author_name'])}</itunes:author>
    <itunes:summary>{escape(config['show_description'])}</itunes:summary>
    <itunes:explicit>{'yes' if config.get('explicit') else 'no'}</itunes:explicit>
    <itunes:image href="{escape(config['cover_image_url'])}" />
    <image>
      <url>{escape(config['cover_image_url'])}</url>
      <title>{escape(config['show_title'])}</title>
      <link>{escape(config['site_base_url'])}</link>
    </image>
    <itunes:owner>
      <itunes:name>{escape(config['author_name'])}</itunes:name>
      <itunes:email>{escape(config['author_email'])}</itunes:email>
    </itunes:owner>
    <itunes:category text="{escape(config.get('itunes_category', 'Religion &amp; Spirituality'))}">
      <itunes:category text="{escape(config.get('itunes_subcategory', 'Christianity'))}" />
    </itunes:category>
{items_xml}
  </channel>
</rss>
"""

    FEED_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEED_OUTPUT_PATH.write_text(feed_xml, encoding="utf-8")
    return str(FEED_OUTPUT_PATH)


if __name__ == "__main__":
    # Manual rebuild from whatever manifest already exists on disk.
    path = build_feed()
    print(f"Rebuilt feed at {path}")
