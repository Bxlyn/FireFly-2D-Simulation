# =========================
# core/compost.py
# =========================
import pygame
import configs.settings as cs


class Compost:
    """
    Central hub where all drones spawn from.
    Defaults to screen center unless (x, y) provided.
    """
    def __init__(self, radius, color, x=None, y=None):
        w, h = cs.screen_width, cs.screen_height
        cx, cy = (w // 2, h // 2)
        self.pos = pygame.Vector2(cx if x is None else x,
                                  cy if y is None else y)
        self.radius = float(radius)
        self.color = color
        self.ring_color = (210, 180, 120)
        self.guide_color = (230, 230, 230)

    def draw(self, surface):
        cx, cy = int(self.pos.x), int(self.pos.y)
        r = int(self.radius)
        pygame.draw.circle(surface, self.color, (cx, cy), r)
        pygame.draw.circle(surface, self.ring_color, (cx, cy), r + 6, 2)
        pygame.draw.line(surface, self.guide_color, (cx - r, cy), (cx + r, cy), 2)
        pygame.draw.line(surface, self.guide_color, (cx, cy - r), (cx, cy + r), 2)
