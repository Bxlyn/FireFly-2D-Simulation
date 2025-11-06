import pygame
import core.drone as cd
import configs.settings as cs

pygame.init()
screen = pygame.display.set_mode((cs.screen_width, cs.screen_height))
clock = pygame.time.Clock()
running = True

drones = cd.Drone(cs.startX, cs.startY, cs.speed)

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    dt = clock.tick(cs.fps) / 1000.0  # seconds since last frame

    screen.fill(cs.dgreen)

    drones.move(dt)
    drones.draw(screen)

    pygame.display.flip()

pygame.quit()
