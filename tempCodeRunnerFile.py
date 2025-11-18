import pygame
import core.drone as cd
import core.compost as cc
import configs.settings as cs
import core.fire as fire

pygame.init()
screen = pygame.display.set_mode((cs.screen_width, cs.screen_height))
clock = pygame.time.Clock()
running = True

# create compost at center (defaults are fine)
compost = cc.Compost(radius=cs.cradius, color=cs.cyellow)

sim_fire = fire.Fire(cell_px=cs.fire_cell_px)

# pass compost and a start delay (e.g., 2.0 seconds)
drones = cd.Drone(cs.startX, cs.startY, cs.speed, start_delay=cs.start_delay, compost=compost)

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    dt = clock.tick(cs.fps) / 1000.0

    screen.fill(cs.dgreen)

    # draw compost first so drones render on top
    compost.draw(screen)

    # --- FIRE ---
    sim_fire.random_ignitions(lam_per_s=0.02, dt=dt)  # occasional spontaneous ignitions
    sim_fire.update(dt)
    sim_fire.draw(screen)

    # --- DRONE ---
    drones.move(dt)
    drones.draw(screen)

    pygame.display.flip()

pygame.quit()
