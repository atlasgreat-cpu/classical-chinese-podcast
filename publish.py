#!/usr/bin/env python3
"""
Publish podcast episodes to GitHub Pages RSS feed.

轻量版 — 独立脚本，只做两件事：
  1. 复制 MP3 到 GitHub 仓库
  2. 重新生成 RSS feed + push

使用:
  python3 publish.py <诗名>                        # 发布一首（从 episodes.json 读 title/desc）
  python3 publish.py <诗名> --title "..." --desc "..."  # 发布并指定 title/desc
  python3 publish.py --list                        # 列出已发布节目
  python3 publish.py --regenerate                  # 仅重新生成 RSS（不改动文件）
"""

import os, sys, json, subprocess, shutil, argparse, re
from pathlib import Path
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
REPO_DIR = os.path.join(HOME, "podcast-repo")
EPISODES_DIR = os.path.join(REPO_DIR, "episodes")
PODCAST_OUTPUT = os.path.join(HOME, "podcast_output")
POEMS_JSON = os.path.join(PODCAST_OUTPUT, "poems.json")
METADATA_JSON = os.path.join(REPO_DIR, "episodes.json")
RSS_PATH = os.path.join(REPO_DIR, "feed.xml")
ARTWORK_SRC = os.path.join(PODCAST_OUTPUT, "artwork.png")
ARTWORK_DST = os.path.join(REPO_DIR, "artwork.png")

# ── Podcast-level metadata ──
GITHUB_USER = "atlasgreat-cpu"
REPO_NAME = "classical-chinese-podcast"
PODCAST_TITLE = "Classical Chinese Poetry — 唐诗英韵"
PODCAST_DESC = "Bilingual recitations of Tang Dynasty masterpieces. Each episode features a poem in English and Chinese, with historical context and literary insight. 中英双语唐诗朗诵，探索千年诗韵。"
PODCAST_AUTHOR = "atlasgreat"
PODCAST_LANGUAGE = "en"
PODCAST_CATEGORY = "Arts"
PODCAST_SUBCATEGORY = "Books"
PODCAST_EXPLICIT = "no"
BASE_URL = f"https://{GITHUB_USER}.github.io/{REPO_NAME}"
EPISODES_URL = f"{BASE_URL}/episodes"
IMAGE_URL = f"{BASE_URL}/artwork.png"

os.makedirs(EPISODES_DIR, exist_ok=True)


def load_poems():
    """Load poems.json for author/era info."""
    path = POEMS_JSON
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "podcast_output", "poems.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_metadata():
    """Load user-editable episodes.json (titles, descriptions, episode numbers, publish dates)."""
    if os.path.exists(METADATA_JSON):
        with open(METADATA_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_metadata(data):
    with open(METADATA_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_duration(mp3_path):
    """Get audio duration in HH:MM:SS and seconds using ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", mp3_path],
            capture_output=True, text=True, timeout=15
        )
        secs = float(r.stdout.strip())
        h, m = divmod(int(secs), 3600)
        m, s = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}", int(secs)
    except Exception:
        return "00:00:00", 0


def get_file_size(mp3_path):
    return os.path.getsize(mp3_path)


def find_mp3(poem_name):
    """Find the MP3 file for a given poem name."""
    mp3_path = os.path.join(PODCAST_OUTPUT, f"{poem_name}_podcast.mp3")
    if os.path.exists(mp3_path):
        return mp3_path
    # Try fuzzy match
    for f in os.listdir(PODCAST_OUTPUT):
        if f.startswith(poem_name) and f.endswith("_podcast.mp3"):
            return os.path.join(PODCAST_OUTPUT, f)
    return None


def xml_escape(text):
    """Escape text for XML."""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))


def rfc2822(date_str):
    """Convert YYYY-MM-DD to RFC 2822 format."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%a, %d %b %Y 00:00:00 +0000")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def generate_rss():
    """Generate RSS feed from episodes.json metadata + MP3 files in episodes/."""
    metadata = load_metadata()
    poems = load_poems()

    # Collect episodes that have MP3 files
    episodes = []
    for poem_name, meta in metadata.items():
        mp3_name = f"{poem_name}_podcast.mp3"
        mp3_path = os.path.join(EPISODES_DIR, mp3_name)
        if not os.path.exists(mp3_path):
            continue

        duration_str, duration_secs = get_duration(mp3_path)
        file_size = get_file_size(mp3_path)
        pub_date = meta.get("published", datetime.now().strftime("%Y-%m-%d"))
        episode_num = meta.get("episode", len(episodes) + 1)

        # Get author from poems.json
        poem_data = poems.get(poem_name, {})
        author = poem_data.get("author", "")

        episodes.append({
            "poem_name": poem_name,
            "title": meta.get("title", poem_name),
            "description": meta.get("description", ""),
            "author": author,
            "pub_date": pub_date,
            "episode_num": episode_num,
            "duration": duration_str,
            "duration_secs": duration_secs,
            "file_size": file_size,
            "mp3_url": f"{EPISODES_URL}/{mp3_name}",
            "guid": f"{BASE_URL}/?ep={episode_num}",
        })

    # Sort by episode number
    episodes.sort(key=lambda e: e["episode_num"])

    # ── Build RSS XML ──
    now = rfc2822(datetime.now().strftime("%Y-%m-%d"))
    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom"
     version="2.0">
<channel>
  <title>{xml_escape(PODCAST_TITLE)}</title>
  <link>{BASE_URL}/</link>
  <description>{xml_escape(PODCAST_DESC)}</description>
  <language>{PODCAST_LANGUAGE}</language>
  <lastBuildDate>{now}</lastBuildDate>
  <pubDate>{now}</pubDate>
  <atom:link href="{BASE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
  <itunes:author>{xml_escape(PODCAST_AUTHOR)}</itunes:author>
  <itunes:summary>{xml_escape(PODCAST_DESC)}</itunes:summary>
  <itunes:image href="{IMAGE_URL}"/>
  <itunes:category text="{PODCAST_CATEGORY}">
    <itunes:category text="{PODCAST_SUBCATEGORY}"/>
  </itunes:category>
  <itunes:explicit>{PODCAST_EXPLICIT}</itunes:explicit>
  <itunes:type>episodic</itunes:type>
  <image>
    <url>{IMAGE_URL}</url>
    <title>{xml_escape(PODCAST_TITLE)}</title>
    <link>{BASE_URL}/</link>
  </image>
'''

    for ep in episodes:
        author_line = f" — {xml_escape(ep['author'])}" if ep['author'] else ""
        desc = xml_escape(ep['description'])
        rss += f'''  <item>
    <title>{xml_escape(ep['title'])}{author_line}</title>
    <description>{desc}</description>
    <content:encoded><![CDATA[{ep['description']}]]></content:encoded>
    <enclosure url="{ep['mp3_url']}" length="{ep['file_size']}" type="audio/mpeg"/>
    <guid isPermaLink="false">{ep['guid']}</guid>
    <pubDate>{rfc2822(ep['pub_date'])}</pubDate>
    <itunes:title>{xml_escape(ep['title'])}</itunes:title>
    <itunes:episode>{ep['episode_num']}</itunes:episode>
    <itunes:duration>{ep['duration']}</itunes:duration>
    <itunes:author>{xml_escape(PODCAST_AUTHOR)}</itunes:author>
    <itunes:summary>{desc}</itunes:summary>
    <itunes:image href="{IMAGE_URL}"/>
    <itunes:explicit>{PODCAST_EXPLICIT}</itunes:explicit>
  </item>
'''

    rss += '''</channel>
</rss>
'''
    return rss


def git_commit_push(message, files):
    """Commit changed files and push to GitHub."""
    os.chdir(REPO_DIR)
    for f in files:
        subprocess.run(["git", "add", f], check=True, capture_output=True)
    # Check if there's anything to commit
    r = subprocess.run(["git", "status", "--porcelain"] + files, capture_output=True, text=True)
    if not r.stdout.strip():
        print("  (no changes to commit)")
        return
    subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], check=True, capture_output=True)
    print(f"  ✓ committed & pushed: {message}")


def publish_one(poem_name, title=None, description=None):
    """Publish a single episode."""
    print(f"\n📻 Publishing: {poem_name}")

    # 1. Find MP3
    mp3_src = find_mp3(poem_name)
    if not mp3_src:
        print(f"  ✗ MP3 not found for '{poem_name}' in {PODCAST_OUTPUT}")
        return False
    print(f"  MP3: {mp3_src}")

    # 2. Copy to episodes/
    mp3_dst = os.path.join(EPISODES_DIR, f"{poem_name}_podcast.mp3")
    shutil.copy2(mp3_src, mp3_dst)
    print(f"  Copied to: {mp3_dst}")

    # 3. Get duration
    dur_str, dur_secs = get_duration(mp3_dst)
    print(f"  Duration: {dur_str}")

    # 4. Update episodes.json
    metadata = load_metadata()
    if poem_name not in metadata:
        metadata[poem_name] = {}

    if title:
        metadata[poem_name]["title"] = title
    elif "title" not in metadata[poem_name]:
        # Default: poem name
        metadata[poem_name]["title"] = poem_name

    if description:
        metadata[poem_name]["description"] = description
    elif "description" not in metadata[poem_name]:
        metadata[poem_name]["description"] = ""

    if "published" not in metadata[poem_name]:
        metadata[poem_name]["published"] = datetime.now().strftime("%Y-%m-%d")

    if "episode" not in metadata[poem_name]:
        # Auto-assign next episode number
        existing = [m.get("episode", 0) for m in metadata.values()]
        metadata[poem_name]["episode"] = max(existing) + 1 if existing else 1

    save_metadata(metadata)
    print(f"  Episode #{metadata[poem_name]['episode']}")

    # 5. Copy artwork if not already there
    if os.path.exists(ARTWORK_SRC) and not os.path.exists(ARTWORK_DST):
        shutil.copy2(ARTWORK_SRC, ARTWORK_DST)
        print(f"  Artwork copied")

    # 6. Regenerate RSS
    rss = generate_rss()
    with open(RSS_PATH, "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"  RSS generated: {RSS_PATH}")

    # 7. Git commit & push
    changed = [os.path.relpath(mp3_dst, REPO_DIR), "episodes.json", "feed.xml"]
    if os.path.exists(ARTWORK_DST):
        changed.append(os.path.relpath(ARTWORK_DST, REPO_DIR))
    git_commit_push(f"publish: {poem_name}", changed)

    print(f"  ✅ Published! RSS: {BASE_URL}/feed.xml")
    return True


def cmd_regenerate():
    """Regenerate RSS without adding files."""
    rss = generate_rss()
    with open(RSS_PATH, "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"RSS regenerated: {RSS_PATH}")
    git_commit_push("regenerate RSS feed", ["feed.xml"])


def cmd_list():
    """List all published episodes."""
    metadata = load_metadata()
    if not metadata:
        print("No episodes published yet.")
        return
    print(f"{'#':>3}  {'Episode':<6}  {'Poem':<20}  {'Published':>10}  {'Title'}")
    print("-" * 80)
    for name, meta in sorted(metadata.items(), key=lambda x: x[1].get("episode", 0)):
        ep = meta.get("episode", "?")
        pub = meta.get("published", "?")
        title = meta.get("title", name)[:40]
        print(f"{ep:>3}  #{ep:<5}  {name:<20}  {pub:>10}  {title}")


def main():
    parser = argparse.ArgumentParser(description="Publish podcast episodes to GitHub Pages RSS")
    parser.add_argument("poem", nargs="?", help="Poem name (Chinese characters)")
    parser.add_argument("--title", help="Episode title (your custom title)")
    parser.add_argument("--desc", "--description", dest="description", help="Episode description")
    parser.add_argument("--list", action="store_true", help="List published episodes")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate RSS feed only")
    args = parser.parse_args()

    if args.list:
        cmd_list()
    elif args.regenerate:
        cmd_regenerate()
    elif args.poem:
        publish_one(args.poem, args.title, args.description)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
