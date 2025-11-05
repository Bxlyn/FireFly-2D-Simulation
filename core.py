import pygame
import random as rd
import configs.settings as cs

class Drone:
    def __init__(self, x, y, speed):
        self.radius = 10
        self.speed = speed

        self.position = [(x+d*24, y) for d in range(4)]
    def draw(self, surface):
        for pos in self.position:
            pygame.draw.circle(surface, cs.blue,pos, self.radius)
    
    def move(self):
        for i in range(len(self.position)):
            x, y = self.position[i]
            self.position[i] = (x+self.speed, y+self.speed)