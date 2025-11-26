import time
import threading
from collections import deque

import pygame
import core.drone as cd
import core.compost as cc
import core.fire as fire
import configs.settings as cs
from ui.start_screen import run_start_screen


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


def irl_str(sim_seconds: float) -> str:
    """Human-readable IRL time given sim seconds and cs.sim_to_real_min_per_sec."""
    mins = max(0.0, sim_seconds) * float(getattr(cs, "sim_to_real_min_per_sec", 10.0 / 3.0))
    if mins >= 90.0:
        h = int(mins // 60)
        m = int(round(mins % 60))
        return f"~{h}h {m}m"
    return f"~{mins:.1f}m"


# =========================
# App bootstrap
# =========================
pygame.init()
pygame.display.set_caption("FireFly 2D Simulation")
screen = pygame.display.set_mode((cs.screen_width, cs.screen_height))
clock = pygame.time.Clock()

# --- Start Screen ---
start_ok = run_start_screen(screen, clock, title="FireFly 2D Simulation")
if not start_ok:
    pygame.quit()
    raise SystemExit

running = True

# Central log bus (terminal only)
log_bus = LogBus(
    maxlen=getattr(cs, "max_log_lines", 2000),
    stamp=True,
    mirror_stdout=True
)
log_bus.push("[SYSTEM] Simulation started. Left click to ignite a spot fire. Press Esc to quit.")

compost = cc.Compost(radius=cs.cradius, color=cs.cyellow)
sim_fire = fire.Fire(cell_px=cs.fire_cell_px)

# Create drones (squad of 4 inside one object)
drones = cd.Drone(
    cs.startX, cs.startY, cs.speed,
    start_delay=cs.start_delay,
    compost=compost,
    fire_sim=sim_fire,
    log_bus=log_bus
)

# Log the chosen scale and expected cruise mapping once
mpp = drones.m_per_px  # meters per pixel (now exists)
target_kmh = float(getattr(cs, "hybrid_vtol_cruise_kmh", 72.0))  # display only
log_bus.push(
    f"[SCALE] 1 px = {mpp:.3f} m | sim speed = {cs.speed:.1f} px/s ≈ {cs.speed*mpp*3.6:.1f} km/h "
    f"(target cruise {target_kmh:.1f} km/h)"
)

# Metrics logging cadence
_metrics_accum = 0.0
_metrics_period = float(getattr(cs, "metrics_log_period_s", 1.0))


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

    # Drones
    drones.move(dt)
    drones.draw(screen, dt_since_last_frame=dt)

    # Periodic METRICS logging (sim time, IRL time, drone speeds, fire perimeter & area)
    _metrics_accum += dt
    if _metrics_accum >= _metrics_period:
        _metrics_accum = 0.0

        # Time (sim + IRL)
        sim_t = sim_fire.sim_t
        irl_txt = irl_str(sim_t)

        # Drone instantaneous speeds (km/h)
        kmhs = drones.get_last_speeds_kmh()     # list of 4 floats

        # Fire metrics (global)
        fm = sim_fire.compute_metrics(drones.m_per_px)
        log_bus.push(
            "[METRICS] "
            f"sim={sim_t:6.2f}s | IRL≈{irl_txt} | "
            f"Speed km/h D1:{kmhs[0]:.1f} D2:{kmhs[1]:.1f} D3:{kmhs[2]:.1f} D4:{kmhs[3]:.1f} | "
            f"Perimeter {fm['perimeter_m']:.0f} m | "
            f"Burning {fm['burning_area_ha']:.3f} ha | "
            f"Scorched {fm['scorched_area_ha']:.3f} ha"
        )

    pygame.display.flip()

pygame.quit()
