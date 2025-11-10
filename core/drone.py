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

# ---------- drone (Monte Carlo search) ----------

class Drone:
    """
    4 drones (one per quadrant):
      - maintain a belief grid over their sector
      - Monte-Carlo choose next waypoint: sample K candidates, score = expected gain - travel cost
      - move to best candidate, update belief from FOV, diffuse, renormalize
      - keep FOV footprint fully inside sector (clamps use FOV radius)
      - smooth start after compost delay (consumes leftover dt)
    """
    def __init__(self, x, y, speed, *, start_delay, compost=None):
        # Visual/body
        self.radius = float(cs.drone_radius)
        self.color = cs.blue

        # FOV circle parameters (vertical FOV)
        self.fov_angle = float(cs.fov_angle_deg)
        self.altitude = float(cs.altitude_px)
        self.fov_radius = self.altitude * math.tan(math.radians(self.fov_angle / 2.0))
        self.fov_alpha = int(cs.fov_alpha)

        # Monte Carlo params
        self.cell = int(getattr(cs, "mc_cell_px", 16))
        self.K = int(getattr(cs, "mc_candidates", 60))
        self.replan_T = float(getattr(cs, "mc_replan_seconds", 0.7))
        self.cost_per_px = float(getattr(cs, "mc_cost_per_px", 0.0008))
        self.detect_strength = float(getattr(cs, "mc_detect_strength", 0.85))
        self.diffusion = float(getattr(cs, "mc_diffusion", 0.06))

        self.speed = float(speed)  # px/sec

        w, h = cs.screen_width, cs.screen_height
        cx, cy = w // 2, h // 2

        # World/compost center
        if compost is not None:
            self.world_center = compost.pos.copy()
            compost_radius = compost.radius
        else:
            self.world_center = pygame.Vector2(cx, cy)
            compost_radius = max(32, self.radius * 3)

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
        spawn_ring = max(self.radius + 4, min(compost_radius - self.radius - 4, compost_radius * 0.66))
        spawn_angles = [135, 45, 225, 315]  # TL, TR, BL, BR
        self.positions = []
        for ang in spawn_angles:
            offset = pygame.Vector2(spawn_ring, 0).rotate(ang)
            self.positions.append(self.world_center + offset)

        # State per drone
        self.phase = [0] * 4                 # 0: approach into sector, 2: Monte-Carlo navigation
        self.mc_target = [None] * 4          # current waypoint
        self.replan_timer = [0.0] * 4
        self.start_delay = float(start_delay)
        self._elapsed = 0.0

        # Belief grids (one per sector)
        self.grid_origin = []   # (left, top) per sector
        self.grid_dims = []     # (nx, ny) per sector
        self.belief = []        # belief[sector] is ny x nx list of floats
        for safe in self.safe_rects:
            left, top, width, height = safe.left, safe.top, safe.width, safe.height
            nx = max(1, math.ceil(width / self.cell))
            ny = max(1, math.ceil(height / self.cell))
            total = nx * ny
            # uniform initial belief
            grid = [[1.0 / total for _ in range(nx)] for _ in range(ny)]
            self.belief.append(grid)
            self.grid_origin.append((left, top))
            self.grid_dims.append((nx, ny))

        # Alpha surface for semi-transparent FOV circles
        self._fov_surface = pygame.Surface((w, h), pygame.SRCALPHA)

        # RNG
        self._rng = random.Random(1337)

    # ---------- belief utilities ----------

    def _belief_sum_in_disc(self, sector_idx: int, cx: float, cy: float, radius: float) -> float:
        """Sum belief mass inside a circle centered at (cx, cy) with given radius."""
        grid = self.belief[sector_idx]
        left0, top0 = self.grid_origin[sector_idx]
        nx, ny = self.grid_dims[sector_idx]
        c = self.cell
        r2 = radius * radius

        # bounding box in cell coordinates
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
        """Reduce belief under the current FOV and renormalize; then apply simple diffusion."""
        grid = self.belief[sector_idx]
        left0, top0 = self.grid_origin[sector_idx]
        nx, ny = self.grid_dims[sector_idx]
        c = self.cell
        r2 = radius * radius
        detect = self.detect_strength

        # 1) reduce where we looked
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

        # 2) renormalize (avoid collapse)
        if ssum <= 1e-12:
            # reset to uniform if everything went to ~0
            uniform = 1.0 / (nx * ny)
            for jy in range(ny):
                for ix in range(nx):
                    grid[jy][ix] = uniform
            ssum = 1.0
        else:
            inv = 1.0 / ssum
            for jy in range(ny):
                row = grid[jy]
                for ix in range(nx):
                    row[ix] *= inv

        # 3) diffusion (5-point stencil; small smoothing)
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
            # renormalize after diffusion
            total = sum(sum(row) for row in new_grid)
            inv = 1.0 / total
            for jy in range(ny):
                for ix in range(nx):
                    new_grid[jy][ix] *= inv
            self.belief[sector_idx] = new_grid

    # ---------- Monte Carlo target selection ----------

    def _replan_target(self, i: int):
        """Sample K candidates; pick argmax(gain - lambda * distance)."""
        safe = self.safe_rects[i]
        if safe.width <= 1 or safe.height <= 1:
            self.mc_target[i] = pygame.Vector2(safe.centerx, safe.centery)
            self.replan_timer[i] = self.replan_T
            return

        best_score = -1e30
        best_pt = None
        cur = self.positions[i]
        for _ in range(self.K):
            x = self._rng.uniform(safe.left, safe.right)
            y = self._rng.uniform(safe.top, safe.bottom)
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
                    # red-ish proportional to probability
                    alpha = int(min(255, amax * (p / max_p)))
                    if alpha <= 0: 
                        continue
                    rect = pygame.Rect(left0 + ix * self.cell, top0 + jy * self.cell, self.cell, self.cell)
                    overlay.fill((255, 0, 0, alpha), rect)
        surface.blit(overlay, (0, 0))

    def draw(self, surface):
        # Sector outlines
        for r in self.sectors:
            pygame.draw.rect(surface, cs.dgreen, r, 1)
        # Belief heatmap (optional)
        self._draw_belief_heatmap(surface)
        # FOV under drones
        for pos in self.positions:
            self._draw_fov_circle(surface, pos)
        # Drone bodies
        for pos in self.positions:
            pygame.draw.circle(surface, self.color, (int(pos.x), int(pos.y)), int(self.radius))

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

            # First time we need a target: pick one
            if self.phase[i] == 0 and self.mc_target[i] is None:
                self._replan_target(i)

            # Approach phase (only screen clamp to avoid snap), until we're inside safe rect
            if self.phase[i] == 0:
                entry = self.mc_target[i]
                new_pos = move_towards(pos, entry, step)
                _screen_clamp(new_pos, self.fov_radius, W, H)
                if self.safe_rects[i].collidepoint(new_pos.x, new_pos.y):
                    self.phase[i] = 2
                self.positions[i] = new_pos

                # Observation & belief update at the new position
                self._observation_update(i, self.positions[i].x, self.positions[i].y, self.fov_radius)
                continue

            # Monte Carlo navigation inside sector
            target = self.mc_target[i]
            new_pos = move_towards(pos, target, step)
            self.positions[i] = new_pos

            # Keep FOV inside sector
            r = self.sectors[i]
            m = self.fov_radius
            self.positions[i].x = max(r.left + m,  min(self.positions[i].x, r.right  - m))
            self.positions[i].y = max(r.top  + m,  min(self.positions[i].y, r.bottom - m))

            # Observation & belief update at the new position
            self._observation_update(i, self.positions[i].x, self.positions[i].y, self.fov_radius)

            # Replan when we reach target or timer fires
            self.replan_timer[i] -= dt
            arrived = self.positions[i].distance_to(target) <= max(2.0, self.radius)
            if arrived or self.replan_timer[i] <= 0.0:
                self._replan_target(i)
