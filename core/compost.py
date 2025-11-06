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
        self.radius = radius
        self.color = color
        self.ring_color = (210, 180, 120)

    def draw(self, surface):
        # base
        pygame.draw.circle(surface, self.color,
                           (int(self.pos.x), int(self.pos.y)), self.radius)
        # decorative ring
        pygame.draw.circle(surface, self.ring_color,
                           (int(self.pos.x), int(self.pos.y)), self.radius + 6, 2)
