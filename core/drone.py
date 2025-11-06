import math
import pygame
import configs.settings as cs

# Helper: move a point toward a target by at most 'max_step'
def move_towards(p: pygame.Vector2, target: pygame.Vector2, max_step: float) -> pygame.Vector2:
    diff = target - p
    dist = diff.length()
    if dist <= max_step or dist == 0:
        return target
    return p + diff.normalize() * max_step

class Drone:
    """
    4 drones:
      - spawn spaced inside compost (one per compost quadrant)
      - go to sector
      - sweep sector in parallel tracks (boustrophedon) using FOV circle radius
      - motion clamped by FOV radius so coverage stays inside each sector
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

        # Spawn four drones around a ring inside the compost (one per slice)
        spawn_ring = max(self.radius + 4,
                         min(compost_radius - self.radius - 4, compost_radius * 0.66))
        spawn_angles = [135, 45, 225, 315]  # TL, TR, BL, BR (match sectors)
        self.positions = []
        for ang in spawn_angles:
            offset = pygame.Vector2(spawn_ring, 0).rotate(ang)
            self.positions.append(self.world_center + offset)

        # State per drone
        # phase: 0 delay, 1 go-to first sweep start, 2 sweeping
        self.phase = [0] * 4
        self.current_wp_idx = [0] * 4
        self.start_delay = float(start_delay)
        self._elapsed = 0.0

        # Build boustrophedon sweep paths for each sector
        self.sweep_paths = []
        for r in self.sectors:
            self.sweep_paths.append(self._build_sweep_path(r))

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

        # Stride: distance between adjacent scanlines
        # Using fov_radius * sqrt(2) gives theoretical full cover with a circle moving orthogonally.
        # Multiply by factor <= 1 for overlap.
        stride = self.fov_radius * math.sqrt(2) * float(getattr(cs, "sweep_stride_factor", 0.9))
        stride = max(6.0, stride)  # keep sane minimum

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

        # If the last y overshot but we still have vertical space near bottom, add a final pass at bottom
        if len(path) >= 2 and path[-1].y < bottom:
            if not toggle:
                path.append(pygame.Vector2(left,  bottom))
                path.append(pygame.Vector2(right, bottom))
            else:
                path.append(pygame.Vector2(right, bottom))
                path.append(pygame.Vector2(left,  bottom))

        # Start point is the first point of the path
        return path if path else [pygame.Vector2((left+right)/2, (top+bottom)/2)]

    # ---------- drawing ----------

    def _draw_fov_circle(self, surface: pygame.Surface, center: pygame.Vector2):
        # Clear temp surface (alpha)
        self._fov_surface.fill((0, 0, 0, 0))
        # Draw translucent filled circle
        color = (self.color[0], self.color[1], self.color[2], self.fov_alpha)
        pygame.draw.circle(self._fov_surface, color,
                           (int(center.x), int(center.y)), int(self.fov_radius))
        # Blit under the drone
        surface.blit(self._fov_surface, (0, 0))

    def draw(self, surface):
        # (Optional) visualize sector bounds
        for r in self.sectors:
            pygame.draw.rect(surface, cs.dgreen, r,1)

        # Optional: draw sweep guides for debugging
        if getattr(cs, "show_sweep_guides", False):
            guide_color = (255, 255, 255)
            for path in self.sweep_paths:
                for i in range(1, len(path)):
                    pygame.draw.line(surface, guide_color,
                                     (int(path[i-1].x), int(path[i-1].y)),
                                     (int(path[i].x),   int(path[i].y)), 1)

        # Draw FOV first (under the drones)
        for pos in self.positions:
            self._draw_fov_circle(surface, pos)

        # Draw drones on top
        for pos in self.positions:
            pygame.draw.circle(surface, self.color, (int(pos.x), int(pos.y)), int(self.radius))

    # ---------- update ----------

    def move(self, dt: float):
        # Start delay at compost
        if self._elapsed < self.start_delay:
            self._elapsed += dt
            return

        step = self.speed * dt

        for i in range(4):
            pos = self.positions[i]

            # Choose current target based on phase
            if self.phase[i] == 0:
                # head to first sweep point for this sector
                target = self.sweep_paths[i][0]
                # when we reach it, start sweeping
                new_pos = move_towards(pos, target, step)
                if new_pos.distance_to(target) == 0:
                    self.phase[i] = 2
                    self.current_wp_idx[i] = 1 if len(self.sweep_paths[i]) > 1 else 0
                self.positions[i] = new_pos

            elif self.phase[i] == 2:
                path = self.sweep_paths[i]
                wp_i = self.current_wp_idx[i]
                target = path[wp_i]

                new_pos = move_towards(pos, target, step)
                self.positions[i] = new_pos

                # If we reached the waypoint, go to next; loop at end to rescan
                if new_pos.distance_to(target) == 0:
                    self.current_wp_idx[i] = (wp_i + 1) % len(path)

            # Clamp by **FOV radius** so coverage stays within the sector
            r = self.sectors[i]
            m = self.fov_radius
            self.positions[i].x = max(r.left + m,  min(self.positions[i].x, r.right  - m))
            self.positions[i].y = max(r.top  + m,  min(self.positions[i].y, r.bottom - m))
