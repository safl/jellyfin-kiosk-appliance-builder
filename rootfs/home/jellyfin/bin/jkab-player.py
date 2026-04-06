#!/usr/bin/env python3
"""JKAB Player — Simple Jellyfin client for TV remote / D-pad navigation"""
import io
import json
import subprocess
import sys
import textwrap
import time
import urllib.request

SERVER = "http://localhost:8096"
AUTH_HEADER = 'MediaBrowser Client="JKAB", Device="JKAB", DeviceId="jkab", Version="1.0"'

# --- Jellyfin API ---

class JellyfinAPI:
    def __init__(self, server, username, password):
        self.server = server
        self.token = None
        self.user_id = None
        self._image_cache = {}
        self._auth(username, password)

    def _request(self, path, method="GET", data=None):
        url = f"{self.server}{path}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f'{AUTH_HEADER}, Token="{self.token}"'
        else:
            headers["Authorization"] = AUTH_HEADER
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def _auth(self, username, password):
        result = self._request("/Users/AuthenticateByName", "POST",
                               {"Username": username, "Pw": password})
        self.token = result["AccessToken"]
        self.user_id = result["User"]["Id"]

    def get_libraries(self):
        result = self._request(f"/Users/{self.user_id}/Views")
        return result["Items"]

    def get_items(self, parent_id):
        result = self._request(
            f"/Users/{self.user_id}/Items?ParentId={parent_id}"
            f"&SortBy=SortName&SortOrder=Ascending"
            f"&Fields=Overview,RunTimeTicks,ProductionYear,CommunityRating,Genres"
            f"&Recursive=false"
        )
        return result["Items"]

    def get_stream_url(self, item_id):
        return (f"{self.server}/Videos/{item_id}/stream"
                f"?Static=true&api_key={self.token}")

    def get_image(self, item_id, image_type="Primary", max_height=400):
        key = f"{item_id}_{image_type}_{max_height}"
        if key in self._image_cache:
            return self._image_cache[key]
        try:
            url = (f"{self.server}/Items/{item_id}/Images/{image_type}"
                   f"?maxHeight={max_height}&quality=80")
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = resp.read()
            self._image_cache[key] = data
            return data
        except Exception:
            return None


# --- UI ---

try:
    import pygame
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "--break-system-packages", "pygame"])
    import pygame


class UI:
    BG = (15, 15, 20)
    PANEL_BG = (25, 25, 35)
    FG = (200, 200, 210)
    SEL = (30, 80, 180)
    SEL_BRIGHT = (50, 110, 220)
    DIM = (100, 100, 120)
    ACCENT = (80, 160, 255)
    TITLE_COLOR = (255, 255, 255)
    YEAR_COLOR = (150, 150, 170)
    RATING_COLOR = (255, 200, 50)

    def __init__(self):
        pygame.init()
        pygame.mouse.set_visible(False)
        info = pygame.display.Info()
        self.width = info.current_w
        self.height = info.current_h
        self.screen = pygame.display.set_mode((self.width, self.height),
                                               pygame.FULLSCREEN)
        s = max(1, self.height / 1080)  # scale factor relative to 1080p
        self.font_title = pygame.font.SysFont("sans", int(40 * s))
        self.font_big = pygame.font.SysFont("sans", int(34 * s))
        self.font = pygame.font.SysFont("sans", int(28 * s))
        self.font_small = pygame.font.SysFont("sans", int(22 * s))
        self.font_detail = pygame.font.SysFont("sans", int(24 * s))
        self.item_h = int(50 * s)
        self.list_width = self.width * 2 // 5
        self.detail_x = self.list_width + int(40 * s)

    def show_message(self, text):
        self.screen.fill(self.BG)
        surf = self.font.render(text, True, self.DIM)
        rect = surf.get_rect(center=(self.width // 2, self.height // 2))
        self.screen.blit(surf, rect)
        pygame.display.flip()

    def _draw_detail_panel(self, item, api):
        """Draw the right panel with poster, metadata, and overview."""
        if not isinstance(item, dict):
            return

        x = self.detail_x
        y = 100
        panel_w = self.width - x - 40

        # Dark panel background
        panel = pygame.Rect(x - 20, 80, panel_w + 40, self.height - 160)
        pygame.draw.rect(self.screen, self.PANEL_BG, panel, border_radius=12)

        # Poster image
        poster_h = self.height // 2
        poster_w = int(poster_h * 0.67)
        img_data = api.get_image(item.get("Id", ""), max_height=poster_h) if api else None
        if img_data:
            try:
                img_surface = pygame.image.load(io.BytesIO(img_data))
                img_surface = pygame.transform.smoothscale(img_surface,
                                                           (poster_w, poster_h))
                self.screen.blit(img_surface, (x, y))
            except Exception:
                pass

        # Metadata next to poster
        meta_x = x + poster_w + 30
        meta_w = panel_w - poster_w - 50
        meta_y = y

        # Title
        name = item.get("Name", "")
        title_surf = self.font_big.render(name, True, self.TITLE_COLOR)
        self.screen.blit(title_surf, (meta_x, meta_y))
        meta_y += title_surf.get_height() + 10

        # Year and type
        parts = []
        if item.get("ProductionYear"):
            parts.append(str(item["ProductionYear"]))
        if item.get("Type"):
            parts.append(item["Type"])
        if item.get("RunTimeTicks"):
            mins = item["RunTimeTicks"] // 600000000
            parts.append(f"{mins} min")
        if parts:
            info_surf = self.font_small.render("  ·  ".join(parts), True,
                                                self.YEAR_COLOR)
            self.screen.blit(info_surf, (meta_x, meta_y))
            meta_y += info_surf.get_height() + 8

        # Rating
        if item.get("CommunityRating"):
            rating = f"★ {item['CommunityRating']:.1f}"
            rat_surf = self.font_small.render(rating, True, self.RATING_COLOR)
            self.screen.blit(rat_surf, (meta_x, meta_y))
            meta_y += rat_surf.get_height() + 8

        # Genres
        genres = item.get("Genres", [])
        if genres:
            genre_text = ", ".join(genres[:3])
            genre_surf = self.font_small.render(genre_text, True, self.DIM)
            self.screen.blit(genre_surf, (meta_x, meta_y))
            meta_y += genre_surf.get_height() + 15

        # Overview (wrapped text below poster)
        overview = item.get("Overview", "")
        if overview:
            ov_y = y + poster_h + 20
            chars_per_line = max(20, panel_w // (self.font_small.size("x")[0]))
            lines = textwrap.wrap(overview, width=chars_per_line)
            for line in lines[:6]:
                line_surf = self.font_small.render(line, True, self.FG)
                self.screen.blit(line_surf, (x, ov_y))
                ov_y += line_surf.get_height() + 4

    def show_menu(self, title, items, selected, api=None, name_key="Name"):
        self.screen.fill(self.BG)

        # Title bar
        title_h = int(60 * max(1, self.height / 1080))
        accent_bar = pygame.Rect(0, 0, self.width, title_h)
        pygame.draw.rect(self.screen, self.PANEL_BG, accent_bar)
        title_surf = self.font_title.render(title, True, self.ACCENT)
        self.screen.blit(title_surf, (40, (title_h - title_surf.get_height()) // 2))

        # Item list (left panel)
        ih = self.item_h
        list_top = title_h + 10
        visible = (self.height - list_top - 60) // ih
        start = max(0, selected - visible // 2)
        y = list_top

        for i in range(start, min(start + visible, len(items))):
            item = items[i]
            name = item if isinstance(item, str) else item.get(name_key, "?")

            if i == selected:
                bar = pygame.Rect(20, y, self.list_width - 20, ih - 4)
                pygame.draw.rect(self.screen, self.SEL, bar, border_radius=6)
                ind = pygame.Rect(20, y, 4, ih - 4)
                pygame.draw.rect(self.screen, self.SEL_BRIGHT, ind)
                color = self.TITLE_COLOR
            else:
                color = self.FG

            text_surf = self.font.render(name, True, color)
            text_y = y + (ih - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (40, text_y))

            if isinstance(item, dict) and item.get("ProductionYear"):
                yr = self.font_small.render(str(item["ProductionYear"]),
                                             True, self.DIM)
                self.screen.blit(yr, (self.list_width - 80, text_y + 4))

            y += ih

        # Detail panel for selected item
        if items and isinstance(items[selected], dict):
            self._draw_detail_panel(items[selected], api)

        # Bottom hint bar
        hint_bar = pygame.Rect(0, self.height - 50, self.width, 50)
        pygame.draw.rect(self.screen, self.PANEL_BG, hint_bar)
        hint = self.font_small.render("↑↓ Navigate   Enter Select   Esc Back",
                                       True, self.DIM)
        self.screen.blit(hint, (40, self.height - 40))

        pygame.display.flip()

    def wait_key(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        return "up"
                    elif event.key == pygame.K_DOWN:
                        return "down"
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        return "select"
                    elif event.key == pygame.K_ESCAPE:
                        return "back"
                    elif event.key == pygame.K_q:
                        return "quit"
            pygame.time.wait(50)

    def quit(self):
        pygame.quit()


# --- Player ---

def play_video(ui, url):
    """Play video with mpv fullscreen, hardware accelerated."""
    subprocess.call([
        "mpv", "--fullscreen", "--hwdec=auto",
        url
    ])
    # Reclaim display after mpv exits
    ui.screen = pygame.display.set_mode((ui.width, ui.height), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)


# --- Main ---

def browse_items(ui, api, title, parent_id):
    items = api.get_items(parent_id)
    if not items:
        ui.show_message("No items found")
        ui.wait_key()
        return

    selected = 0
    while True:
        ui.show_menu(title, items, selected, api=api)
        key = ui.wait_key()

        if key == "up":
            selected = max(0, selected - 1)
        elif key == "down":
            selected = min(len(items) - 1, selected + 1)
        elif key == "select":
            item = items[selected]
            if item["Type"] in ("Movie", "Episode"):
                ui.show_message(f"Playing {item['Name']}...")
                url = api.get_stream_url(item["Id"])
                play_video(ui, url)
            elif item["Type"] in ("Series", "Season", "Folder",
                                   "CollectionFolder", "BoxSet"):
                browse_items(ui, api, item["Name"], item["Id"])
        elif key in ("back", "quit"):
            return


def main():
    ui = UI()
    ui.show_message("Connecting to Jellyfin...")

    # Wait for server
    api = None
    for _ in range(60):
        try:
            api = JellyfinAPI(SERVER, "jellyfin", "jellyfin")
            break
        except Exception:
            time.sleep(2)

    if not api:
        ui.show_message("Could not connect to Jellyfin server")
        time.sleep(5)
        ui.quit()
        return

    # Main loop — browse libraries
    while True:
        libraries = api.get_libraries()
        selected = 0
        while True:
            ui.show_menu("JKAB", libraries, selected, api=api)
            key = ui.wait_key()
            if key == "up":
                selected = max(0, selected - 1)
            elif key == "down":
                selected = min(len(libraries) - 1, selected + 1)
            elif key == "select":
                lib = libraries[selected]
                browse_items(ui, api, lib["Name"], lib["Id"])
                break
            elif key in ("quit",):
                ui.quit()
                return


if __name__ == "__main__":
    main()
