# core/drone.py
import math
import random
import pygame
import configs.settings as cs

# ---------- helpers ----------

def move_towards(p: pygame.Vector2, target: pygame.Vector2, max_step: float) -> pygame.Vector2:
    diff = target - p
    dist = diff.length()
    if dist <= max_step or dist == 0:
        return target
    return p + diff.normalize() * max_step

def _screen_clamp(pos: pygame.Vector2, margin: float, w: int, h: int):
    pos.x = max(margin, min(pos.x, w - margin))
    pos.y = max(margin, min(pos.y, h - margin))
    return pos

def _sector_safe_rect(rect: pygame.Rect, margin: float) -> pygame.Rect:
    # shrink by FOV radius so the FOV circle stays inside the sector
    left   = rect.left   + margin
    right  = rect.right  - margin
    top    = rect.top    + margin
    bottom = rect.bottom - margin
    if right < left:   left, right = right, left
    if bottom < top:   top, bottom = bottom, top
    return pygame.Rect(int(left), int(top), int(right - left), int(bottom - top))

# ---------- drone (Monte Carlo search + periodic recharge + battery HUD + low-batt RTB) ----------

class Drone:
    """
    4 drones (one per quadrant):
      - Monte Carlo search on a belief grid
      - periodic RETURN to compost and RECHARGE for a few seconds
      - returns early when battery is LOW (threshold or time-to-base + reserve)
      - battery HUD (bar above each drone + top-left panel)
      - smooth start after compost delay; FOV circle drawn
    """

    # States
    APPROACH = 0
    SEARCH   = 2
    RETURN   = 3
    RECHARGE = 4

    def __init__(self, x, y, speed, *, start_delay, compost=None):
        # Visual/body
        self.radius = float(cs.drone_radius)
        self.color = cs.blue

        # FOV circle parameters (vertical FOV)
        self.fov_angle  = float(cs.fov_angle_deg)
        self.altitude   = float(cs.altitude_px)
        self.fov_radius = self.altitude * math.tan(math.radians(self.fov_angle / 2.0))
        self.fov_alpha  = int(cs.fov_alpha)

        # Monte Carlo params
        self.cell            = int(getattr(cs, "mc_cell_px", 16))
        self.K               = int(getattr(cs, "mc_candidates", 60))
        self.replan_T        = float(getattr(cs, "mc_replan_seconds", 0.7))
        self.cost_per_px     = float(getattr(cs, "mc_cost_per_px", 0.0008))
        self.detect_strength = float(getattr(cs, "mc_detect_strength", 0.85))
        self.diffusion       = float(getattr(cs, "mc_diffusion", 0.06))

        # Duty cycle (recharge)
        self.work_T      = float(getattr(cs, "duty_work_seconds", 25.0))
        self.charge_T    = float(getattr(cs, "duty_recharge_seconds", 3.0))  # 2..5s ok
        self.jitter_frac = float(getattr(cs, "duty_jitter_frac", 0.25))

        # Low-battery return
        self.return_threshold = float(getattr(cs, "battery_return_threshold", 0.20))
        self.reserve_seconds  = float(getattr(cs, "battery_reserve_seconds", 3.0))

        # HUD toggles & style
        self._show_hud        = bool(getattr(cs, "show_battery_hud", True))
        self._show_world_bars = bool(getattr(cs, "battery_world_bars", True))
        self._show_panel      = bool(getattr(cs, "battery_panel", True))
        self._panel_pos       = tuple(getattr(cs, "battery_panel_pos", (12, 12)))
        self._panel_w         = int(getattr(cs, "battery_panel_width", 240))
        self._bar_h           = int(getattr(cs, "battery_bar_h", 10))
        self._t_low           = float(getattr(cs, "battery_low_threshold", 0.20))
        self._t_med           = float(getattr(cs, "battery_med_threshold", 0.50))
        self._c_low           = tuple(getattr(cs, "battery_low_color",  (220, 70, 60)))
        self._c_med           = tuple(getattr(cs, "battery_med_color",  (230, 200, 40)))
        self._c_high          = tuple(getattr(cs, "battery_high_color", (60, 200, 90)))
        self._c_text          = tuple(getattr(cs, "hud_text_color",     (240, 240, 240)))

        self.speed = float(speed)  # px/sec

        w, h = cs.screen_width, cs.screen_height
        cx, cy = w // 2, h // 2

        # World/compost center
        if compost is not None:
            self.world_center = compost.pos.copy()
            self.base_center  = compost.pos.copy()
            self.base_radius  = float(compost.radius)
        else:
            self.world_center = pygame.Vector2(cx, cy)
            self.base_center  = self.world_center.copy()
            self.base_radius  = max(32.0, self.radius * 3)

        # Define quadrants (TL, TR, BL, BR)
        self.sectors = [
            pygame.Rect(0,      0,      w // 2, h // 2),  # 0
            pygame.Rect(w // 2, 0,      w // 2, h // 2),  # 1
            pygame.Rect(0,      h // 2, w // 2, h // 2),  # 2
            pygame.Rect(w // 2, h // 2, w // 2, h // 2),  # 3
        ]

        # Safe rects: inset so FOV disk stays inside
        self.safe_rects = [_sector_safe_rect(r, self.fov_radius) for r in self.sectors]

        # Spawn four drones spaced inside compost (one per compost slice)
        spawn_ring    = max(self.radius + 4, min(self.base_radius - self.radius - 4, self.base_radius * 0.66))
        spawn_angles  = [135, 45, 225, 315]  # TL, TR, BL, BR
        self.positions = []
        for ang in spawn_angles:
            offset = pygame.Vector2(spawn_ring, 0).rotate(ang)
            self.positions.append(self.world_center + offset)

        # State per drone
        self.phase         = [self.APPROACH] * 4
        self.mc_target     = [None] * 4
        self.replan_timer  = [0.0] * 4
        self.start_delay   = float(start_delay)
        self._elapsed      = 0.0

        # Battery model (time-based)
        self._rng = random.Random(1337)
        def jittered_work():
            j = 1.0 + self.jitter_frac * (2.0 * self._rng.random() - 1.0)  # in [1-j, 1+j]
            return max(2.0, self.work_T * j)

        self.work_period    = [jittered_work() for _ in range(4)]   # full duration when battery=100%
        self.work_remaining = [p for p in self.work_period]         # counts down while away
        self.recharge_timer = [0.0] * 4                             # counts down while charging

        # Belief grids (one per sector, uniform init)
        self.grid_origin = []   # (left, top) per sector
        self.grid_dims   = []   # (nx, ny) per sector
        self.belief      = []   # ny x nx floats
        for safe in self.safe_rects:
            left, top, width, height = safe.left, safe.top, safe.width, safe.height
            nx = max(1, math.ceil(width  / self.cell))
            ny = max(1, math.ceil(height / self.cell))
            total = nx * ny
            grid = [[1.0 / total for _ in range(nx)] for _ in range(ny)]
            self.belief.append(grid)
            self.grid_origin.append((left, top))
            self.grid_dims.append((nx, ny))

        # Surfaces / font
        self._fov_surface = pygame.Surface((w, h), pygame.SRCALPHA)
        self._font = pygame.font.Font(None, 16)

    # ---------- battery helpers ----------

    def _battery_frac(self, i: int) -> float:
        """0..1 fraction of battery for HUD."""
        if self.phase[i] == self.RECHARGE:
            if self.charge_T <= 1e-6: return 1.0
            return max(0.0, min(1.0, 1.0 - self.recharge_timer[i] / self.charge_T))
        if self.work_period[i] <= 1e-6: return 0.0
        return max(0.0, min(1.0, self.work_remaining[i] / self.work_period[i]))

    def _battery_color(self, f: float):
        if f <= self._t_low:  return self._c_low
        if f <= self._t_med:  return self._c_med
        return self._c_high

    def _should_return_now(self, i: int) -> bool:
        """Return if battery fraction below threshold OR
           remaining time insufficient to reach base plus reserve."""
        if self.phase[i] in (self.RETURN, self.RECHARGE):
            return False
        # fraction rule
        if self.work_period[i] > 1e-6:
            frac = self.work_remaining[i] / self.work_period[i]
            if frac <= self.return_threshold:
                return True
        # time-to-base rule
        dist_home = self.positions[i].distance_to(self.base_center)
        time_home = dist_home / max(self.speed, 1e-6)
        return self.work_remaining[i] <= (time_home + self.reserve_seconds)

    # ---------- belief utilities ----------

    def _belief_sum_in_disc(self, sector_idx: int, cx: float, cy: float, radius: float) -> float:
        grid = self.belief[sector_idx]
        left0, top0 = self.grid_origin[sector_idx]
        nx, ny = self.grid_dims[sector_idx]
        c = self.cell
        r2 = radius * radius

        x0 = max(0, int((cx - radius - left0) // c))
        x1 = min(nx - 1, int((cx + radius - left0) // c))
        y0 = max(0, int((cy - radius - top0) // c))
        y1 = min(ny - 1, int((cy + radius - top0) // c))

        total = 0.0
        for jy in range(y0, y1 + 1):
            cy_cell = top0 + (jy + 0.5) * c
            dy2 = (cy_cell - cy) * (cy_cell - cy)
            for ix in range(x0, x1 + 1):
                cx_cell = left0 + (ix + 0.5) * c
                dx = cx_cell - cx
                if dx * dx + dy2 <= r2:
                    total += grid[jy][ix]
        return total

    def _observation_update(self, sector_idx: int, cx: float, cy: float, radius: float):
        grid = self.belief[sector_idx]
        left0, top0 = self.grid_origin[sector_idx]
        nx, ny = self.grid_dims[sector_idx]
        c = self.cell
        r2 = radius * radius
        detect = self.detect_strength

        ssum = 0.0
        for jy in range(ny):
            cy_cell = top0 + (jy + 0.5) * c
            dy2 = (cy_cell - cy) * (cy_cell - cy)
            row = grid[jy]
            for ix in range(nx):
                cx_cell = left0 + (ix + 0.5) * c
                dx = cx_cell - cx
                if dx * dx + dy2 <= r2:
                    row[ix] *= (1.0 - detect)
                ssum += row[ix]

        if ssum <= 1e-12:
            uniform = 1.0 / (nx * ny)
            for jy in range(ny):
                for ix in range(nx):
                    grid[jy][ix] = uniform
        else:
            inv = 1.0 / ssum
            for jy in range(ny):
                row = grid[jy]
                for ix in range(nx):
                    row[ix] *= inv

        d = self.diffusion
        if d > 0.0:
            new_grid = [[0.0 for _ in range(nx)] for _ in range(ny)]
            for jy in range(ny):
                for ix in range(nx):
                    center = grid[jy][ix]
                    nsum = center
                    cnt = 1
                    if ix > 0:       nsum += grid[jy][ix - 1]; cnt += 1
                    if ix < nx - 1:  nsum += grid[jy][ix + 1]; cnt += 1
                    if jy > 0:       nsum += grid[jy - 1][ix]; cnt += 1
                    if jy < ny - 1:  nsum += grid[jy + 1][ix]; cnt += 1
                    avg = nsum / cnt
                    new_grid[jy][ix] = (1.0 - d) * center + d * avg
            total = sum(sum(row) for row in new_grid)
            inv = 1.0 / max(total, 1e-12)
            for jy in range(ny):
                for ix in range(nx):
                    new_grid[jy][ix] *= inv
            self.belief[sector_idx] = new_grid

    # ---------- Monte Carlo target selection ----------

    def _replan_target(self, i: int):
        safe = self.safe_rects[i]
        if safe.width <= 1 or safe.height <= 1:
            self.mc_target[i] = pygame.Vector2(safe.centerx, safe.centery)
            self.replan_timer[i] = self.replan_T
            return

        best_score = -1e30
        best_pt = None
        cur = self.positions[i]
        for _ in range(self.K):
            x = random.uniform(safe.left, safe.right)
            y = random.uniform(safe.top, safe.bottom)
            gain = self._belief_sum_in_disc(i, x, y, self.fov_radius)
            dist = math.hypot(x - cur.x, y - cur.y)
            score = gain - self.cost_per_px * dist
            if score > best_score:
                best_score = score
                best_pt = (x, y)

        if best_pt is None:
            best_pt = (safe.centerx, safe.centery)

        self.mc_target[i] = pygame.Vector2(best_pt[0], best_pt[1])
        self.replan_timer[i] = self.replan_T

    # ---------- drawing ----------

    def _draw_fov_circle(self, surface: pygame.Surface, center: pygame.Vector2):
        self._fov_surface.fill((0, 0, 0, 0))
        color = (self.color[0], self.color[1], self.color[2], self.fov_alpha)
        pygame.draw.circle(self._fov_surface, color, (int(center.x), int(center.y)), int(self.fov_radius))
        surface.blit(self._fov_surface, (0, 0))

    def _draw_belief_heatmap(self, surface: pygame.Surface):
        if not getattr(cs, "show_belief_heatmap", False):
            return
        overlay = pygame.Surface((cs.screen_width, cs.screen_height), pygame.SRCALPHA)
        max_p = 0.0
        for grid in self.belief:
            for row in grid:
                for p in row:
                    if p > max_p: max_p = p
        if max_p <= 0: return
        amax = int(getattr(cs, "heatmap_alpha", 120))
        for si, grid in enumerate(self.belief):
            left0, top0 = self.grid_origin[si]
            nx, ny = self.grid_dims[si]
            for jy in range(ny):
                for ix in range(nx):
                    p = grid[jy][ix]
                    alpha = int(min(255, amax * (p / max_p)))
                    if alpha <= 0: 
                        continue
                    rect = pygame.Rect(left0 + ix * self.cell, top0 + jy * self.cell, self.cell, self.cell)
                    overlay.fill((255, 0, 0, alpha), rect)
        surface.blit(overlay, (0, 0))

    def _draw_battery_world_bars(self, surface: pygame.Surface):
        if not (self._show_hud and self._show_world_bars): return
        w = 46
        h = 6
        for i, pos in enumerate(self.positions):
            f = self._battery_frac(i)
            col = self._battery_color(f)
            x = int(pos.x - w // 2)
            y = int(pos.y - self.radius - 10 - h)
            pygame.draw.rect(surface, (10, 10, 10), (x - 1, y - 1, w + 2, h + 2), border_radius=2)
            pygame.draw.rect(surface, (40, 40, 40), (x, y, w, h), border_radius=2)
            pygame.draw.rect(surface, col, (x, y, int(w * f), h), border_radius=2)

    def _draw_battery_panel(self, surface: pygame.Surface):
        if not (self._show_hud and self._show_panel): return
        x0, y0 = self._panel_pos
        W = self._panel_w
        pad = 8
        rows = 4
        row_h = max(self._bar_h + 10, 18)
        H = pad * 2 + rows * row_h

        panel = pygame.Surface((W, H), pygame.SRCALPHA)
        panel.fill((20, 20, 20, 180))  # semi-transparent

        labels = ["TL", "TR", "BL", "BR"]
        state_txt = { self.APPROACH:"APP", self.SEARCH:"SRCH", self.RETURN:"RET", self.RECHARGE:"CHG" }

        for i in range(4):
            y = pad + i * row_h
            txt = f"{labels[i]} {state_txt.get(self.phase[i], '?')}"
            srf = self._font.render(txt, True, self._c_text)
            panel.blit(srf, (8, y + 1))

            bx = 60
            bw = W - bx - 12
            by = y + (row_h - self._bar_h) // 2
            f = self._battery_frac(i)
            col = self._battery_color(f)
            pygame.draw.rect(panel, (40, 40, 40), (bx, by, bw, self._bar_h), border_radius=2)
            pygame.draw.rect(panel, col, (bx, by, int(bw * f), self._bar_h), border_radius=2)

            pct = int(round(100 * f))
            psrf = self._font.render(f"{pct}%", True, self._c_text)
            panel.blit(psrf, (bx + bw - psrf.get_width() - 2, by - 1))

        surface.blit(panel, (x0, y0))

    def draw(self, surface):
        # Sector outlines
        for r in self.sectors:
            pygame.draw.rect(surface, cs.dgreen, r, 1)
        # Belief heatmap (optional)
        self._draw_belief_heatmap(surface)
        # FOV under drones
        for pos in self.positions:
            self._draw_fov_circle(surface, pos)
        # Drone bodies (yellow while recharging)
        for i, pos in enumerate(self.positions):
            color = cs.cyellow if self.phase[i] == self.RECHARGE else self.color
            pygame.draw.circle(surface, color, (int(pos.x), int(pos.y)), int(self.radius))
        # Battery HUD
        self._draw_battery_world_bars(surface)
        self._draw_battery_panel(surface)

    # ---------- update ----------

    def move(self, dt: float):
        # Smooth delay: consume leftover dt when delay ends this frame
        if self._elapsed < self.start_delay:
            remain = self.start_delay - self._elapsed
            if dt <= remain:
                self._elapsed += dt
                return
            else:
                self._elapsed = self.start_delay
                dt -= remain  # use leftover time this frame

        step = self.speed * dt
        W, H = cs.screen_width, cs.screen_height

        for i in range(4):
            pos = self.positions[i]

            # ----- RECHARGE -----
            if self.phase[i] == self.RECHARGE:
                self.positions[i] = self.base_center.copy()
                self.recharge_timer[i] -= dt
                if self.recharge_timer[i] <= 0.0:
                    # reset full battery with jittered period
                    wp = max(2.0, self.work_T * (1.0 + self.jitter_frac * (2.0 * random.random() - 1.0)))
                    self.work_period[i]    = wp
                    self.work_remaining[i] = wp
                    self.mc_target[i]      = None
                    self.phase[i]          = self.APPROACH
                continue

            # Ensure we have a target when not returning/charging
            if self.mc_target[i] is None:
                self._replan_target(i)

            # ----- RETURN TO BASE -----
            if self.phase[i] == self.RETURN:
                target = self.base_center
                new_pos = move_towards(pos, target, step)
                _screen_clamp(new_pos, self.fov_radius, W, H)
                self.positions[i] = new_pos

                # drain battery while flying home
                self.work_remaining[i] = max(0.0, self.work_remaining[i] - dt)

                # (Optional) observation while flying home
                self._observation_update(i, new_pos.x, new_pos.y, self.fov_radius)

                # Arrived at compost?
                if new_pos.distance_to(self.base_center) <= max(1.0, self.base_radius - self.radius):
                    self.phase[i] = self.RECHARGE
                    self.recharge_timer[i] = self.charge_T
                continue

            # ----- APPROACH (into sector safe area) -----
            if self.phase[i] == self.APPROACH:
                entry = self.mc_target[i]
                new_pos = move_towards(pos, entry, step)
                _screen_clamp(new_pos, self.fov_radius, W, H)
                self.positions[i] = new_pos

                # observation during transit
                self._observation_update(i, new_pos.x, new_pos.y, self.fov_radius)

                # enter SEARCH when inside safe rect
                if self.safe_rects[i].collidepoint(new_pos.x, new_pos.y):
                    self.phase[i] = self.SEARCH
                    self.replan_timer[i] = self.replan_T

                # drain battery while away
                self.work_remaining[i] = max(0.0, self.work_remaining[i] - dt)

                # LOW-BATTERY RETURN CHECK
                if self._should_return_now(i):
                    self.phase[i] = self.RETURN
                    self.mc_target[i] = None
                continue

            # ----- SEARCH (Monte Carlo) -----
            if self.phase[i] == self.SEARCH:
                target = self.mc_target[i]
                new_pos = move_towards(pos, target, step)
                self.positions[i] = new_pos

                # Keep FOV inside sector
                r = self.sectors[i]
                m = self.fov_radius
                self.positions[i].x = max(r.left + m,  min(self.positions[i].x, r.right  - m))
                self.positions[i].y = max(r.top  + m,  min(self.positions[i].y, r.bottom - m))

                # Observation & belief update
                self._observation_update(i, self.positions[i].x, self.positions[i].y, self.fov_radius)

                # Replan if we arrived or timer elapsed
                self.replan_timer[i] -= dt
                arrived = self.positions[i].distance_to(target) <= max(2.0, self.radius)
                if arrived or self.replan_timer[i] <= 0.0:
                    self._replan_target(i)

                # drain battery while away
                self.work_remaining[i] = max(0.0, self.work_remaining[i] - dt)

                # LOW-BATTERY RETURN CHECK
                if self._should_return_now(i):
                    self.phase[i] = self.RETURN
                    self.mc_target[i] = None
