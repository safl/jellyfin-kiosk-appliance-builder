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
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JKAB_VERSION = "v0.7.0"


def item_label(item: dict) -> str:
    """Display label for an item, prefixing season/episode for episodes."""
    name = item.get("name", "?")
    meta = item.get("metadata") or {}
    season = meta.get("season")
    episode = meta.get("episode")
    if season is not None and episode is not None:
        return f"S{int(season):02d}E{int(episode):02d}  {name}"
    if episode is not None:
        return f"E{int(episode):02d}  {name}"
    return name

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

    @staticmethod
    def _encode(path: str) -> str:
        """Percent-encode each path segment, preserve slashes."""
        return urllib.parse.quote(path, safe="/")

    def get_media(self, path: str = "") -> Optional[dict]:
        """Get media listing for a path."""
        try:
            suffix = f"/{self._encode(path)}" if path else ""
            url = f"{self.server}/api/media{suffix}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            self.cache[path] = data
            return data
        except Exception as e:
            logger.error(f"Failed to get media {path}: {e}")
            return self.cache.get(path)

    def get_stream_url(self, media_path: str) -> str:
        """Get stream URL for a video."""
        return f"{STREAM_BASE}/{self._encode(media_path)}"

    def get_image_url(self, image_path: str) -> str:
        """Get image URL."""
        return f"{IMAGE_BASE}/{self._encode(image_path)}"

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

        self.font_title = pygame.font.SysFont(font_name, int(64 * s), bold=True)
        self.font_big = pygame.font.SysFont(font_name, int(50 * s), bold=True)
        self.font = pygame.font.SysFont(font_name, int(38 * s))
        self.font_small = pygame.font.SysFont(font_name, int(28 * s))

        # Grid layout — fewer, larger covers. Poster width is derived from
        # the available width so the row spans the whole grid uniformly.
        self.grid_cols = max(4, int(self.width / 600))
        self.grid_margin = int(60 * s)
        self.grid_gap = int(20 * s)
        total_gap = self.grid_gap * (self.grid_cols - 1)
        self.poster_w = (self.width - self.grid_margin * 2 - total_gap) // self.grid_cols
        self.poster_h = int(self.poster_w * 1.5)  # 2:3 portrait
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
        tab_focus: bool = False,
    ):
        """Render grid of items (posters), with optional Collections tab bar."""
        self.screen.fill(self.BG)

        s = max(1, self.height / 1080)
        title_h = int(90 * s)

        if tabs:
            self._render_tab_bar(tabs, selected_tab, title_h, tab_focus)
        else:
            title_surf = self.font_title.render(title, True, self.TEXT)
            self.screen.blit(title_surf, (40, (title_h - title_surf.get_height()) // 2))

        start_y = title_h + int(40 * s)
        grid_x_start = self.grid_margin
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
            label_band = self.font.get_height() + int(20 * max(1, self.height / 1080))
            y = start_y + row * (poster_h + gap + label_band)

            poster_img = None
            if item.get("poster"):
                poster_img = self._load_image(api.get_image_url(item["poster"]))

            label = item_label(item)
            meta = item.get("metadata") or {}
            is_episode = meta.get("episode") is not None
            is_folder = item.get("type") == "folder"

            if i == selected and not tab_focus:
                ring_outer = max(8, int(12 * s))
                ring_inner = max(3, int(5 * s))
                pygame.draw.rect(
                    self.screen,
                    (170, 0, 0),
                    (x - ring_outer, y - ring_outer,
                     poster_w + ring_outer * 2, poster_h + ring_outer * 2),
                    border_radius=12,
                )
                pygame.draw.rect(
                    self.screen,
                    (210, 210, 210),
                    (x - ring_inner, y - ring_inner,
                     poster_w + ring_inner * 2, poster_h + ring_inner * 2),
                    border_radius=8,
                )

            if poster_img:
                scaled = pygame.transform.smoothscale(poster_img, (poster_w, poster_h))
                self.screen.blit(scaled, (x, y))
            else:
                pygame.draw.rect(
                    self.screen, self.DIM, (x, y, poster_w, poster_h), border_radius=4
                )
                placeholder_surf = self.font.render(label[:18], True, self.TEXT)
                text_rect = placeholder_surf.get_rect(center=(x + poster_w // 2, y + poster_h // 2))
                self.screen.blit(placeholder_surf, text_rect)

            # Label below poster: always for folders (user needs to know what
            # they're entering) and episodes (SxxExx is the useful info), and
            # for any item without artwork. Hidden only for movies whose
            # poster already speaks for itself.
            if is_folder or is_episode or poster_img is None:
                label_text = label if len(label) <= 26 else label[:25] + "…"
                label_surf = self.font.render(label_text, True, self.TEXT)
                self.screen.blit(label_surf, (x, y + poster_h + 12))

        self._render_hint_bar(
            "↑↓←→ Navigate   Enter Select   Esc Back   ↑ from top: switch Collection   R Reload"
        )

        pygame.display.flip()

    def _render_tab_bar(self, tabs: list, selected_tab: int, height: int, tab_focus: bool = False):
        """Draw a horizontal Collections tab bar at the top.

        When ``tab_focus`` is True, the active tab gets a chip background and
        a thicker underline so it's visually obvious that DPad input now acts
        on the bar (left/right switches collection, down returns to grid).
        """
        s = max(1, self.height / 1080)
        bar_bg = (28, 28, 28) if tab_focus else (15, 15, 15)
        pygame.draw.rect(self.screen, bar_bg, (0, 0, self.width, height))

        pad = int(28 * s)
        gap = int(36 * s)
        sep_w = max(1, int(2 * s))
        sep_h = int(self.font.get_height() * 0.55)
        x = pad
        y_text = (height - self.font.get_height()) // 2
        sep_y = (height - sep_h) // 2
        for i, name in enumerate(tabs):
            label_surf = self.font.render(name, True, self.TEXT if i == selected_tab else self.DIM)
            label_w = label_surf.get_width()
            if i == selected_tab:
                if tab_focus:
                    chip_pad = int(10 * s)
                    pygame.draw.rect(
                        self.screen,
                        (60, 60, 60),
                        (x - chip_pad, y_text - chip_pad // 2,
                         label_w + chip_pad * 2, label_surf.get_height() + chip_pad),
                        border_radius=6,
                    )
                underline_y = height - int(6 * s)
                pygame.draw.rect(
                    self.screen,
                    self.ACCENT,
                    (x, underline_y, label_w, int(6 * s) if tab_focus else int(4 * s)),
                )
            self.screen.blit(label_surf, (x, y_text))
            x += label_w
            if i < len(tabs) - 1:
                sep_x = x + gap // 2 - sep_w // 2
                pygame.draw.rect(
                    self.screen, (80, 80, 80), (sep_x, sep_y, sep_w, sep_h)
                )
                x += gap

        lib_surf = self.font_small.render("Media Library", True, self.DIM)
        self.screen.blit(
            lib_surf,
            (self.width - lib_surf.get_width() - pad, (height - lib_surf.get_height()) // 2),
        )

    def _render_hint_bar(self, hint_text: str):
        """Draw the bottom hint bar with the JKAB version anchored bottom-right.

        Multi-spaced hint segments (split on three+ spaces) are joined with
        a middle-dot glyph for clearer visual separation. A thin divider sits
        between the hint text and the version label.
        """
        s = max(1, self.height / 1080)
        hint_bar_h = int(70 * s)
        bar_top = self.height - hint_bar_h
        pad_y = (hint_bar_h - self.font_small.get_height()) // 2
        pygame.draw.rect(self.screen, (20, 20, 20), (0, bar_top, self.width, hint_bar_h))

        # Divider above the bar
        pygame.draw.rect(self.screen, (50, 50, 50), (0, bar_top, self.width, max(1, int(2 * s))))

        import re
        joined = re.sub(r" {2,}", "  \u00B7  ", hint_text)
        hint_surf = self.font_small.render(joined, True, self.DIM)
        self.screen.blit(hint_surf, (40, bar_top + pad_y))

        ver_surf = self.font_small.render(f"JKAB {JKAB_VERSION}", True, self.DIM)
        ver_x = self.width - ver_surf.get_width() - 20

        # Vertical separator between hints and version label
        sep_h = int(self.font_small.get_height() * 0.7)
        sep_x = ver_x - int(20 * s)
        pygame.draw.rect(
            self.screen,
            (60, 60, 60),
            (sep_x, bar_top + (hint_bar_h - sep_h) // 2, max(1, int(2 * s)), sep_h),
        )
        self.screen.blit(ver_surf, (ver_x, bar_top + pad_y))

    def render_details(self, item: dict, api: MediaServerAPI, action_text: str = "Play"):
        """Render item details (poster + metadata)."""
        self.screen.fill(self.BG)

        poster_img = None
        if item.get("poster"):
            poster_img = self._load_image(api.get_image_url(item["poster"]))

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
            ph_surf = self.font_big.render(item_label(item)[:24], True, self.TEXT)
            text_rect = ph_surf.get_rect(center=(poster_x + poster_w // 2, poster_y + poster_h // 2))
            self.screen.blit(ph_surf, text_rect)

        # Metadata on right
        meta_x = poster_x + poster_w + 60
        meta_y = poster_y
        meta_w = self.width - meta_x - 40

        metadata = item.get("metadata", {})

        title = item_label(item)
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

        # Play button flows under the plot text but is also pinned so it
        # never exceeds the poster height — keeps the right column visually
        # aligned with the left poster column.
        s = max(1, self.height / 1080)
        hint_bar_h = int(70 * s)
        btn_h = int(110 * s)
        btn_w = int(380 * s)
        poster_bottom = poster_y + poster_h
        button_top_floor = self.height - hint_bar_h - btn_h - int(40 * s)
        btn_y = max(meta_y + int(36 * s), poster_bottom - btn_h)
        btn_y = min(btn_y, button_top_floor)
        btn_x = meta_x

        # Visual style mirrors the selected episode row: a dark chip with a
        # red bottom-stripe matching the active tab underline.
        pygame.draw.rect(
            self.screen,
            (30, 30, 30),
            (btn_x, btn_y, btn_w, btn_h),
            border_radius=int(12 * s),
        )
        stripe_h = int(8 * s)
        pygame.draw.rect(
            self.screen,
            self.ACCENT,
            (btn_x, btn_y + btn_h - stripe_h, btn_w, stripe_h),
            border_bottom_left_radius=int(12 * s),
            border_bottom_right_radius=int(12 * s),
        )
        play_label = f"\u25B6  {action_text}"
        play_surf = self.font_big.render(play_label, True, self.TEXT)
        play_rect = play_surf.get_rect(center=(btn_x + btn_w // 2, btn_y + (btn_h - stripe_h) // 2))
        self.screen.blit(play_surf, play_rect)

        self._render_hint_bar(f"Enter {action_text}   Esc Back")

        pygame.display.flip()

    def render_episode_list(
        self, title: str, items: list, selected: int, api: MediaServerAPI
    ):
        """Vertical scrolling list for season/episode browsing.

        Each row: 16:9 thumbnail (left), label (top-right), plot (below).
        The selected row gets a chip background and a brighter label.
        """
        self.screen.fill(self.BG)

        s = max(1, self.height / 1080)
        title_h = int(90 * s)
        margin = int(60 * s)

        title_surf = self.font_title.render(title, True, self.TEXT)
        self.screen.blit(title_surf, (margin, (title_h - title_surf.get_height()) // 2))

        hint_bar_h = int(70 * s)
        list_y = title_h + int(20 * s)
        list_h = self.height - list_y - hint_bar_h

        thumb_h = int(280 * s)
        thumb_w = int(thumb_h * 16 / 9)
        row_pad = int(20 * s)
        row_h = thumb_h + row_pad

        visible = max(1, list_h // row_h)
        start = max(0, selected - visible // 2)
        start = min(start, max(0, len(items) - visible))

        text_x = margin + thumb_w + int(28 * s)
        text_w = self.width - text_x - margin

        import textwrap
        plot_chars = max(40, int(text_w / (self.font_small.get_height() * 0.55)))

        for i in range(start, min(start + visible, len(items))):
            item = items[i]
            y = list_y + (i - start) * row_h
            row_rect = (
                margin - row_pad // 2,
                y,
                self.width - margin * 2 + row_pad,
                row_h - row_pad,
            )
            if i == selected:
                pygame.draw.rect(self.screen, (30, 30, 30), row_rect, border_radius=8)

            thumb_img = None
            if item.get("poster"):
                thumb_img = self._load_image(api.get_image_url(item["poster"]))
            if thumb_img:
                scaled = pygame.transform.smoothscale(thumb_img, (thumb_w, thumb_h))
                self.screen.blit(scaled, (margin, y))
            else:
                pygame.draw.rect(
                    self.screen, self.DIM, (margin, y, thumb_w, thumb_h), border_radius=4
                )

            label_color = self.TEXT if i == selected else self.DIM
            label_surf = self.font.render(item_label(item), True, label_color)
            self.screen.blit(label_surf, (text_x, y + int(10 * s)))

            plot = (item.get("metadata") or {}).get("plot") or ""
            if plot:
                lines = textwrap.wrap(plot, width=plot_chars)
                line_y = y + int(10 * s) + label_surf.get_height() + int(10 * s)
                line_color = self.TEXT if i == selected else self.DIM
                max_lines = max(1, (thumb_h - (line_y - y)) // (self.font_small.get_height() + 4))
                for line in lines[:max_lines]:
                    line_surf = self.font_small.render(line, True, line_color)
                    self.screen.blit(line_surf, (text_x, line_y))
                    line_y += line_surf.get_height() + 4

        if len(items) > visible:
            scroll_text = f"{selected + 1} / {len(items)}"
            scroll_surf = self.font_big.render(scroll_text, True, self.TEXT)
            self.screen.blit(
                scroll_surf,
                (self.width - scroll_surf.get_width() - margin,
                 title_h - scroll_surf.get_height() - int(8 * s)),
            )

        self._render_hint_bar("↑↓ Navigate   Enter Play   Esc Back   R Reload")
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


def _is_episode_listing(items: list) -> bool:
    """True when most video items in the listing have episode metadata.
    Triggers the vertical scroll list view (Series/Season browsing)."""
    videos = [it for it in items if it.get("type") == "video"]
    if not videos:
        return False
    with_episode = sum(
        1 for it in videos if (it.get("metadata") or {}).get("episode") is not None
    )
    return with_episode >= max(1, len(videos) // 2 + 1)


def browse_grid(ui: UIRenderer, api: MediaServerAPI, path: str = "") -> bool:
    """Browse media. Renders as a poster grid by default, or as a vertical
    episode list when the listing is dominated by TV episodes.

    Returns True if user navigated deeper."""
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
    list_mode = data.get("view_hint") == "list" or _is_episode_listing(items)

    while True:
        if list_mode:
            ui.render_episode_list(title, items, selected, api)
        else:
            ui.render_grid(title, items, selected, api)
        key = ui.wait_key()

        if list_mode:
            if key == "up":
                selected = max(0, selected - 1)
            elif key == "down":
                selected = min(len(items) - 1, selected + 1)
            elif key == "select":
                item = items[selected]
                if item["type"] == "folder":
                    browse_grid(ui, api, item["path"])
                else:
                    play_video(ui, api, item["path"], item.get("name", "?"))
            elif key == "reload":
                api.cache.clear()
                ui.image_cache.clear()
                data = api.get_media(path) or {}
                items = data.get("items", [])
                selected = min(selected, max(0, len(items) - 1))
                list_mode = data.get("view_hint") == "list" or _is_episode_listing(items)
            elif key in ("back", "quit"):
                return False if key == "quit" else True
            continue

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
                browse_grid(ui, api, item["path"])
            else:
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
            data = api.get_media(path) or {}
            items = data.get("items", [])
            selected = min(selected, max(0, len(items) - 1))
            list_mode = data.get("view_hint") == "list" or _is_episode_listing(items)
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
    tab_focus = False  # Persists across tab switches: stay in tab focus
                       # while the user cycles collections, until they
                       # press DOWN or SELECT to commit to the grid.

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
                    tab_focus=tab_focus,
                )
                key = ui.wait_key()

                if tab_focus:
                    if key == "left" and len(tabs) > 1:
                        selected_tab = (selected_tab - 1) % len(tabs)
                        break
                    elif key == "right" and len(tabs) > 1:
                        selected_tab = (selected_tab + 1) % len(tabs)
                        break
                    elif key in ("down", "select", "back"):
                        tab_focus = False
                    elif key == "quit":
                        return
                    elif key == "reload":
                        new_tabs, new_paths = _load_tabs(api)
                        if new_tabs:
                            tabs, tab_paths = new_tabs, new_paths
                            selected_tab = min(selected_tab, len(tabs) - 1)
                        api.cache.clear()
                        ui.image_cache.clear()
                        break
                    continue

                cols = ui.grid_cols
                col = selected % cols
                row = selected // cols

                if key == "up":
                    if row == 0 and len(tabs) > 1:
                        tab_focus = True
                    else:
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
