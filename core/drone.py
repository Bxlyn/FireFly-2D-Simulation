# core/drone.py
import math
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
    # shrink by FOV radius so the FOV circle stays inside
    left   = rect.left   + margin
    right  = rect.right  - margin
    top    = rect.top    + margin
    bottom = rect.bottom - margin
    # repair if FOV is huge
    if right < left:   left, right   = right, left
    if bottom < top:   top, bottom   = bottom, top
    safe = pygame.Rect(int(left), int(top), int(right - left), int(bottom - top))
    return safe

# ---------- drone ----------

class Drone:
    """
    4 drones:
      - spawn spaced inside compost (one per compost quadrant)
      - go to sector entry
      - sweep sector with optimal parallel strips (spacing s = 2*r * factor, factor<=1)
      - orientation chosen along the LONGER side to minimize turns/overhead
      - motion clamped by FOV radius so coverage stays inside each sector
      - smooth start after delay (consumes leftover dt)
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

        # Optimal strip spacing (exact 2r with optional tiny overlap)
        self.opt_stride_factor = float(getattr(cs, "opt_stride_factor", 1.0))
        self.strip_spacing = max(1.0, 2.0 * self.fov_radius * self.opt_stride_factor)

        self.speed = float(speed)  # units/sec

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
            pygame.Rect(0,      0,      w // 2, h // 2),  # 0: TL
            pygame.Rect(w // 2, 0,      w // 2, h // 2),  # 1: TR
            pygame.Rect(0,      h // 2, w // 2, h // 2),  # 2: BL
            pygame.Rect(w // 2, h // 2, w // 2, h // 2),  # 3: BR
        ]

        # Safe rects (FOV-contained)
        self.safe_rects = [_sector_safe_rect(r, self.fov_radius) for r in self.sectors]
        self.sector_centers = [pygame.Vector2(r.center) for r in self.sectors]

        # Spawn four drones around a ring inside the compost (one per slice)
        spawn_ring = max(self.radius + 4, min(compost_radius - self.radius - 4, compost_radius * 0.66))
        spawn_angles = [135, 45, 225, 315]  # TL, TR, BL, BR (match sectors)
        self.positions = []
        for ang in spawn_angles:
            offset = pygame.Vector2(spawn_ring, 0).rotate(ang)
            self.positions.append(self.world_center + offset)

        # State per drone
        # phase: 0 delay/approach, 2 sweeping
        self.phase = [0] * 4
        self.current_wp_idx = [0] * 4
        self.start_delay = float(start_delay)
        self._elapsed = 0.0

        # Build optimal (orientation-aware) sweep paths for each sector
        self.sweep_paths = []
        for safe in self.safe_rects:
            self.sweep_paths.append(self._build_optimal_sweep_path(safe))

        # Pre-allocate alpha surface for FOV (screen-sized; one blit per drone)
        self._fov_surface = pygame.Surface((w, h), pygame.SRCALPHA)

    # ---------- path generation (optimal parallel strips) ----------

    def _build_optimal_sweep_path(self, safe: pygame.Rect):
        """
        Parallel-strip coverage with spacing s = 2r * factor (factor<=1),
        oriented along the LONGER side of the safe rect.
        """
        left, top, width, height = float(safe.left), float(safe.top), float(safe.width), float(safe.height)
        right  = left + width
        bottom = top  + height
        s = self.strip_spacing

        path = []

        if height >= width:
            # Move along Y (vertical lanes), step across X by s
            # Build lane abscissas
            xs = [left + k * s for k in range(int(max(0, math.floor(width / s))) + 1)]
            if xs[-1] < right - 1e-6:
                xs.append(right)  # ensure last lane at the far edge

            toggle = False
            for x in xs:
                if not toggle:
                    path.append(pygame.Vector2(x, top))
                    path.append(pygame.Vector2(x, bottom))
                else:
                    path.append(pygame.Vector2(x, bottom))
                    path.append(pygame.Vector2(x, top))
                toggle = not toggle
        else:
            # Move along X (horizontal lanes), step across Y by s
            ys = [top + k * s for k in range(int(max(0, math.floor(height / s))) + 1)]
            if ys[-1] < bottom - 1e-6:
                ys.append(bottom)

            toggle = False
            for y in ys:
                if not toggle:
                    path.append(pygame.Vector2(left,  y))
                    path.append(pygame.Vector2(right, y))
                else:
                    path.append(pygame.Vector2(right, y))
                    path.append(pygame.Vector2(left,  y))
                toggle = not toggle

        # Safety: degenerate case
        if not path:
            path = [pygame.Vector2((left + right) / 2, (top + bottom) / 2)]

        return path

    # ---------- drawing ----------

    def _draw_fov_circle(self, surface: pygame.Surface, center: pygame.Vector2):
        # Clear temp surface (alpha)
        self._fov_surface.fill((0, 0, 0, 0))
        # Draw translucent filled circle
        color = (self.color[0], self.color[1], self.color[2], cs.fov_alpha)
        pygame.draw.circle(self._fov_surface, color, (int(center.x), int(center.y)), int(self.fov_radius))
        # Blit under the drone
        surface.blit(self._fov_surface, (0, 0))

    def draw(self, surface):
        # (Optional) visualize sector bounds
        for r in self.sectors:
            pygame.draw.rect(surface, cs.dgreen, r, 1)

        # Optional: show sweep guides & safe rects
        if getattr(cs, "show_sweep_guides", False):
            guide_color = (255, 255, 255)
            for path in self.sweep_paths:
                for i in range(1, len(path)):
                    pygame.draw.line(surface, guide_color,
                                     (int(path[i - 1].x), int(path[i - 1].y)),
                                     (int(path[i].x),     int(path[i].y)), 1)
            for safe in self.safe_rects:
                pygame.draw.rect(surface, (255, 255, 0), safe, 1)

        # Draw FOV first (under the drones)
        for pos in self.positions:
            self._draw_fov_circle(surface, pos)

        # Draw drones on top
        for pos in self.positions:
            pygame.draw.circle(surface, self.color, (int(pos.x), int(pos.y)), int(self.radius))

    # ---------- update ----------

    def move(self, dt: float):
        # Smooth delay: consume leftover dt when delay ends this frame
        if self._elapsed < self.start_delay:
            remaining = self.start_delay - self._elapsed
            if dt <= remaining:
                self._elapsed += dt
                return
            else:
                self._elapsed = self.start_delay
                dt -= remaining  # use leftover time this frame

        step = self.speed * dt
        w, h = cs.screen_width, cs.screen_height

        for i in range(4):
            pos = self.positions[i]

            # Approach to first strip entry (screen-clamped only to avoid snap)
            if self.phase[i] == 0:
                entry = self.sweep_paths[i][0]
                new_pos = move_towards(pos, entry, step)
                _screen_clamp(new_pos, self.fov_radius, w, h)

                # enter sweeping once inside the safe rect
                if self.safe_rects[i].collidepoint(new_pos.x, new_pos.y):
                    self.phase[i] = 2
                    self.current_wp_idx[i] = 1 if len(self.sweep_paths[i]) > 1 else 0

                self.positions[i] = new_pos
                continue

            # Sweeping (serpentine)
            path = self.sweep_paths[i]
            wp_i = self.current_wp_idx[i]
            target = path[wp_i]

            new_pos = move_towards(pos, target, step)
            self.positions[i] = new_pos

            # Advance waypoint on arrival; loop to rescan sector
            if new_pos.distance_to(target) == 0:
                self.current_wp_idx[i] = (wp_i + 1) % len(path)

            # Clamp by FOV radius to keep coverage inside the sector
            r = self.sectors[i]
            m = self.fov_radius
            self.positions[i].x = max(r.left + m,  min(self.positions[i].x, r.right  - m))
            self.positions[i].y = max(r.top  + m,  min(self.positions[i].y, r.bottom - m))
