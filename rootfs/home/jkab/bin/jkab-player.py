#!/usr/bin/env python3
"""JKAB Player - Netflix-style grid UI for media browsing and playback"""

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import pygame
import urllib.request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JKAB_VERSION = "v0.7.0"

# Configuration
SERVER_URL = "http://localhost:8080"
STREAM_BASE = f"{SERVER_URL}/stream"
IMAGE_BASE = f"{SERVER_URL}/image"


# --- View States ---


class ViewState(Enum):
    MAIN_MENU = "main_menu"
    GRID = "grid"
    DETAILS = "details"
    LIST = "list"
    PLAYING = "playing"


# --- API Client ---


class MediaServerAPI:
    """Client for jkab-server API."""

    def __init__(self, server_url: str = SERVER_URL):
        self.server = server_url
        self.cache = {}

    def get_media(self, path: str = "") -> Optional[dict]:
        """Get media listing for a path."""
        try:
            url = f"{self.server}/api/media" + (f"/{path}" if path else "")
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            self.cache[path] = data
            return data
        except Exception as e:
            logger.error(f"Failed to get media {path}: {e}")
            # Return cached data if available
            return self.cache.get(path)

    def get_stream_url(self, media_path: str) -> str:
        """Get stream URL for a video."""
        return f"{STREAM_BASE}/{media_path}"

    def get_image_url(self, image_path: str) -> str:
        """Get image URL."""
        return f"{IMAGE_BASE}/{image_path}"

    def save_progress(self, media_path: str, position: int, duration: int):
        """Save watch progress."""
        try:
            url = f"{self.server}/api/progress"
            data = {
                "path": media_path,
                "position": position,
                "duration": duration,
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as e:
            logger.warning(f"Failed to save progress: {e}")


# --- Navigation Stack ---


@dataclass
class ViewContext:
    state: ViewState
    data: dict = field(default_factory=dict)
    selected_index: int = 0


class NavigationStack:
    """Manage navigation history."""

    def __init__(self):
        self.stack = [ViewContext(ViewState.MAIN_MENU)]

    def push(self, state: ViewState, data: dict = None):
        """Push a new view state."""
        self.stack.append(ViewContext(state, data or {}, 0))

    def pop(self) -> bool:
        """Pop to previous state. Returns False if at root."""
        if len(self.stack) > 1:
            self.stack.pop()
            return True
        return False

    def current(self) -> ViewContext:
        """Get current view context."""
        return self.stack[-1]

    def update_selected(self, index: int):
        """Update selected index in current view."""
        self.current().selected_index = index


# --- UI Rendering ---


class UIRenderer:
    """Pygame UI rendering."""

    # Colors (Netflix-inspired)
    BG = (0, 0, 0)  # Pure black
    TEXT = (255, 255, 255)  # Pure white
    SELECT = (255, 255, 255)  # White border
    DIM = (100, 100, 100)  # Dimmed gray
    ACCENT = (229, 9, 20)  # Netflix red (optional)

    def __init__(self):
        pygame.init()
        pygame.mouse.set_visible(False)

        info = pygame.display.Info()
        self.width = info.current_w
        self.height = info.current_h
        self.screen = pygame.display.set_mode(
            (self.width, self.height), pygame.FULLSCREEN
        )
        pygame.display.set_caption("JKAB Player")

        # Scale factor relative to 1080p
        s = max(1, self.height / 1080)

        # Find best available font (try in order of preference)
        font_name = None
        for candidate in ["dejavusans", "liberationsans", "notosans", "ubuntu", "sans"]:
            if pygame.font.match_font(candidate):
                font_name = candidate
                break

        self.font_title = pygame.font.SysFont(font_name, int(40 * s), bold=True)
        self.font_big = pygame.font.SysFont(font_name, int(32 * s), bold=True)
        self.font = pygame.font.SysFont(font_name, int(24 * s))
        self.font_small = pygame.font.SysFont(font_name, int(18 * s))

        # Grid layout
        self.grid_cols = max(5, int(self.width / 350))
        self.poster_h = int(self.height / 3.5)
        self.poster_w = int(self.poster_h * 0.667)  # 2:3 aspect ratio
        self.grid_gap = int(16 * s)
        self.grid_h = int(100 * s)

        # Image cache
        self.image_cache = {}

    def show_message(self, text: str):
        """Show loading/status message."""
        self.screen.fill(self.BG)
        surf = self.font.render(text, True, self.DIM)
        rect = surf.get_rect(center=(self.width // 2, self.height // 2))
        self.screen.blit(surf, rect)
        pygame.display.flip()

    def _load_image(self, image_url: str) -> Optional[pygame.Surface]:
        """Load image from URL with caching."""
        if image_url in self.image_cache:
            return self.image_cache[image_url]

        try:
            req = urllib.request.Request(image_url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                img_data = resp.read()
            import io

            surf = pygame.image.load(io.BytesIO(img_data))
            self.image_cache[image_url] = surf
            return surf
        except Exception as e:
            logger.debug(f"Failed to load image {image_url}: {e}")
            return None

    def render_grid(
        self,
        title: str,
        items: list,
        selected: int,
        api: MediaServerAPI,
        tabs: Optional[list] = None,
        selected_tab: int = 0,
    ):
        """Render grid of items (posters), with optional Collections tab bar."""
        self.screen.fill(self.BG)

        s = max(1, self.height / 1080)
        title_h = int(60 * s)

        if tabs:
            self._render_tab_bar(tabs, selected_tab, title_h)
        else:
            title_surf = self.font_title.render(title, True, self.TEXT)
            self.screen.blit(title_surf, (40, (title_h - title_surf.get_height()) // 2))

        start_y = title_h + 40
        grid_x_start = 40
        cols = self.grid_cols
        poster_w = self.poster_w
        poster_h = self.poster_h
        gap = self.grid_gap

        # Calculate rows needed
        rows = (len(items) + cols - 1) // cols

        # Render posters
        for i, item in enumerate(items):
            row = i // cols
            col = i % cols

            x = grid_x_start + col * (poster_w + gap)
            y = start_y + row * (poster_h + gap + 30)  # Extra space for title

            # Load poster image
            poster_img = None
            if "poster" in item:
                parent_path = (
                    item.get("path", "").rsplit("/", 1)[0]
                    if "/" in item.get("path", "")
                    else ""
                )
                if parent_path:
                    image_url = api.get_image_url(f"{parent_path}/{item['poster']}")
                else:
                    image_url = api.get_image_url(item["poster"])
                poster_img = self._load_image(image_url)

            # Draw poster background or placeholder
            if poster_img:
                scaled = pygame.transform.smoothscale(poster_img, (poster_w, poster_h))
                self.screen.blit(scaled, (x, y))
            else:
                pygame.draw.rect(
                    self.screen, self.DIM, (x, y, poster_w, poster_h), border_radius=4
                )
                # Add title text on placeholder
                title_text = item.get("name", "?")[:16]
                title_surf = self.font_small.render(title_text, True, self.TEXT)
                text_rect = title_surf.get_rect(center=(x + poster_w // 2, y + poster_h // 2))
                self.screen.blit(title_surf, text_rect)

            # Draw selection border
            if i == selected:
                pygame.draw.rect(
                    self.screen,
                    self.SELECT,
                    (x - 2, y - 2, poster_w + 4, poster_h + 4),
                    width=3,
                    border_radius=4,
                )

            # Draw title below poster
            title_text = item.get("name", "?")[:20]  # Truncate long titles
            title_surf = self.font_small.render(title_text, True, self.TEXT)
            self.screen.blit(title_surf, (x, y + poster_h + 8))

        self._render_hint_bar(
            "↑↓←→ Navigate   Enter Select   Esc Back   R Reload   [/] Tabs"
        )

        pygame.display.flip()

    def _render_tab_bar(self, tabs: list, selected_tab: int, height: int):
        """Draw a horizontal Collections tab bar at the top."""
        s = max(1, self.height / 1080)
        pygame.draw.rect(self.screen, (15, 15, 15), (0, 0, self.width, height))

        pad = int(28 * s)
        gap = int(20 * s)
        x = pad
        y_text = (height - self.font.get_height()) // 2
        for i, name in enumerate(tabs):
            label = name
            label_surf = self.font.render(label, True, self.TEXT if i == selected_tab else self.DIM)
            label_w = label_surf.get_width()
            if i == selected_tab:
                underline_y = height - int(6 * s)
                pygame.draw.rect(
                    self.screen,
                    self.ACCENT,
                    (x, underline_y, label_w, int(4 * s)),
                )
            self.screen.blit(label_surf, (x, y_text))
            x += label_w + gap

        lib_surf = self.font_small.render("Media Library", True, self.DIM)
        self.screen.blit(
            lib_surf,
            (self.width - lib_surf.get_width() - pad, (height - lib_surf.get_height()) // 2),
        )

    def _render_hint_bar(self, hint_text: str):
        """Draw the bottom hint bar with the JKAB version anchored bottom-right."""
        hint_bar_h = 50
        pygame.draw.rect(
            self.screen, (20, 20, 20), (0, self.height - hint_bar_h, self.width, hint_bar_h)
        )
        hint_surf = self.font_small.render(hint_text, True, self.DIM)
        self.screen.blit(hint_surf, (40, self.height - hint_bar_h + 12))
        ver_surf = self.font_small.render(f"JKAB {JKAB_VERSION}", True, self.DIM)
        self.screen.blit(
            ver_surf,
            (self.width - ver_surf.get_width() - 20, self.height - hint_bar_h + 12),
        )

    def render_details(self, item: dict, api: MediaServerAPI, action_text: str = "Play"):
        """Render item details (poster + metadata)."""
        self.screen.fill(self.BG)

        # Load poster
        poster_img = None
        if "poster" in item:
            parent_path = (
                item.get("path", "").rsplit("/", 1)[0]
                if "/" in item.get("path", "")
                else ""
            )
            if parent_path:
                image_url = api.get_image_url(f"{parent_path}/{item['poster']}")
            else:
                image_url = api.get_image_url(item["poster"])
            poster_img = self._load_image(image_url)

        # Poster on left (60% width)
        poster_w = int(self.width * 0.3)
        poster_h = int(poster_w * 1.5)
        poster_x = 60
        poster_y = 80

        if poster_img:
            scaled = pygame.transform.smoothscale(poster_img, (poster_w, poster_h))
            self.screen.blit(scaled, (poster_x, poster_y))
        else:
            pygame.draw.rect(
                self.screen, self.DIM, (poster_x, poster_y, poster_w, poster_h)
            )
            # Add title text on placeholder
            title = item.get("name", "?")[:20]
            title_surf = self.font.render(title, True, self.TEXT)
            text_rect = title_surf.get_rect(center=(poster_x + poster_w // 2, poster_y + poster_h // 2))
            self.screen.blit(title_surf, text_rect)

        # Metadata on right
        meta_x = poster_x + poster_w + 60
        meta_y = poster_y
        meta_w = self.width - meta_x - 40

        metadata = item.get("metadata", {})

        # Title
        title = item.get("name", "?")
        title_surf = self.font_big.render(title, True, self.TEXT)
        self.screen.blit(title_surf, (meta_x, meta_y))
        meta_y += title_surf.get_height() + 20

        # Year / Type / Runtime
        info_parts = []
        if metadata.get("year"):
            info_parts.append(str(metadata["year"]))
        if item.get("type") == "folder":
            info_parts.append("Collection")
        elif metadata.get("season"):
            info_parts.append(f"S{metadata['season']:02d}E{metadata.get('episode', 0):02d}")
        if metadata.get("runtime"):
            info_parts.append(f"{metadata['runtime']} min")

        if info_parts:
            info_text = " · ".join(info_parts)
            info_surf = self.font_small.render(info_text, True, self.DIM)
            self.screen.blit(info_surf, (meta_x, meta_y))
            meta_y += info_surf.get_height() + 12

        # Rating
        if metadata.get("rating"):
            rating_text = f"★ {metadata['rating']:.1f}"
            rating_surf = self.font_small.render(rating_text, True, self.ACCENT)
            self.screen.blit(rating_surf, (meta_x, meta_y))
            meta_y += rating_surf.get_height() + 12

        # Genres
        if metadata.get("genres"):
            genre_text = ", ".join(metadata["genres"][:3])
            genre_surf = self.font_small.render(genre_text, True, self.DIM)
            self.screen.blit(genre_surf, (meta_x, meta_y))
            meta_y += genre_surf.get_height() + 12

        # Plot
        if metadata.get("plot"):
            plot = metadata["plot"]
            char_width = self.font_small.get_ascent()
            chars_per_line = max(30, meta_w // (char_width * 0.6))
            import textwrap

            plot_lines = textwrap.wrap(plot, width=chars_per_line)
            for line in plot_lines[:4]:
                line_surf = self.font_small.render(line, True, self.TEXT)
                self.screen.blit(line_surf, (meta_x, meta_y))
                meta_y += line_surf.get_height() + 4

        self._render_hint_bar(f"Enter {action_text}   Esc Back")

        pygame.display.flip()

    def render_list(self, title: str, items: list, selected: int):
        """Render vertical list (seasons, episodes)."""
        self.screen.fill(self.BG)

        # Title bar
        title_h = 60
        title_surf = self.font_title.render(title, True, self.TEXT)
        self.screen.blit(title_surf, (40, (title_h - title_surf.get_height()) // 2))

        # List items
        item_h = 50
        list_y = title_h + 20
        visible = (self.height - list_y - 80) // item_h

        start = max(0, selected - visible // 2)
        for i in range(start, min(start + visible, len(items))):
            item = items[i]
            y = list_y + (i - start) * item_h

            # Background
            if i == selected:
                pygame.draw.rect(
                    self.screen,
                    (30, 30, 30),
                    (20, y, self.width - 40, item_h),
                    border_radius=4,
                )
                color = self.TEXT
            else:
                color = self.DIM

            # Item text
            text = item if isinstance(item, str) else item.get("name", "?")
            text_surf = self.font.render(text, True, color)
            self.screen.blit(text_surf, (40, y + (item_h - text_surf.get_height()) // 2))

        # Bottom hint
        hint_y = self.height - 50
        hint_surf = self.font_small.render(
            "↑↓ Navigate   Enter Select   Esc Back", True, self.DIM
        )
        self.screen.blit(hint_surf, (40, hint_y))

        pygame.display.flip()

    def wait_key(self) -> Optional[str]:
        """Wait for dpad input."""
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        return "up"
                    elif event.key == pygame.K_DOWN:
                        return "down"
                    elif event.key == pygame.K_LEFT:
                        return "left"
                    elif event.key == pygame.K_RIGHT:
                        return "right"
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        return "select"
                    elif event.key == pygame.K_ESCAPE:
                        return "back"
                    elif event.key == pygame.K_q:
                        return "quit"
                    elif event.key in (pygame.K_r, pygame.K_F5):
                        return "reload"
                    elif event.key in (pygame.K_PAGEDOWN, pygame.K_RIGHTBRACKET, pygame.K_TAB):
                        return "next_tab"
                    elif event.key in (pygame.K_PAGEUP, pygame.K_LEFTBRACKET):
                        return "prev_tab"
            pygame.time.wait(50)

    def quit(self):
        """Quit pygame."""
        pygame.quit()


# --- Main Player ---


def play_video(ui: UIRenderer, api: MediaServerAPI, media_path: str, title: str):
    """Play video with mpv."""
    ui.show_message(f"Playing {title}...")
    stream_url = api.get_stream_url(media_path)

    try:
        subprocess.run(
            ["mpv", "--fullscreen", "--hwdec=auto", stream_url],
            check=False,
        )
    except Exception as e:
        logger.error(f"Failed to play video: {e}")
        ui.show_message(f"Playback error: {e}")
        time.sleep(3)

    # Reclaim pygame display
    ui.screen = pygame.display.set_mode(
        (ui.width, ui.height), pygame.FULLSCREEN
    )
    pygame.mouse.set_visible(False)


def browse_grid(ui: UIRenderer, api: MediaServerAPI, path: str = "") -> bool:
    """Browse media grid. Returns True if user navigated deeper."""
    api.cache.pop(path, None)
    data = api.get_media(path)
    if not data:
        ui.show_message("No media found")
        time.sleep(2)
        return False

    items = data.get("items", [])
    if not items:
        ui.show_message("No items in this folder")
        time.sleep(2)
        return False

    selected = 0
    title = path.split("/")[-1] if path else "Media"

    while True:
        ui.render_grid(title, items, selected, api)
        key = ui.wait_key()

        if key == "up":
            cols = ui.grid_cols
            selected = max(0, selected - cols)
        elif key == "down":
            cols = ui.grid_cols
            selected = min(len(items) - 1, selected + cols)
        elif key == "left":
            selected = max(0, selected - 1)
        elif key == "right":
            selected = min(len(items) - 1, selected + 1)
        elif key == "select":
            item = items[selected]
            if item["type"] == "folder":
                # Navigate into folder
                browse_grid(ui, api, item["path"])
            else:
                # Show details and play
                ui.render_details(item, api, "Play")
                while True:
                    key = ui.wait_key()
                    if key == "select":
                        play_video(ui, api, item["path"], item.get("name", "?"))
                        break
                    elif key == "back":
                        break
        elif key == "reload":
            api.cache.clear()
            ui.image_cache.clear()
            data = api.get_media(path)
            items = (data or {}).get("items", [])
            selected = min(selected, max(0, len(items) - 1))
        elif key in ("back", "quit"):
            return False if key == "quit" else True

    return True


def _load_tabs(api: MediaServerAPI) -> tuple:
    """Re-query the indexer root and return (tabs, paths) for the menu."""
    root_data = api.get_media()
    if not root_data or not root_data.get("items"):
        return [], []
    folders = [item for item in root_data["items"] if item["type"] == "folder"]
    return (
        [folder["name"] for folder in folders],
        [folder["path"] for folder in folders],
    )


def main_menu(ui: UIRenderer, api: MediaServerAPI):
    """Main menu with dynamic tabs for all folders in /media.

    Press R or F5 anywhere in the grid to re-query the indexer (catches
    USB drives plugged in after launch).
    """
    tabs, tab_paths = _load_tabs(api)
    if not tabs:
        ui.show_message("No media folders found in /media")
        time.sleep(3)
        return

    selected_tab = 0

    while True:
        ui.show_message(f"Loading {tabs[selected_tab]}...")

        # Get items for current tab. Bypass the per-path cache so reloads
        # always reflect drives mounted after the player started.
        path = tab_paths[selected_tab]
        api.cache.pop(path, None)
        data = api.get_media(path)

        if data and data.get("items"):
            items = data["items"]
            selected = 0

            while True:
                ui.render_grid(
                    tabs[selected_tab], items, selected, api,
                    tabs=tabs, selected_tab=selected_tab,
                )
                key = ui.wait_key()

                cols = ui.grid_cols
                col = selected % cols

                if key == "up":
                    selected = max(0, selected - cols)
                elif key == "down":
                    selected = min(len(items) - 1, selected + cols)
                elif key == "left":
                    if col == 0 and selected_tab > 0:
                        selected_tab -= 1
                        break
                    else:
                        selected = max(0, selected - 1)
                elif key == "right":
                    if col == cols - 1 and selected_tab < len(tabs) - 1:
                        selected_tab += 1
                        break
                    else:
                        selected = min(len(items) - 1, selected + 1)
                elif key == "next_tab" and len(tabs) > 1:
                    selected_tab = (selected_tab + 1) % len(tabs)
                    break
                elif key == "prev_tab" and len(tabs) > 1:
                    selected_tab = (selected_tab - 1) % len(tabs)
                    break
                elif key == "select":
                    item = items[selected]
                    if item["type"] == "folder":
                        browse_grid(ui, api, item["path"])
                    else:
                        ui.render_details(item, api, "Play")
                        while True:
                            k = ui.wait_key()
                            if k == "select":
                                play_video(ui, api, item["path"], item.get("name", "?"))
                                break
                            elif k == "back":
                                break
                elif key == "reload":
                    new_tabs, new_paths = _load_tabs(api)
                    if new_tabs:
                        tabs, tab_paths = new_tabs, new_paths
                        selected_tab = min(selected_tab, len(tabs) - 1)
                    api.cache.clear()
                    ui.image_cache.clear()
                    break
                elif key == "quit":
                    return

        else:
            ui.show_message(f"Empty: {tabs[selected_tab]}")
            time.sleep(2)
            selected_tab = (selected_tab + 1) % len(tabs)


def main():
    """Main entry point."""
    ui = UIRenderer()
    api = MediaServerAPI()

    ui.show_message("Connecting to server...")

    # Wait for server to be ready
    for attempt in range(60):
        try:
            api.get_media()
            logger.info("Server ready")
            break
        except Exception:
            time.sleep(1)
    else:
        ui.show_message("Server not responding")
        time.sleep(3)
        ui.quit()
        sys.exit(1)

    try:
        main_menu(ui, api)
    except KeyboardInterrupt:
        pass
    finally:
        ui.quit()


if __name__ == "__main__":
    main()
