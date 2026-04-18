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


def index_media(base_path: Path, rel_path: str = "") -> Optional[dict]:
    """Recursively index media directory."""
    current_path = base_path / rel_path if rel_path else base_path

    if not current_path.exists() or not current_path.is_dir():
        return None

    items = []

    try:
        for entry in sorted(current_path.iterdir()):
            # Skip hidden files
            if entry.name.startswith("."):
                continue

            rel = str(entry.relative_to(base_path)) if rel_path == "" else f"{rel_path}/{entry.name}"

            if entry.is_dir():
                # Folder
                items.append({
                    "type": "folder",
                    "name": entry.name,
                    "path": rel,
                    "poster": find_poster(entry),
                })
            elif entry.is_file() and entry.suffix.lower() in VIDEO_EXTS:
                # Video file
                items.append(get_media_item(entry, rel))
    except Exception as e:
        logger.error(f"Error indexing {current_path}: {e}")

    return {
        "path": rel_path if rel_path else "root",
        "items": items,
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
    """Get directory listing with metadata."""
    try:
        result = index_media(MEDIA_ROOT, path)
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
