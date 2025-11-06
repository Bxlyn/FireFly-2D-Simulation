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
      - go to their sector center
      - patrol sector perimeter
      - draw translucent circular FOV footprint (vertical FOV)
      - motion clamped by FOV radius so coverage stays in sector
    """
    def __init__(self, x, y, speed, *, start_delay, compost=None):
        # Visual/body
        self.radius = float(cs.drone_radius)
        self.color = cs.blue

        # FOV circle parameters
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

        # Spawn four drones around a ring inside the compost (one per slice)
        spawn_ring = max(self.radius + 4,
                         min(compost_radius - self.radius - 4, compost_radius * 0.66))
        spawn_angles = [135, 45, 225, 315]  # TL, TR, BL, BR (match sectors)
        self.positions = []
        for ang in spawn_angles:
            offset = pygame.Vector2(spawn_ring, 0).rotate(ang)
            self.positions.append(self.world_center + offset)

        # State
        self.phase = [0] * 4           # 0: go-to-center, 1: patrol
        self.current_wp_idx = [0] * 4  # patrol waypoint
        self.start_delay = float(start_delay)
        self._elapsed = 0.0

        # Patrol waypoints inset by **FOV radius**
        inset = self.fov_radius + 4
        self.patrol_paths = []
        for r in self.sectors:
            left   = r.left   + inset
            right  = r.right  - inset
            top    = r.top    + inset
            bottom = r.bottom - inset
            # keep inset valid if FOV is huge
            left, right = min(left, right), max(left, right)
            top, bottom = min(top, bottom), max(top, bottom)

            path = [
                pygame.Vector2(left, top),
                pygame.Vector2(right, top),
                pygame.Vector2(right, bottom),
                pygame.Vector2(left, bottom),
            ]
            self.patrol_paths.append(path)

        # Pre-allocate alpha surface for FOV (screen-sized; one blit per drone)
        self._fov_surface = pygame.Surface((w, h), pygame.SRCALPHA)

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
            pygame.draw.rect(surface, cs.dgreen, r, 1)

        # Draw FOV first (under the drones)
        for pos in self.positions:
            self._draw_fov_circle(surface, pos)

        # Draw drones on top
        for pos in self.positions:
            pygame.draw.circle(surface, self.color, (int(pos.x), int(pos.y)), int(self.radius))

    def move(self, dt: float):
        if self._elapsed < self.start_delay:
            self._elapsed += dt
            return

        step = self.speed * dt

        for i in range(4):
            pos = self.positions[i]

            # Choose target: center first, then patrol waypoints
            if self.phase[i] == 0:
                target = self.sector_centers[i]
            else:
                path = self.patrol_paths[i]
                wp_i = self.current_wp_idx[i]
                target = path[wp_i]

            new_pos = move_towards(pos, target, step)

            # If reached the target center/waypoint, advance
            if new_pos.distance_to(target) == 0:
                if self.phase[i] == 0:
                    self.phase[i] = 1
                    self.current_wp_idx[i] = 0
                else:
                    self.current_wp_idx[i] = (self.current_wp_idx[i] + 1) % len(self.patrol_paths[i])

            self.positions[i] = new_pos

            # Clamp by **FOV radius** so coverage stays within the sector
            r = self.sectors[i]
            m = self.fov_radius
            self.positions[i].x = max(r.left + m,  min(self.positions[i].x, r.right  - m))
            self.positions[i].y = max(r.top  + m,  min(self.positions[i].y, r.bottom - m))
