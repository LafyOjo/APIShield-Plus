"""Simple SPI display dashboard.

Poll the detector API for aggregated alert statistics and render the latest
counts to a 3.5" SPI screen using ``pygame``. Intended for Raspberry Pi setups
with a small display attached.
"""

import argparse
import time

import pygame
import requests


def fetch_stats(api_base: str, token: str | None) -> list[dict]:
    """Fetch alert statistics from the detector API."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.get(f"{api_base}/api/alerts/stats", headers=headers, timeout=5)
    resp.raise_for_status()
    return resp.json()


def draw_stats(screen: pygame.Surface, font: pygame.font.Font, stats: list[dict]):
    """Render the latest stats to the display."""
    screen.fill((0, 0, 0))
    if not stats:
        text = font.render("No data yet", True, (255, 255, 255))
        screen.blit(text, (10, 10))
    else:
        last = stats[-1]
        lines = [
            "Latest stats:",
            f"Invalid credentials: {last['invalid']}",
            f"Blocked attempts: {last['blocked']}",
        ]
        y = 10
        for line in lines:
            text = font.render(line, True, (255, 255, 255))
            screen.blit(text, (10, y))
            y += font.get_height() + 5
    pygame.display.flip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Display alerts on an SPI screen")
    parser.add_argument("--api-base", default="http://localhost:8001",
                        help="Base URL of the detector API")
    parser.add_argument("--token", help="JWT token for accessing protected endpoints")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Refresh interval in seconds")
    args = parser.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((480, 320))
    font = pygame.font.Font(None, 36)

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
            try:
                stats = fetch_stats(args.api_base, args.token)
            except Exception as e:
                screen.fill((0, 0, 0))
                text = font.render(f"Error: {e}", True, (255, 0, 0))
                screen.blit(text, (10, 10))
                pygame.display.flip()
            else:
                draw_stats(screen, font, stats[-10:])
            time.sleep(args.interval)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
