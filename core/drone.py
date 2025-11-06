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
    safe = rect.inflate(-2 * margin, -2 * margin)
    # if FOV is huge, keep at least a point centered
    if safe.width < 1 or safe.height < 1:
        cx, cy = rect.center
        safe.width = max(1, safe.width)
        safe.height = max(1, safe.height)
        safe.center = (cx, cy)
    return safe

# ---------- drone ----------

class Drone:
    """
    4 drones:
      - spawn spaced inside compost (one per compost quadrant)
      - go to sector entry
      - sweep sector in parallel tracks (boustrophedon) using FOV circle radius
      - motion clamped by FOV radius so coverage stays inside each sector
      - smooth start after delay (no first-frame snap)
    """
    def __init__(self, x, y, speed, *, start_delay, compost=None):
        # Visual/body
        self.radius = float(cs.drone_radius)
        self.color = cs.blue

        # FOV circle parameters (vertical FOV)
        self.fov_angle = float(cs.fov_angle_deg)
        self.altitude = float(cs.altitude_px)
        # footprint radius from vertical FOV
        self.fov_radius = self.altitude * math.tan(math.radians(self.fov_angle / 2.0))
        self.fov_alpha = int(cs.fov_alpha)

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
        self.sector_centers = [pygame.Vector2(r.center) for r in self.sectors]

        # spawn four drones around a ring inside the compost (one per slice)
        spawn_ring = max(self.radius + 4, min(compost_radius - self.radius - 4, compost_radius * 0.66))
        spawn_angles = [135, 45, 225, 315]  # TL, TR, BL, BR (match sectors)
        self.positions = []
        for ang in spawn_angles:
            offset = pygame.Vector2(spawn_ring, 0).rotate(ang)
            self.positions.append(self.world_center + offset)

        # state per drone
        # phase: 0 delay/approach, 2 sweeping (we skip a separate 1 to keep it simple)
        self.phase = [0] * 4
        self.current_wp_idx = [0] * 4
        self.start_delay = float(start_delay)
        self._elapsed = 0.0

        # sweep paths and safe rects
        self.sweep_paths = []
        for r in self.sectors:
            self.sweep_paths.append(self._build_sweep_path(r))

        self.safe_rects = [_sector_safe_rect(r, self.fov_radius) for r in self.sectors]

        # Pre-allocate alpha surface for FOV (screen-sized; one blit per drone)
        self._fov_surface = pygame.Surface((w, h), pygame.SRCALPHA)

    # ---------- path generation ----------

    def _build_sweep_path(self, rect: pygame.Rect):
        """
        Create left-right & right-left tracks that fill the rect,
        keeping the FOV disk fully inside (inset by fov_radius).
        Vertical spacing (stride) derived from fov_radius.
        """
        inset = self.fov_radius + 4
        left   = rect.left   + inset
        right  = rect.right  - inset
        top    = rect.top    + inset
        bottom = rect.bottom - inset

        # Guard against extreme FOVs
        if left > right:  left, right = right, left
        if top > bottom:  top, bottom = bottom, top

        # stride between adjacent scanlines
        stride = self.fov_radius * math.sqrt(2) * float(getattr(cs, "sweep_stride_factor", 0.9))
        stride = max(6.0, stride)  # sane minimum

        y = top
        path = []
        toggle = False  # False => L->R, True => R->L

        while y <= bottom:
            if not toggle:
                path.append(pygame.Vector2(left,  y))
                path.append(pygame.Vector2(right, y))
            else:
                path.append(pygame.Vector2(right, y))
                path.append(pygame.Vector2(left,  y))
            y += stride
            toggle = not toggle

        # Ensure a final pass at bottom if needed
        if len(path) >= 2 and path[-1].y < bottom:
            if not toggle:
                path.append(pygame.Vector2(left,  bottom))
                path.append(pygame.Vector2(right, bottom))
            else:
                path.append(pygame.Vector2(right, bottom))
                path.append(pygame.Vector2(left,  bottom))

        return path if path else [pygame.Vector2((left + right) / 2, (top + bottom) / 2)]

    # ---------- drawing ----------

    def _draw_fov_circle(self, surface: pygame.Surface, center: pygame.Vector2):
        # Clear temp surface (alpha)
        self._fov_surface.fill((0, 0, 0, 0))
        # Draw translucent filled circle
        color = (self.color[0], self.color[1], self.color[2], self.fov_alpha)
        pygame.draw.circle(self._fov_surface, color, (int(center.x), int(center.y)), int(self.fov_radius))
        # Blit under the drone
        surface.blit(self._fov_surface, (0, 0))

    def draw(self, surface):
        # (Optional) visualize sector bounds
        for r in self.sectors:
            pygame.draw.rect(surface, cs.dgreen, r, 1)

        # Optional: sweep guides & safe rects
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
                dt -= remaining  # use the leftover time this frame

        step = self.speed * dt
        w, h = cs.screen_width, cs.screen_height

        for i in range(4):
            pos = self.positions[i]

            # Approach phase (to first sweep entry point), using screen clamp only
            if self.phase[i] == 0:
                entry = self.sweep_paths[i][0]
                new_pos = move_towards(pos, entry, step)

                # avoid first-frame snap: only screen clamp here
                _screen_clamp(new_pos, self.fov_radius, w, h)

                # enter sweeping once inside sector's safe rect
                if self.safe_rects[i].collidepoint(new_pos.x, new_pos.y):
                    self.phase[i] = 2
                    self.current_wp_idx[i] = 1 if len(self.sweep_paths[i]) > 1 else 0

                self.positions[i] = new_pos
                continue

            # Sweeping phase
            path = self.sweep_paths[i]
            wp_i = self.current_wp_idx[i]
            target = path[wp_i]

            new_pos = move_towards(pos, target, step)
            self.positions[i] = new_pos

            # Advance waypoint on arrival; loop to rescan sector
            if new_pos.distance_to(target) == 0:
                self.current_wp_idx[i] = (wp_i + 1) % len(path)

            # Clamp by FOV radius to keep full coverage inside the sector
            r = self.sectors[i]
            m = self.fov_radius
            self.positions[i].x = max(r.left + m,  min(self.positions[i].x, r.right  - m))
            self.positions[i].y = max(r.top  + m,  min(self.positions[i].y, r.bottom - m))
