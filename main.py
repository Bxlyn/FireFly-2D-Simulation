import pygame
import core.drone as cd
import core.compost as cc
import core.fire as fire
import configs.settings as cs

pygame.init()
screen = pygame.display.set_mode((cs.screen_width, cs.screen_height))
clock = pygame.time.Clock()
running = True

compost = cc.Compost(radius=cs.cradius, color=cs.cyellow)
sim_fire = fire.Fire(cell_px=cs.fire_cell_px)
drones = cd.Drone(cs.startX, cs.startY, cs.speed,
                  start_delay=cs.start_delay,
                  compost=compost,
                  fire_sim=sim_fire)  # <-- pass fire_sim

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        # Optional: click to ignite
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = pygame.mouse.get_pos()
            sim_fire.ignite_world(x, y, radius_px=cs.click_ignite_radius_px)

    dt = clock.tick(cs.fps) / 1000.0
    screen.fill(cs.dgreen)

    compost.draw(screen)

    # Background random ignitions
    sim_fire.random_ignitions(cs.bg_ignitions_per_s, dt)
    sim_fire.update(dt)
    sim_fire.draw(screen)

    drones.move(dt)
    drones.draw(screen, dt_since_last_frame=dt)

    pygame.display.flip()

pygame.quit()
