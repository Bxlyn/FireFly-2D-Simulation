import pygame
import configs.settings as cs

# pygame setup
pygame.init()
screen = pygame.display.set_mode((cs.screen_width, cs.screen_height))
clock = pygame.time.Clock()
running = True

while running:
    # poll for events
    # pygame.QUIT event means the user clicked X to close your window
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # fill the screen with a color to wipe away anything from last frame
    screen.fill(cs.dgreen)

    # RENDER YOUR GAME HERE

    # flip() the display to put your work on screen
    pygame.display.flip()

    clock.tick(cs.fps)  # limits FPS to 60

pygame.quit()