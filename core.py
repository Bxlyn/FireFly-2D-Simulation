import pygame
import random as rd
import configs.settings as cs

class Drone:
    def __init__(self, x, y):
        self.x_pos = x
        self.y_pos = y
    
    def draw(self, surface, radius):
        for d in range(4):
            self.drone = pygame.draw.circle(surface, cs.blue,(self.x_pos + d*24, self.y_pos), radius)
    
    def move():
        pass