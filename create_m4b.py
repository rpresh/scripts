#!/usr/bin/env python3
"""Combine an exported audiobook folder (Part NNN.mp3 files + metadata/metadata.json
+ metadata/cover.*) into a single chaptered .m4b file, using ffmpeg/ffprobe."""

import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PART_RE = re.compile(r"^Part (\d+)\.mp3$")


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def find_cover(metadata_dir):
    covers = sorted(p for p in metadata_dir.iterdir() if p.stem.lower() == "cover" and p.is_file())
    if len(covers) != 1:
        fail(f"expected exactly one 'cover.*' file in {metadata_dir}, found {len(covers)}")
    return covers[0]


def load_metadata(folder):
    metadata_dir = folder / "metadata"
    metadata_path = metadata_dir / "metadata.json"
    if not metadata_path.is_file():
        fail(f"{metadata_path} not found")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    cover = find_cover(metadata_dir)
    return metadata, cover


def find_parts(folder, spine_len):
    parts = {}
    for p in folder.iterdir():
        m = PART_RE.match(p.name)
        if m:
            parts[int(m.group(1))] = p
    if not parts:
        fail(f"no 'Part NNN.mp3' files found in {folder}")
    numbers = sorted(parts)
    if numbers != list(range(1, len(numbers) + 1)):
        fail(f"part numbering is not contiguous starting at 1: {numbers}")
    if len(numbers) != spine_len:
        fail(f"found {len(numbers)} part files but metadata.json spine has {spine_len} entries")
    return [parts[n] for n in numbers]


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def build_chapters(metadata, cumulative, total_duration):
    spine_len = len(metadata["spine"])
    chapters = sorted(metadata["chapters"], key=lambda c: (c["spine"], c["offset"]))

    # Validate non-decreasing offsets within each spine file (mirrors bakeMetadata.py).
    by_spine = {}
    for c in chapters:
        by_spine.setdefault(c["spine"], []).append(c)
    for spine_index, chaps in by_spine.items():
        if spine_index < 0 or spine_index >= spine_len:
            fail(f"chapter '{chaps[0]['title']}' references out-of-range spine index {spine_index}")
        prev = None
        for c in chaps:
            if prev is not None and c["offset"] <= prev:
                fail(f"overlapping/non-increasing chapter offsets at spine {spine_index} "
                     f"(chapter '{c['title']}' offset {c['offset']} <= previous {prev})")
            prev = c["offset"]

    result = []
    for i, c in enumerate(chapters):
        start = cumulative[c["spine"]] + c["offset"]
        if i + 1 < len(chapters):
            nxt = chapters[i + 1]
            end = cumulative[nxt["spine"]] + nxt["offset"]
        else:
            end = total_duration
        result.append({"title": c["title"], "start": start, "end": end})
    return result


def strip_html(text):
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def escape_ffmetadata(value):
    value = value.replace("\\", "\\\\")
    for ch in ("=", ";", "#", "\n"):
        value = value.replace(ch, "\\" + ch)
    return value


def write_concat_list(parts, fh):
    for p in parts:
        escaped = str(p.resolve()).replace("'", "'\\''")
        fh.write(f"file '{escaped}'\n")


def write_ffmetadata(metadata, chapters, description, fh):
    authors = [c["name"] for c in metadata.get("creator", []) if c.get("role") == "author"]
    narrators = [c["name"] for c in metadata.get("creator", []) if c.get("role") == "narrator"]

    fh.write(";FFMETADATA1\n")
    fh.write(f"title={escape_ffmetadata(metadata['title'])}\n")
    fh.write(f"album={escape_ffmetadata(metadata['title'])}\n")
    if authors:
        author_str = ", ".join(authors)
        fh.write(f"artist={escape_ffmetadata(author_str)}\n")
        fh.write(f"album_artist={escape_ffmetadata(author_str)}\n")
    if narrators:
        fh.write(f"composer={escape_ffmetadata('; '.join(narrators))}\n")
    fh.write("genre=Audiobook\n")
    if description:
        fh.write(f"comment={escape_ffmetadata(description)}\n")
    fh.write("\n")

    for c in chapters:
        fh.write("[CHAPTER]\n")
        fh.write("TIMEBASE=1/1000\n")
        fh.write(f"START={round(c['start'] * 1000)}\n")
        fh.write(f"END={round(c['end'] * 1000)}\n")
        fh.write(f"title={escape_ffmetadata(c['title'])}\n\n")


def run_ffmpeg(concat_path, ffmetadata_path, cover_path, bitrate, output_path):
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_path),
        "-i", str(ffmetadata_path),
        "-i", str(cover_path),
        "-map_metadata", "1",
        "-map", "0:a",
        "-map", "2:v",
        "-c:a", "aac", "-b:a", bitrate, "-ar", "44100",
        "-c:v", "copy", "-disposition:v:0", "attached_pic",
        "-metadata:s:v", "title=Album cover",
        "-metadata:s:v", "comment=Cover (front)",
        "-movflags", "+faststart",
        "-f", "ipod",
        str(output_path),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="audiobook folder (contains Part NNN.mp3 + metadata/)")
    parser.add_argument("-o", "--output", type=Path, default=None,
                         help="output .m4b path (default: <folder>.m4b next to the folder)")
    parser.add_argument("-b", "--bitrate", default="64k", help="AAC audio bitrate (default: 64k)")
    parser.add_argument("--force", action="store_true", help="overwrite output file if it exists")
    args = parser.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        fail(f"{folder} is not a directory")

    output_path = args.output.resolve() if args.output else folder.parent / f"{folder.name}.m4b"
    if output_path.exists() and not args.force:
        fail(f"{output_path} already exists (use --force to overwrite)")

    metadata, cover = load_metadata(folder)
    parts = find_parts(folder, len(metadata["spine"]))

    print(f"Book: {metadata['title']} ({len(parts)} parts)")
    print("Probing part durations...")
    durations = [ffprobe_duration(p) for p in parts]

    cumulative = [0.0]
    for d in durations[:-1]:
        cumulative.append(cumulative[-1] + d)
    total_duration = cumulative[-1] + durations[-1]

    chapters = build_chapters(metadata, cumulative, total_duration)
    print(f"Computed {len(chapters)} chapters, total duration {total_duration / 3600:.2f}h")

    description = ""
    desc = metadata.get("description", {})
    if isinstance(desc, dict) and desc.get("short"):
        description = strip_html(desc["short"])

    with tempfile.TemporaryDirectory() as tmp:
        concat_path = Path(tmp) / "concat.txt"
        ffmetadata_path = Path(tmp) / "ffmetadata.txt"

        with open(concat_path, "w", encoding="utf-8") as fh:
            write_concat_list(parts, fh)
        with open(ffmetadata_path, "w", encoding="utf-8") as fh:
            write_ffmetadata(metadata, chapters, description, fh)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        run_ffmpeg(concat_path, ffmetadata_path, cover, args.bitrate, output_path)

    print(f"Done: {output_path}")


if __name__ == "__main__":
    main()
