#!/usr/bin/env python3
"""JKAB Media Server - Index and stream metadata from /media/ directory"""

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
CACHE_DIR = Path.home() / ".cache" / "jkab"
PROGRESS_FILE = CACHE_DIR / "progress.toml"
PORT = 8080
HOST = "127.0.0.1"

# Supported video extensions
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v"}
POSTER_NAMES = {"poster.jpg", "cover.jpg", "fanart.jpg", "thumb.jpg"}

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

# Virtual top-level categories (not real directories under /media/)
CATEGORY_MOVIES = "Movies"
CATEGORY_SHOWS = "Shows"
CATEGORIES = (CATEGORY_MOVIES, CATEGORY_SHOWS)

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


def find_poster(media_dir: Path) -> Optional[str]:
    """Find poster image in media directory."""
    for poster_name in POSTER_NAMES:
        poster_path = media_dir / poster_name
        if poster_path.exists():
            return poster_name
    return None


def get_media_item(file_path: Path, rel_path: str) -> dict:
    """Build media item dict from file and adjacent .nfo."""
    nfo_path = file_path.with_suffix(".nfo")
    metadata = parse_nfo_file(nfo_path) if nfo_path.exists() else {}

    # Infer title from filename if not in .nfo
    if "title" not in metadata:
        metadata["title"] = file_path.stem

    # Find poster in same directory as video
    media_dir = file_path.parent
    poster = find_poster(media_dir)

    item = {
        "type": "video",
        "name": metadata.get("title", file_path.stem),
        "file": file_path.name,
        "path": rel_path,
        "metadata": metadata,
    }

    if poster:
        item["poster"] = poster

    return item


def _is_ignored(name: str) -> bool:
    """Skip dotfiles and Windows/macOS/FS metadata."""
    return name.startswith(".") or name in IGNORE_NAMES


def _folder_entry(directory: Path, rel_path: str) -> dict:
    """Build a folder item dict."""
    item = {
        "type": "folder",
        "name": directory.name,
        "path": rel_path,
    }
    poster = find_poster(directory)
    if poster:
        item["poster"] = poster
    return item


def _list_dir_items(directory: Path, rel_prefix: str) -> list:
    """List immediate folder/video children of a directory."""
    items = []
    try:
        for child in sorted(directory.iterdir()):
            if _is_ignored(child.name):
                continue
            rel = f"{rel_prefix}/{child.name}"
            if child.is_dir():
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


def index_root() -> dict:
    """Root view: two virtual categories."""
    return {
        "path": "root",
        "items": [
            {"type": "folder", "name": CATEGORY_MOVIES, "path": CATEGORY_MOVIES},
            {"type": "folder", "name": CATEGORY_SHOWS, "path": CATEGORY_SHOWS},
        ],
    }


def _dedupe(items: list) -> list:
    """Collapse duplicates across drives. First occurrence wins.

    Videos: keyed by lowercase filename stem, so the same physical file present
    on multiple drives surfaces once.
    Folders: keyed by lowercase folder name. Two ``Breaking Bad`` folders on
    different drives won't both appear; the second drive's contents are
    reachable by browsing into that drive directly via filesystem paths.
    """
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


def index_category(category: str) -> dict:
    """Merge contents across all drives for a virtual category.

    Rules per drive (immediate subdir of /media/):
      - Subfolder named 'Movies' (case-insensitive): contents flow to Movies tab
      - Subfolder named 'Shows'  (case-insensitive): contents flow to Shows tab
      - Any other subfolder: the folder itself is added to Shows tab
      - Loose video file at level 2: added as item to Shows tab

    Duplicates across drives are collapsed (see ``_dedupe``).
    """
    items = []
    for drive in list_drives():
        try:
            children = sorted(drive.iterdir())
        except Exception as e:
            logger.warning(f"Cannot read drive {drive}: {e}")
            continue

        for entry in children:
            if _is_ignored(entry.name):
                continue

            rel = f"{drive.name}/{entry.name}"

            if entry.is_file():
                if (
                    category == CATEGORY_SHOWS
                    and entry.suffix.lower() in VIDEO_EXTS
                ):
                    items.append(get_media_item(entry, rel))
                continue

            if not entry.is_dir():
                continue

            entry_lower = entry.name.lower()
            if entry_lower == CATEGORY_MOVIES.lower():
                if category == CATEGORY_MOVIES:
                    items.extend(_list_dir_items(entry, rel))
            elif entry_lower == CATEGORY_SHOWS.lower():
                if category == CATEGORY_SHOWS:
                    items.extend(_list_dir_items(entry, rel))
            else:
                if category == CATEGORY_SHOWS:
                    items.append(_folder_entry(entry, rel))

    return {"path": category, "items": _dedupe(items)}


def index_path(rel_path: str) -> Optional[dict]:
    """List a real filesystem path under /media/ (e.g. 'sample/Movies')."""
    current = MEDIA_ROOT / rel_path
    try:
        if not current.resolve().is_relative_to(MEDIA_ROOT.resolve()):
            return None
    except (OSError, ValueError):
        return None
    if not current.exists() or not current.is_dir():
        return None
    return {
        "path": rel_path,
        "items": _list_dir_items(current, rel_path),
    }


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
    """Get directory listing with metadata.

    Root returns two virtual categories (Movies, Shows). The category paths
    aggregate matching content across every drive under /media/. Any deeper
    path resolves to a real filesystem location.
    """
    try:
        if path == "":
            return jsonify(index_root())
        if path in CATEGORIES:
            return jsonify(index_category(path))

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

    logger.info(f"Starting JKAB Media Server on {HOST}:{PORT}")
    logger.info(f"Serving media from {MEDIA_ROOT}")

    # Run Flask in production mode (no debug, no reloader)
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
