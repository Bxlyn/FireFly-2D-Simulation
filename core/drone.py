import math
import random
import pygame
import configs.settings as cs


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
    left   = rect.left   + margin
    right  = rect.right  - margin
    top    = rect.top    + margin
    bottom = rect.bottom - margin
    if right < left:   left, right = right, left
    if bottom < top:   top, bottom = bottom, top
    return pygame.Rect(int(left), int(top), int(right - left), int(bottom - top))


class Drone:
    APPROACH = 0
    SEARCH   = 2
    RETURN   = 3
    RECHARGE = 4
    HOLD     = 5

    def __init__(self, x, y, speed, *, start_delay, compost=None, fire_sim=None, log_bus=None):
        self.radius = float(cs.drone_radius)
        self.color  = cs.blue

        # FOV
        self.fov_angle  = float(cs.fov_angle_deg)
        self.altitude   = float(cs.altitude_px)
        self.fov_radius = self.altitude * math.tan(math.radians(self.fov_angle / 2.0))
        self.fov_alpha  = int(cs.fov_alpha)

        # MC routing
        self.cell            = int(getattr(cs, "mc_cell_px", 16))
        self.K               = int(getattr(cs, "mc_candidates", 60))
        self.replan_T        = float(getattr(cs, "mc_replan_seconds", 0.7))
        self.cost_per_px     = float(getattr(cs, "mc_cost_per_px", 0.0008))
        self.detect_strength = float(getattr(cs, "mc_detect_strength", 0.85))
        self.diffusion       = float(getattr(cs, "mc_diffusion", 0.06))

        # Duty/Battery
        self.work_T      = float(getattr(cs, "duty_work_seconds", 25.0))
        self.charge_T    = float(getattr(cs, "duty_recharge_seconds", 3.0))
        self.jitter_frac = float(getattr(cs, "duty_jitter_frac", 0.25))
        self.return_threshold = float(getattr(cs, "battery_return_threshold", 0.20))
        self.reserve_seconds  = float(getattr(cs, "battery_reserve_seconds", 3.0))

        # HUD
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

        # Incident coordinates HUD under drone
        self._show_incident_coords = bool(getattr(cs, "show_incident_coords", True))
        self._coord_text_color = tuple(getattr(cs, "incident_coords_color", self._c_text))
        self._coord_bg_color   = tuple(getattr(cs, "incident_coords_bg", (20, 20, 20, 180)))
        self._last_incident_pos = [None] * 4  # (x, y) recorded at detection time

        # Fire sim + terminal log bus
        self.fire = fire_sim
        self._bus = log_bus  # if None, we print()

        self.speed = float(speed)

        # --- Real-world spatial scale: meters per pixel (px → m) ---
        cfg_mpp = None
        for key in ("meters_per_px", "m_per_px", "px_to_meter"):
            if hasattr(cs, key):
                val = float(getattr(cs, key))
                if val > 0.0:
                    cfg_mpp = val
                    break
        if cfg_mpp is not None:
            self.m_per_px = cfg_mpp
        else:
            cruise_kmh = float(getattr(cs, "hybrid_vtol_cruise_kmh",
                                       getattr(cs, "target_uav_speed_kmh", 72.0)))
            cruise_mps = cruise_kmh / 3.6
            self.m_per_px = cruise_mps / max(self.speed, 1e-6)

        w, h = cs.screen_width, cs.screen_height
        cx, cy = w // 2, h // 2

        # Base
        if compost is not None:
            self.world_center = compost.pos.copy()
            self.base_center  = compost.pos.copy()
            self.base_radius  = float(compost.radius)
        else:
            self.world_center = pygame.Vector2(cx, cy)
            self.base_center  = self.world_center.copy()
            self.base_radius  = max(32.0, self.radius * 3)

        # Sectors
        self.sectors = [
            pygame.Rect(0,      0,      w // 2, h // 2),
            pygame.Rect(w // 2, 0,      w // 2, h // 2),
            pygame.Rect(0,      h // 2, w // 2, h // 2),
            pygame.Rect(w // 2, h // 2, w // 2, h // 2),
        ]
        self.safe_rects = [_sector_safe_rect(r, self.fov_radius) for r in self.sectors]

        # Spawn around base (one per compost quadrant)
        spawn_ring    = max(self.radius + 4, min(self.base_radius - self.radius - 4, self.base_radius * 0.66))
        spawn_angles  = [135, 45, 225, 315]
        self.positions = [self.world_center + pygame.Vector2(spawn_ring, 0).rotate(ang) for ang in spawn_angles]

        # State
        self.phase        = [self.APPROACH] * 4
        self.mc_target    = [None] * 4
        self.replan_timer = [0.0] * 4
        self.start_delay  = float(start_delay)
        self._elapsed     = 0.0

        # Battery
        self._rng = random.Random(1337)
        def jittered_work():
            j = 1.0 + self.jitter_frac * (2.0 * self._rng.random() - 1.0)
            return max(2.0, self.work_T * j)
        self.work_period    = [jittered_work() for _ in range(4)]
        self.work_remaining = [p for p in self.work_period]
        self.recharge_timer = [0.0] * 4

        # Routing belief
        self.grid_origin = []
        self.grid_dims   = []
        self.belief      = []
        for safe in self.safe_rects:
            left, top, width, height = safe.left, safe.top, safe.width, safe.height
            nx = max(1, math.ceil(width  / self.cell))
            ny = max(1, math.ceil(height / self.cell))
            total = nx * ny
            self.belief.append([[1.0/total for _ in range(nx)] for _ in range(ny)])
            self.grid_origin.append((left, top))
            self.grid_dims.append((nx, ny))

        # UI
        self._fov_surface = pygame.Surface((w, h), pygame.SRCALPHA)
        self._font = pygame.font.Font(None, 16)
        self._alerts = []
        self._max_alerts = 8
        self._markers = []
        self._marker_ttl = float(getattr(cs, "marker_ttl", 4.0))

        # Detection debouncing
        self.det_min_frac     = float(getattr(cs, "det_min_frac", 0.01))
        self.det_confirm_time = float(getattr(cs, "det_confirm_time", 0.5))
        self._det_hold        = [0.0] * 4
        self._det_cooldowns   = [0.0] * 4

        # Incident hold
        self._holding_incident = [None] * 4

        # Sim -> IRL time scaling (minutes per sim-second)
        self._min_per_sec = float(getattr(cs, "sim_to_real_min_per_sec", 10.0 / 3.0))

        # Speed + distance tracking
        self._prev_positions   = [p.copy() for p in self.positions]
        self._last_speed_pxps  = [0.0] * 4
        self.distance_px       = [0.0, 0.0, 0.0, 0.0]  # <--- NEW: cumulative distance per drone (px)

    # ---------- utilities ----------
    def _log(self, s: str):
        self._alerts.insert(0, s)
        if len(self._alerts) > self._max_alerts:
            self._alerts.pop()
        if self._bus is not None:
            self._bus.push(s)
        else:
            print(s, flush=True)

    def _irl_str(self, sim_seconds: float) -> str:
        mins = max(0.0, sim_seconds) * self._min_per_sec
        if mins >= 90.0:
            h = int(mins // 60)
            m = int(round(mins % 60))
            return f"~{h}h {m}m"
        return f"~{mins:.1f}m"

    def _fmt_m2(self, m2: float) -> str:
        if m2 < 1000:
            return f"{m2:.0f} m²"
        return f"{m2:,.0f} m²"

    def _fmt_area_friendly(self, m2: float) -> str:
        ha = m2 / 10_000.0
        if ha >= 0.1:
            return f"{ha:.3f} ha"
        return f"{m2:.0f} m²"

    # Public speed accessor (km/h for each drone)
    def get_last_speeds_kmh(self):
        return [v * self.m_per_px * 3.6 for v in self._last_speed_pxps]

    # ---------- battery ----------
    def _battery_frac(self, i: int) -> float:
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
        if self.phase[i] in (self.RETURN, self.RECHARGE):
            return False
        if self.work_period[i] > 1e-6:
            frac = self.work_remaining[i] / self.work_period[i]
            if frac <= self.return_threshold:
                return True
        dist_home = self.positions[i].distance_to(self.base_center)
        time_home = dist_home / max(self.speed, 1e-6)
        return self.work_remaining[i] <= (time_home + self.reserve_seconds)

    # ---------- area helpers based on incident tag ----------
    def _incident_cells_and_area_by_tag(self, inc_id: int):
        """Count cells (burning or burned) with tag == inc_id; return sim counts + IRL areas."""
        if not self.fire:
            return 0, 0, 0, 0.0, 0.0
        fw = self.fire
        cell_m = fw.cell * self.m_per_px
        cell_area_m2 = cell_m * cell_m

        total = burned = burning = 0
        N = fw.GW * fw.GH
        for idx in range(N):
            if fw.tag[idx] == inc_id:
                st = fw.state[idx]
                if st == fw.BURNING:
                    burning += 1
                    total += 1
                elif st == fw.BURNED:
                    burned += 1
                    total += 1

        total_m2  = total  * cell_area_m2
        burned_m2 = burned * cell_area_m2
        return total, burned, burning, total_m2, burned_m2

    # ---------- belief ----------
    def _belief_sum_in_disc(self, sector_idx: int, cx: float, cy: float, radius: float) -> float:
        grid = self.belief[sector_idx]
        left0, top0 = self.grid_origin[sector_idx]
        nx, ny = self.grid_dims[sector_idx]
        c = self.cell; r2 = radius * radius
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
                    nsum = center; cnt = 1
                    if ix > 0:       nsum += grid[jy][ix - 1]; cnt += 1
                    if ix < nx - 1:  nsum += grid[jy][ix + 1]; cnt += 1
                    if jy > 0:       nsum += grid[jy - 1][ix]; cnt += 1
                    if jy < ny - 1:  nsum += grid[jy + 1][ix]; cnt += 1
                    new_grid[jy][ix] = (1.0 - d) * center + d * (nsum / cnt)
            total = sum(sum(row) for row in new_grid)
            inv = 1.0 / max(total, 1e-12)
            for jy in range(ny):
                for ix in range(nx):
                    new_grid[jy][ix] *= inv
            self.belief[sector_idx] = new_grid

    def _replan_target(self, i: int):
        safe = self.safe_rects[i]
        if safe.width <= 1 or safe.height <= 1:
            self.mc_target[i] = pygame.Vector2(safe.centerx, safe.centery)
            self.replan_timer[i] = self.replan_T
            return
        best_score = -1e30; best_pt = None
        cur = self.positions[i]
        for _ in range(self.K):
            x = random.uniform(safe.left, safe.right)
            y = random.uniform(safe.top,  safe.bottom)
            gain = self._belief_sum_in_disc(i, x, y, self.fov_radius)
            dist = math.hypot(x - cur.x, y - cur.y)
            score = gain - self.cost_per_px * dist
            if score > best_score:
                best_score = score; best_pt = (x, y)
        if best_pt is None:
            best_pt = (safe.centerx, safe.centery)
        self.mc_target[i] = pygame.Vector2(*best_pt)
        self.replan_timer[i] = self.replan_T

    # ---------- detection & HOLD ----------
    def _maybe_detect_and_report(self, i: int, dt: float):
        if self.fire is None or self.phase[i] == self.HOLD:
            return
        if self._det_cooldowns[i] > 0.0:
            self._det_cooldowns[i] = max(0.0, self._det_cooldowns[i] - dt)
            return

        pos = self.positions[i]
        frac, hotspots = self.fire.burning_fraction_in_disc(pos.x, pos.y, self.fov_radius)
        self._det_hold[i] = (self._det_hold[i] + dt) if (frac >= self.det_min_frac) else 0.0
        if self._det_hold[i] < self.det_confirm_time:
            return

        # Confirmed once
        self._det_hold[i] = 0.0
        self._det_cooldowns[i] = float(getattr(cs, "det_cooldown_s", 3.0))

        if hotspots:
            cx = sum(h[0] for h in hotspots) / len(hotspots)
            cy = sum(h[1] for h in hotspots) / len(hotspots)
        else:
            cx, cy = pos.x, pos.y

        inc_id, is_new = self.fire.register_incident(cx, cy)
        if is_new:
            info = self.fire.get_incident(inc_id) if self.fire else None
            det_s = 0.0
            if info:
                det_s = max(0.0, info.get("detected_t", 0.0) - info.get("ignited_t", 0.0))
            label = ["1", "2", "3", "4"][i]

            # --- Area snapshot at DETECT (local disk) ---
            try:
                r_px = self.fire._monitor_r if hasattr(self.fire, "_monitor_r") else self.fov_radius
                stats = self.fire.compute_local_metrics(cx, cy, r_px, self.m_per_px)
                cells_total = int(stats.get("footprint_cells", 0))
                m2_total = float(stats.get("footprint_area_ha", 0.0)) * 10_000.0
                m2_burned_now = float(stats.get("scorched_area_ha", 0.0)) * 10_000.0
            except Exception:
                cells_total = 0
                m2_total = m2_burned_now = 0.0

            # ---- Concise DETECT log (time-to-detect + area-at-detect) ----
            self._log(
                f"[DETECT] D{label} ({int(cx)},{int(cy)}) | "
                f"t_detect {det_s:.2f}s sim (≈{self._irl_str(det_s)}) | "
                f"area@detect {self._fmt_m2(m2_total)} (sim {cells_total} cells), "
                f"scorched {self._fmt_m2(m2_burned_now)}"
            )

            self._markers.append({"pos": pygame.Vector2(cx, cy), "ttl": self._marker_ttl})
            self._last_incident_pos[i] = (cx, cy)

            # HOLD until that cluster is fully gone
            self.phase[i] = self.HOLD
            self._holding_incident[i] = inc_id

    # ---------- drawing ----------
    def _draw_fov_circle(self, surface: pygame.Surface, center: pygame.Vector2):
        self._fov_surface.fill((0, 0, 0, 0))
        color = (self.color[0], self.color[1], self.color[2], self.fov_alpha)
        pygame.draw.circle(self._fov_surface, color, (int(center.x), int(center.y)), int(self.fov_radius))
        surface.blit(self._fov_surface, (0, 0))

    def _draw_incident_coords_under_drones(self, surface: pygame.Surface):
        if not self._show_incident_coords:
            return
        for i, pos in enumerate(self.positions):
            if self.phase[i] != self.HOLD:
                continue
            xy = self._last_incident_pos[i]
            if not xy:
                continue
            text = f"FIRE {int(xy[0])}, {int(xy[1])}"
            srf  = self._font.render(text, True, self._coord_text_color)

            # pill background (semi-transparent)
            pad_x, pad_y = 6, 3
            w, h = srf.get_width(), srf.get_height()
            x = int(pos.x - (w + 2 * pad_x) // 2)
            y = int(pos.y + self.radius + 8)

            bg = pygame.Surface((w + 2 * pad_x, h + 2 * pad_y), pygame.SRCALPHA)
            bg_col = self._coord_bg_color if len(self._coord_bg_color) == 4 else (*self._coord_bg_color, 180)
            bg.fill(bg_col)
            surface.blit(bg, (x, y))
            surface.blit(srf, (x + pad_x, y + pad_y))

    def _draw_battery_world_bars(self, surface: pygame.Surface):
        if not (self._show_hud and self._show_world_bars): return
        w = 46; h = 6
        for i, pos in enumerate(self.positions):
            f = self._battery_frac(i); col = self._battery_color(f)
            x = int(pos.x - w // 2); y = int(pos.y - self.radius - 10 - h)
            pygame.draw.rect(surface, (10, 10, 10), (x - 1, y - 1, w + 2, h + 2), border_radius=2)
            pygame.draw.rect(surface, (40, 40, 40), (x, y, w, h), border_radius=2)
            pygame.draw.rect(surface, col, (x, y, int(w * f), h), border_radius=2)

    def _draw_battery_panel(self, surface: pygame.Surface):
        if not (self._show_hud and self._show_panel): return
        x0, y0 = self._panel_pos
        W = self._panel_w; pad = 8; rows = 4
        row_h = max(self._bar_h + 10, 18)
        H = pad * 2 + rows * row_h
        panel = pygame.Surface((W, H), pygame.SRCALPHA)
        panel.fill((20, 20, 20, 180))

        labels = ["1", "2", "3", "4"]
        state_txt = { self.APPROACH:"APP", self.SEARCH:"SRCH", self.RETURN:"RET",
                      self.RECHARGE:"CHG", self.HOLD:"HOLD" }

        for i in range(4):
            y = pad + i * row_h
            txt = f"{labels[i]} {state_txt.get(self.phase[i], '?')}"
            srf = self._font.render(txt, True, self._c_text); panel.blit(srf, (8, y + 1))
            bx = 60; bw = W - bx - 12; by = y + (row_h - self._bar_h) // 2
            f = self._battery_frac(i); col = self._battery_color(f)
            pygame.draw.rect(panel, (40, 40, 40), (bx, by, bw, self._bar_h), border_radius=2)
            pygame.draw.rect(panel, col, (bx, by, int(bw * f), self._bar_h), border_radius=2)
            pct = int(round(100 * f))
            psrf = self._font.render(f"{pct}%", True, self._c_text)
            panel.blit(psrf, (bx + bw - psrf.get_width() - 2, by - 1))
        surface.blit(panel, (x0, y0))

        # Alerts (top-right)
        if self._alerts:
            pad = 8; W2 = 380; line_h = 16
            H2 = pad * 2 + line_h * min(len(self._alerts), 8)
            x1 = cs.screen_width - W2 - 12; y1 = 12
            disp = pygame.Surface((W2, H2), pygame.SRCALPHA)
            disp.fill((20, 20, 20, 180))
            title = self._font.render("Emergency Dispatch Log", True, (240,240,240))
            disp.blit(title, (8, 4))
            y = 4 + line_h
            for s in self._alerts[:8]:
                txt = self._font.render(s, True, (230,230,230))
                disp.blit(txt, (8, y)); y += line_h
            surface.blit(disp, (x1, y1))

    def _draw_detection_markers(self, surface: pygame.Surface, dt_since_last_frame: float):
        alive = []
        for m in self._markers:
            m["ttl"] -= dt_since_last_frame
            if m["ttl"] > 0.0:
                alive.append(m)
                pos = m["pos"]
                t = m["ttl"] / self._marker_ttl
                R = int(12 + 20 * (1 - t))
                pygame.draw.circle(surface, (255, 210, 0), (int(pos.x), int(pos.y)), R, 2)
                pygame.draw.circle(surface, (255,   0, 0), (int(pos.x), int(pos.y)), max(2, R // 6))
        self._markers = alive

    def draw(self, surface, dt_since_last_frame: float = 0.016):
        for r in self.sectors:
            pygame.draw.rect(surface, cs.dgreen, r, 1)
        for pos in self.positions:
            self._draw_fov_circle(surface, pos)
        for i, pos in enumerate(self.positions):
            color = cs.cyellow if self.phase[i] == self.RECHARGE else self.color
            pygame.draw.circle(surface, color, (int(pos.x), int(pos.y)), int(self.radius))
        self._draw_incident_coords_under_drones(surface)
        self._draw_detection_markers(surface, dt_since_last_frame)
        self._draw_battery_world_bars(surface)
        self._draw_battery_panel(surface)

    # ---------- update ----------
    def move(self, dt: float):
        if self._elapsed < self.start_delay:
            remain = self.start_delay - self._elapsed
            if dt <= remain:
                self._elapsed += dt; return
            self._elapsed = self.start_delay; dt -= remain

        step = self.speed * dt
        W, H = cs.screen_width, cs.screen_height

        for i in range(4):
            pos = self.positions[i]

            # If we have an incident and it's still active → keep/enter HOLD
            if self._holding_incident[i] is not None and self.phase[i] not in (self.HOLD, self.RETURN, self.RECHARGE):
                if self.fire and self.fire.incident_is_active(self._holding_incident[i]):
                    self.phase[i] = self.HOLD

            # HOLD until cluster is fully gone
            if self.phase[i] == self.HOLD:
                inc_id = self._holding_incident[i]
                active = (self.fire is not None and self.fire.incident_is_active(inc_id))
                if active:
                    # DISPATCH log when suppression becomes live (no duplicate t_detect here)
                    if self.fire:
                        info = self.fire.get_incident(inc_id)
                        if info and info.get("zone_live") and not info.get("announced_suppression", False):
                            stop_s = max(0.0, info["suppressed_t"] - info["ignited_t"])
                            label = ["1", "2", "3", "4"][i]
                            self._log(
                                f"[DISPATCH] D{label} -> ({int(info['cx'])},{int(info['cy'])}) | "
                                f"spread until stop {stop_s:.2f}s sim (≈{self._irl_str(stop_s)})"
                            )
                            self.fire.mark_incident_announced(inc_id, "suppression")
                    self.work_remaining[i] = max(0.0, self.work_remaining[i] - dt)
                    if self._should_return_now(i):
                        self.phase[i] = self.RETURN
                    continue

                else:
                    # Incident fully out: log final footprint (by tag) once
                    if self.fire:
                        info = self.fire.get_incident(inc_id)
                        if info and info.get("extinguished_t") is not None and not info.get("announced_extinguished", False):
                            base_t = info.get("suppressed_t") or info.get("detected_t") or info.get("ignited_t")
                            out_s  = max(0.0, info["extinguished_t"] - base_t)

                            total_cells, burned_cells, burning_cells, total_m2, burned_m2 = \
                                self._incident_cells_and_area_by_tag(inc_id)

                            label  = ["1", "2", "3", "4"][i]
                            self._log(
                                f"[EXTINGUISHED] D{label} ({int(info['cx'])},{int(info['cy'])}) | "
                                f"final burned area {self._fmt_m2(total_m2)} (sim {total_cells} cells) | "
                                f"out in {out_s:.2f}s after stop (≈{self._irl_str(out_s)})"
                            )
                            self.fire.mark_incident_announced(inc_id, "extinguished")
                    # Clear hold and resume search
                    self._holding_incident[i] = None
                    self.phase[i] = self.SEARCH
                    self.replan_timer[i] = 0.0
                    continue

            # RECHARGE
            if self.phase[i] == self.RECHARGE:
                self.positions[i] = self.base_center.copy()
                self.recharge_timer[i] -= dt
                if self.recharge_timer[i] <= 0.0:
                    wp = max(2.0, self.work_T * (1.0 + self.jitter_frac * (2.0 * random.random() - 1.0)))
                    self.work_period[i]    = wp
                    self.work_remaining[i] = wp
                    self.mc_target[i]      = None
                    self.phase[i]          = self.APPROACH
                continue

            # Ensure a target
            if self.mc_target[i] is None:
                self._replan_target(i)

            # RETURN
            if self.phase[i] == self.RETURN:
                target = self.base_center
                new_pos = move_towards(pos, target, step)
                _screen_clamp(new_pos, self.fov_radius, W, H)
                self.positions[i] = new_pos
                self.work_remaining[i] = max(0.0, self.work_remaining[i] - dt)
                self._maybe_detect_and_report(i, dt)
                if new_pos.distance_to(self.base_center) <= max(1.0, self.base_radius - self.radius):
                    self.phase[i] = self.RECHARGE
                    self.recharge_timer[i] = self.charge_T
                continue

            # APPROACH
            if self.phase[i] == self.APPROACH:
                entry = self.mc_target[i]
                new_pos = move_towards(pos, entry, step)
                _screen_clamp(new_pos, self.fov_radius, W, H)
                self.positions[i] = new_pos
                self._observation_update(i, new_pos.x, new_pos.y, self.fov_radius)
                self._maybe_detect_and_report(i, dt)
                if self.safe_rects[i].collidepoint(new_pos.x, new_pos.y):
                    self.phase[i] = self.SEARCH
                    self.replan_timer[i] = self.replan_T
                self.work_remaining[i] = max(0.0, self.work_remaining[i] - dt)
                if self._should_return_now(i):
                    self.phase[i] = self.RETURN
                    self.mc_target[i] = None
                continue

            # SEARCH
            if self.phase[i] == self.SEARCH:
                target = self.mc_target[i]
                new_pos = move_towards(pos, target, step)
                self.positions[i] = new_pos

                r = self.sectors[i]; m = self.fov_radius
                self.positions[i].x = max(r.left + m,  min(self.positions[i].x, r.right  - m))
                self.positions[i].y = max(r.top  + m,  min(self.positions[i].y, r.bottom - m))

                self._observation_update(i, self.positions[i].x, self.positions[i].y, self.fov_radius)
                self._maybe_detect_and_report(i, dt)

                self.replan_timer[i] -= dt
                arrived = self.positions[i].distance_to(target) <= max(2.0, self.radius)
                if arrived or self.replan_timer[i] <= 0.0:
                    self._replan_target(i)

                self.work_remaining[i] = max(0.0, self.work_remaining[i] - dt)
                if self._should_return_now(i):
                    self.phase[i] = self.RETURN
                    self.mc_target[i] = None

        # Speed + distance update (per frame)
        if dt > 1e-6:
            for i in range(4):
                disp = self.positions[i] - self._prev_positions[i]
                dlen = disp.length()
                self.distance_px[i] += dlen                 # <--- accumulate distance (px)
                self._last_speed_pxps[i] = dlen / dt
                self._prev_positions[i] = self.positions[i].copy()
        else:
            for i in range(4):
                self._prev_positions[i] = self.positions[i].copy()

    # ---------- run-end summary ----------
    def build_summary(self, fire):
        sim_time = fire.sim_t
        irl_time = self._irl_str(sim_time)

        # Pull metrics from Fire (support both *_m2 and non-suffixed names)
        det_times = getattr(fire, "det_times", [])
        detect_areas = getattr(fire, "detect_areas_m2", getattr(fire, "detect_areas", []))
        final_areas  = getattr(fire, "final_areas_m2",  getattr(fire, "final_areas",  []))

        avg_det_sim = (sum(det_times) / len(det_times)) if det_times else 0.0
        avg_det_irl = self._irl_str(avg_det_sim)
        avg_detect_area = (sum(detect_areas) / len(detect_areas)) if detect_areas else 0.0
        avg_final_area  = (sum(final_areas)  / len(final_areas))  if final_areas  else 0.0
        biggest_fire    = max(final_areas) if final_areas else 0.0

        # Totals (final areas are per-incident footprints when extinguished)
        total_burned = sum(final_areas)

        # Use a grid snapshot for "total scorched so far" (ever-burned), so it works even if you exit mid-incident
        snap = fire.compute_metrics(self.m_per_px) if hasattr(fire, "compute_metrics") else {"scorched_area_ha": 0.0}
        total_scorched = float(snap.get("scorched_area_ha", 0.0)) * 10_000.0

        # Distances
        distances_px = getattr(self, "distance_px", [0.0, 0.0, 0.0, 0.0])
        distances_km = [d * self.m_per_px / 1000.0 for d in distances_px]

        return {
            "sim_time": sim_time,
            "irl_time": irl_time,
            "fires_detected": len(det_times),
            "avg_detect_time_sim": avg_det_sim,
            "avg_detect_time_irl": avg_det_irl,
            "avg_detect_area_m2": avg_detect_area,
            "avg_final_area_m2": avg_final_area,
            "biggest_fire_m2": biggest_fire,
            "total_burned_m2": total_burned,
            "total_scorched_m2": total_scorched,
            "undetected_fires": getattr(fire, "undetected_count", 0),
            "drone_avg_speed_kmh": sum(self.get_last_speeds_kmh()) / 4.0,
            "drone_distances_km": distances_km,
            "dispatch_events": getattr(fire, "dispatch_count", 0),
            "extinguished_events": getattr(fire, "extinguished_count", 0),
            "user_ignitions": getattr(fire, "user_ignitions", 0),
        }
