# main.py
import time
import threading
from collections import deque

import pygame
import core.drone as cd
import core.compost as cc
import core.fire as fire
import configs.settings as cs

# =========================
# Minimal central log bus (prints to terminal)
# =========================
class LogBus:
    def __init__(self, maxlen=1000, stamp=True, mirror_stdout=True):
        self._lines = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._stamp = stamp
        self._mirror = mirror_stdout

    def push(self, s: str):
        if not isinstance(s, str):
            s = str(s)
        if self._stamp:
            t = time.strftime("%H:%M:%S")
            s = f"{t}  {s}"
        with self._lock:
            self._lines.append(s)
        if self._mirror:
            print(s, flush=True)  # real-time terminal output

    def snapshot(self):
        with self._lock:
            return list(self._lines)

# =========================
# App bootstrap
# =========================
pygame.init()
pygame.display.set_caption("FireFly 2D Simulation")
screen = pygame.display.set_mode((cs.screen_width, cs.screen_height))
clock = pygame.time.Clock()
running = True

# Central log bus (terminal only)
log_bus = LogBus(maxlen=getattr(cs, "max_log_lines", 2000), stamp=True, mirror_stdout=True)
log_bus.push("[SYSTEM] Simulation started. Left click to ignite a spot fire. Press Esc to quit.")

compost = cc.Compost(radius=cs.cradius, color=cs.cyellow)
sim_fire = fire.Fire(cell_px=cs.fire_cell_px)

# Announce scale so IRL conversions are clear
log_bus.push(
    f"[SCALE] 1 px = {sim_fire.px_to_m:.3f} m; "
    f"1 fire cell = {sim_fire.cell} px = {sim_fire.cell * sim_fire.px_to_m:.2f} m; "
    f"cell area = {sim_fire.cell_area_m2:.1f} m²."
)

drones = cd.Drone(cs.startX, cs.startY, cs.speed,
                  start_delay=cs.start_delay,
                  compost=compost,
                  fire_sim=sim_fire,
                  log_bus=log_bus)  # route alerts to the terminal

# =========================
# Main loop
# =========================
while running:
    for event in pygame.event.get():
        # Close main window
        if event.type == pygame.QUIT:
            running = False
            break

        # Esc to quit
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False
            break

        # Left-click to ignite (also log so you see something immediately)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = pygame.mouse.get_pos()
            sim_fire.ignite_world(x, y, radius_px=cs.click_ignite_radius_px)
            log_bus.push(f"[USER] Ignited at ({x}, {y})")
            continue

    if not running:
        break

    # Step sim
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
