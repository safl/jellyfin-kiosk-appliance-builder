#!/usr/bin/env python3
"""Tellybox Media Server - Index and stream metadata from /media/ directory"""

import json
import logging
import mimetypes
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, send_file, request
from werkzeug.exceptions import NotFound

# Configuration
MEDIA_ROOT = Path("/media")
CACHE_DIR = Path.home() / ".cache" / "tellybox"
PROGRESS_FILE = CACHE_DIR / "progress.toml"
PORT = 8080
HOST = "127.0.0.1"

# Supported video extensions
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v"}

# Generic poster filenames (preference order: portrait first, landscape last).
GENERIC_POSTER_NAMES = ("poster.jpg", "cover.jpg", "thumb.jpg", "fanart.jpg")

# Suffixes appended to a video stem in the Kodi MovieFolder convention.
KODI_POSTER_SUFFIXES = ("-poster.jpg", "-thumb.jpg", "-landscape.jpg", "-fanart.jpg")

# Filesystem entries to skip (Windows/macOS metadata, FS metadata, etc.)
IGNORE_NAMES = {
    "System Volume Information",
    "$RECYCLE.BIN",
    "RECYCLER",
    "FOUND.000",
    "lost+found",
    ".Trashes",
    ".Spotlight-V100",
    ".fseventsd",
    "@eaDir",
}

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CACHE_DIR.mkdir(parents=True, exist_ok=True)


# --- Metadata parsing ---


def parse_nfo_file(nfo_path: Path) -> dict:
    """Parse KODI-format .nfo XML file and extract metadata."""
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        metadata = {}

        # Common fields
        for field in ["title", "plot", "year", "runtime"]:
            elem = root.find(field)
            if elem is not None and elem.text:
                if field == "year":
                    metadata[field] = int(elem.text) if elem.text.isdigit() else None
                elif field == "runtime":
                    # Runtime can be in minutes or seconds, usually minutes
                    try:
                        metadata[field] = int(elem.text)
                    except ValueError:
                        metadata[field] = None
                else:
                    metadata[field] = elem.text

        # Rating (community rating)
        rating_elem = root.find("rating")
        if rating_elem is not None and rating_elem.text:
            try:
                metadata["rating"] = float(rating_elem.text)
            except ValueError:
                pass

        # Genres
        genres = []
        for genre_elem in root.findall("genre"):
            if genre_elem.text:
                genres.append(genre_elem.text)
        if genres:
            metadata["genres"] = genres

        # For episodes: season, episode number
        season_elem = root.find("season")
        episode_elem = root.find("episode")
        if season_elem is not None and season_elem.text:
            try:
                metadata["season"] = int(season_elem.text)
            except ValueError:
                pass
        if episode_elem is not None and episode_elem.text:
            try:
                metadata["episode"] = int(episode_elem.text)
            except ValueError:
                pass

        return metadata
    except Exception as e:
        logger.warning(f"Failed to parse {nfo_path}: {e}")
        return {}


def find_poster_for_video(video_path: Path) -> Optional[str]:
    """Find a poster for a single video file.

    Tries Kodi MovieFolder names (``MyMovie-poster.jpg`` next to ``MyMovie.mp4``)
    first, then generic names in the same directory.
    """
    parent = video_path.parent
    stem = video_path.stem
    for suffix in KODI_POSTER_SUFFIXES:
        candidate = parent / f"{stem}{suffix}"
        if candidate.exists():
            return candidate.name
    for name in GENERIC_POSTER_NAMES:
        candidate = parent / name
        if candidate.exists():
            return name
    return None


def find_poster(media_dir: Path) -> Optional[str]:
    """Find a poster representing a folder.

    Prefers generic names (poster.jpg, cover.jpg, ...). Falls back to a
    Kodi-style poster keyed off the first video file in the directory, so
    movie folders that only ship ``MovieTitle-poster.jpg`` still work.
    """
    for name in GENERIC_POSTER_NAMES:
        if (media_dir / name).exists():
            return name
    try:
        for entry in sorted(media_dir.iterdir()):
            if entry.is_file() and entry.suffix.lower() in VIDEO_EXTS:
                poster = find_poster_for_video(entry)
                if poster:
                    return poster
                break
    except Exception:
        pass
    return None


def get_media_item(file_path: Path, rel_path: str, display_name: Optional[str] = None) -> dict:
    """Build media item dict from file and adjacent .nfo. ``poster`` is a
    full relative path. ``display_name`` overrides the inferred title (used
    when collapsing a movie folder so the folder name surfaces in the grid).
    """
    nfo_path = file_path.with_suffix(".nfo")
    metadata = parse_nfo_file(nfo_path) if nfo_path.exists() else {}

    if "title" not in metadata:
        metadata["title"] = file_path.stem

    poster = find_poster_for_video(file_path)
    name = display_name or metadata.get("title", file_path.stem)

    item = {
        "type": "video",
        "name": name,
        "file": file_path.name,
        "path": rel_path,
        "metadata": metadata,
    }

    rel_dir = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    if poster:
        item["poster"] = f"{rel_dir}/{poster}" if rel_dir else poster

    return item


def _is_ignored(name: str) -> bool:
    """Skip dotfiles and Windows/macOS/FS metadata."""
    return name.startswith(".") or name in IGNORE_NAMES


def _folder_entry(directory: Path, rel_path: str) -> dict:
    """Build a folder item dict. ``poster`` is a full relative path."""
    item = {
        "type": "folder",
        "name": directory.name,
        "path": rel_path,
    }
    poster = find_poster(directory)
    if poster:
        item["poster"] = f"{rel_path}/{poster}"
    return item


def _single_video_in(directory: Path) -> Optional[Path]:
    """Return the only video file directly in ``directory`` if it has exactly
    one video and zero non-ignored subdirectories. Used to collapse Kodi-style
    movie folders into a single playable item."""
    videos = []
    try:
        for child in directory.iterdir():
            if _is_ignored(child.name):
                continue
            if child.is_dir():
                return None
            if child.is_file() and child.suffix.lower() in VIDEO_EXTS:
                videos.append(child)
                if len(videos) > 1:
                    return None
    except Exception:
        return None
    return videos[0] if len(videos) == 1 else None


def _list_dir_items(directory: Path, rel_prefix: str) -> list:
    """List immediate folder/video children of a directory.

    Collapses Kodi-style movie folders (one video, no subdirs) into a single
    video item so the user reaches Play in two clicks instead of three.
    """
    items = []
    try:
        for child in sorted(directory.iterdir()):
            if _is_ignored(child.name):
                continue
            rel = f"{rel_prefix}/{child.name}"
            if child.is_dir():
                video = _single_video_in(child)
                if video is not None:
                    items.append(get_media_item(
                        video, f"{rel}/{video.name}", display_name=child.name
                    ))
                else:
                    items.append(_folder_entry(child, rel))
            elif child.is_file() and child.suffix.lower() in VIDEO_EXTS:
                items.append(get_media_item(child, rel))
    except Exception as e:
        logger.error(f"Error listing {directory}: {e}")
    return items


def list_drives() -> list:
    """Return immediate subdirectories of /media/ (skip junk, dotfiles)."""
    if not MEDIA_ROOT.exists():
        return []
    try:
        return [
            d for d in sorted(MEDIA_ROOT.iterdir())
            if d.is_dir() and not _is_ignored(d.name)
        ]
    except Exception as e:
        logger.error(f"Error listing drives: {e}")
        return []


def _collection_sort_key(name: str) -> tuple:
    """Custom-then-Shows-then-Movies ordering for the tab bar.

    Custom collections (Yoga, Documentaries, Concerts, ...) come first
    alphabetically, then Shows, then Movies — keeping the highest-traffic
    collections at the right edge for fast access.
    """
    lower = name.lower()
    if lower == "movies":
        rank = 2
    elif lower == "shows":
        rank = 1
    else:
        rank = 0
    return (rank, lower)


def discover_collections() -> list:
    """Find all unique 2nd-level folder names across every drive.

    Each unique name is a Collection — e.g. ``Movies``, ``Shows``, ``Yoga``.
    Names are case-folded for comparison; the first-seen casing wins as the
    display name. Sorted: custom collections first (alphabetically), then
    Shows, then Movies.
    """
    seen: dict = {}
    for drive in list_drives():
        try:
            children = sorted(drive.iterdir())
        except Exception as e:
            logger.warning(f"Cannot read drive {drive}: {e}")
            continue
        for entry in children:
            if not entry.is_dir() or _is_ignored(entry.name):
                continue
            key = entry.name.lower()
            if key not in seen:
                seen[key] = entry.name
    return sorted(seen.values(), key=_collection_sort_key)


def index_root() -> dict:
    """Root view: one folder entry per Collection."""
    return {
        "path": "root",
        "items": [
            {"type": "folder", "name": name, "path": name}
            for name in discover_collections()
        ],
    }


def _dedupe(items: list) -> list:
    """Collapse duplicates across drives. First occurrence wins."""
    seen: set = set()
    result = []
    for item in items:
        if item.get("type") == "video":
            stem = Path(item.get("file", "")).stem.lower()
            key = ("v", stem)
        else:
            key = ("f", item.get("name", "").lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def index_collection(collection: str) -> Optional[dict]:
    """Merge contents of every ``/media/*/<collection>/`` across drives.

    Match is case-insensitive on the collection name. Returns None if no
    drive contains a matching subfolder (the collection no longer exists).
    """
    target = collection.lower()
    items = []
    matched = False
    for drive in list_drives():
        try:
            children = drive.iterdir()
        except Exception as e:
            logger.warning(f"Cannot read drive {drive}: {e}")
            continue
        for entry in children:
            if not entry.is_dir() or _is_ignored(entry.name):
                continue
            if entry.name.lower() != target:
                continue
            matched = True
            rel_prefix = f"{drive.name}/{entry.name}"
            items.extend(_list_dir_items(entry, rel_prefix))

    if not matched:
        return None

    items.sort(key=lambda it: it.get("name", "").lower())
    return {"path": collection, "items": _dedupe(items)}


def index_path(rel_path: str) -> Optional[dict]:
    """List a real filesystem path under /media/ (e.g. 'sample/Movies').

    Adds ``view_hint = "list"`` when the directory is a TV show root
    (Kodi convention: contains ``tvshow.nfo``). The player uses this to
    pick a vertical episode list rather than the poster grid for season
    listings — keeps Columbo and Turtles consistent.
    """
    current = MEDIA_ROOT / rel_path
    try:
        if not current.resolve().is_relative_to(MEDIA_ROOT.resolve()):
            return None
    except (OSError, ValueError):
        return None
    if not current.exists() or not current.is_dir():
        return None
    response = {
        "path": rel_path,
        "items": _list_dir_items(current, rel_path),
    }
    if (current / "tvshow.nfo").exists():
        response["view_hint"] = "list"
    return response


# --- Progress tracking ---


def load_progress() -> dict:
    """Load progress data from TOML file."""
    if not PROGRESS_FILE.exists():
        return {}

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    try:
        with open(PROGRESS_FILE, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        logger.warning(f"Failed to load progress: {e}")
        return {}


def save_progress(data: dict):
    """Save progress data to TOML file."""
    try:
        import tomli_w
    except ImportError:
        # Fallback: write minimal TOML manually if tomli_w not available
        try:
            with open(PROGRESS_FILE, "w") as f:
                for key, value in data.items():
                    # Escape key for TOML
                    key_safe = key.replace('"', '\\"')
                    f.write(f'"{key_safe}" = {json.dumps(value)}\n')
            return
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
            return

    try:
        with open(PROGRESS_FILE, "wb") as f:
            tomli_w.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save progress: {e}")


# --- Flask routes ---


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/api/media", defaults={"path": ""}, methods=["GET"])
@app.route("/api/media/<path:path>", methods=["GET"])
def get_media(path: str):
    """Get a Media Library listing.

    Root returns one entry per Collection — derived from the unique
    second-level folder names found across every drive under /media/. A
    single-segment path (no slash) resolves as a Collection and aggregates
    matching content across drives. Deeper paths resolve to real filesystem
    locations.
    """
    try:
        if path == "":
            return jsonify(index_root())

        if "/" not in path:
            collection = index_collection(path)
            if collection is not None:
                return jsonify(collection)

        result = index_path(path)
        if result is None:
            raise NotFound(f"Path not found: {path}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting media: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/stream/<path:path>", methods=["GET"])
def stream_video(path: str):
    """Stream video file with range request support."""
    try:
        file_path = MEDIA_ROOT / path

        # Security: ensure path is within MEDIA_ROOT
        if not file_path.resolve().is_relative_to(MEDIA_ROOT.resolve()):
            raise NotFound("Invalid path")

        if not file_path.exists() or not file_path.is_file():
            raise NotFound(f"File not found: {path}")

        # Check if it's a video file
        if file_path.suffix.lower() not in VIDEO_EXTS:
            raise NotFound(f"Not a video file: {path}")

        # Use Flask's send_file which supports range requests
        return send_file(
            file_path,
            mimetype=mimetypes.guess_type(str(file_path))[0] or "video/mp4",
            as_attachment=False,
            download_name=file_path.name,
        )
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error streaming video: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/progress/<path:path>", methods=["GET"])
def get_progress(path: str):
    """Get watch progress for a video."""
    try:
        progress_data = load_progress()
        video_progress = progress_data.get(path)

        if video_progress:
            return jsonify(video_progress)
        else:
            return jsonify({}), 404
    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/progress", methods=["POST"])
def save_watch_progress():
    """Save watch progress for a video."""
    try:
        data = request.get_json()
        path = data.get("path")
        position = data.get("position")
        duration = data.get("duration")

        if not path:
            return jsonify({"error": "Missing path"}), 400

        progress_data = load_progress()
        progress_data[path] = {
            "position": position,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
        }
        save_progress(progress_data)

        return jsonify({"status": "saved"}), 200
    except Exception as e:
        logger.error(f"Error saving progress: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/image/<path:path>", methods=["GET"])
def get_image(path: str):
    """Serve image files from /media/."""
    try:
        file_path = MEDIA_ROOT / path

        # Security: ensure path is within MEDIA_ROOT
        if not file_path.resolve().is_relative_to(MEDIA_ROOT.resolve()):
            raise NotFound("Invalid path")

        if not file_path.exists() or not file_path.is_file():
            raise NotFound(f"Image not found: {path}")

        # Only allow image files
        if not file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            raise NotFound(f"Not an image file: {path}")

        return send_file(
            file_path,
            mimetype=mimetypes.guess_type(str(file_path))[0] or "image/jpeg",
            as_attachment=False,
        )
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error getting image: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Check that /media/ exists
    if not MEDIA_ROOT.exists():
        logger.error(f"{MEDIA_ROOT} does not exist")
        sys.exit(1)

    logger.info(f"Starting Tellybox Media Server on {HOST}:{PORT}")
    logger.info(f"Serving media from {MEDIA_ROOT}")

    # Run Flask in production mode (no debug, no reloader)
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
