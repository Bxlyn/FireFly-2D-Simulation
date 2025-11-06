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

def _wedge_points(center: pygame.Vector2, heading: pygame.Vector2, radius: float, angle_deg: float, samples: int = 22):
    """
    Build polygon points for a filled wedge (sector).
    center: Vector2
    heading: unit Vector2 (direction drone is facing)
    radius: FOV radius
    angle_deg: full cone angle
    samples: number of arc samples
    """
    # heading angle in degrees (pygame uses x-right, y-down)
    theta = math.degrees(math.atan2(heading.y, heading.x))
    half = angle_deg / 2.0
    start = math.radians(theta - half)
    end = math.radians(theta + half)

    points = [ (int(center.x), int(center.y)) ]
    for i in range(samples + 1):
        t = start + (end - start) * (i / samples)
        x = center.x + radius * math.cos(t)
        y = center.y + radius * math.sin(t)
        points.append((int(x), int(y)))
    return points

class Drone:
    """
    4 drones:
      - spawn spaced inside compost (one per compost quadrant)
      - go to their sector center
      - then patrol sector perimeter
      - draw transparent FOV wedge and clamp motion by FOV radius
    """
    def __init__(self, x, y, speed, *, start_delay, compost=None):
        # Visual/body
        self.radius = float(cs.drone_radius)
        self.color = cs.blue

        # FOV
        self.fov_radius = float(cs.fov_radius)
        self.fov_angle = float(cs.fov_angle_deg)
        self.fov_rgba = cs.fov_color  # (r,g,b,a)

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

        # Heading (unit) per drone used for FOV orientation
        # Initialize headings pointing outward to their sector center
        self.heading = []
        for i in range(4):
            v = (self.sector_centers[i] - self.positions[i])
            self.heading.append(v.normalize() if v.length() > 0 else pygame.Vector2(1, 0))

        # State
        self.phase = [0] * 4           # 0: go-to-center, 1: patrol
        self.current_wp_idx = [0] * 4  # patrol waypoint
        self.start_delay = float(start_delay)
        self._elapsed = 0.0

        # Patrol waypoints inset by FOV radius (so FOV stays inside sector)
        inset = self.fov_radius + 4
        self.patrol_paths = []
        for r in self.sectors:
            left   = r.left   + inset
            right  = r.right  - inset
            top    = r.top    + inset
            bottom = r.bottom - inset
            # Keep inset valid even if fov is huge
            left, right = min(left, right), max(left, right)
            top, bottom = min(top, bottom), max(top, bottom)

            path = [
                pygame.Vector2(left, top),
                pygame.Vector2(right, top),
                pygame.Vector2(right, bottom),
                pygame.Vector2(left, bottom),
            ]
            self.patrol_paths.append(path)

    def _draw_fov(self, surface: pygame.Surface, center: pygame.Vector2, heading: pygame.Vector2):
        # Draw translucent FOV wedge on a separate alpha surface, then blit
        fov_surf = pygame.Surface((cs.screen_width, cs.screen_height), pygame.SRCALPHA)
        pts = _wedge_points(center, heading, self.fov_radius, self.fov_angle, samples=28)
        pygame.draw.polygon(fov_surf, self.fov_rgba, pts)
        surface.blit(fov_surf, (0, 0))

    def draw(self, surface):
        # (Optional) visualize sector bounds
        for r in self.sectors:
            pygame.draw.rect(surface, cs.dgreen, r, 1)

        # Draw FOV first (under the drones)
        for i in range(4):
            self._draw_fov(surface, self.positions[i], self.heading[i])

        # Draw drones
        for pos in self.positions:
            pygame.draw.circle(surface, self.color, (int(pos.x), int(pos.y)), int(self.radius))

    def move(self, dt: float):
        if self._elapsed < self.start_delay:
            self._elapsed += dt
            return

        step = self.speed * dt

        for i in range(4):
            pos = self.positions[i]

            if self.phase[i] == 0:
                # Move to sector center
                target = self.sector_centers[i]
            else:
                # Patrol along perimeter waypoints
                path = self.patrol_paths[i]
                wp_i = self.current_wp_idx[i]
                target = path[wp_i]

            new_pos = move_towards(pos, target, step)

            # Update heading (for FOV orientation)
            v = (target - pos)
            if v.length() > 0:
                self.heading[i] = v.normalize()

            # If we reached the target center/waypoint, advance state
            if new_pos.distance_to(target) == 0:
                if self.phase[i] == 0:
                    self.phase[i] = 1
                    self.current_wp_idx[i] = 0
                else:
                    self.current_wp_idx[i] = (self.current_wp_idx[i] + 1) % len(self.patrol_paths[i])

            self.positions[i] = new_pos

            # Clamp by FOV radius (not the body) so the *coverage* stays inside the sector
            r = self.sectors[i]
            margin = self.fov_radius
            self.positions[i].x = max(r.left + margin,  min(self.positions[i].x, r.right  - margin))
            self.positions[i].y = max(r.top  + margin,  min(self.positions[i].y, r.bottom - margin))
