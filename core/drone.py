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
    Manages 4 drones:
      - all start at the global center
      - each assigned one quadrant (sector)
      - phase 1: go to the sector center
      - phase 2: patrol the sector perimeter (clockwise)
    """
    def __init__(self, x, y, speed):
        self.radius = 10
        self.speed = float(speed)             # world units per second
        self.color = cs.blue

        w, h = cs.screen_width, cs.screen_height
        cx, cy = w // 2, h // 2
        self.world_center = pygame.Vector2(cx, cy)

        # Define quadrants (top-left, top-right, bottom-left, bottom-right)
        self.sectors = [
            pygame.Rect(0,      0,      w // 2, h // 2),  # TL
            pygame.Rect(w // 2, 0,      w // 2, h // 2, ),# TR
            pygame.Rect(0,      h // 2, w // 2, h // 2),  # BL
            pygame.Rect(w // 2, h // 2, w // 2, h // 2),  # BR
        ]

        # Sector centers
        self.sector_centers = [pygame.Vector2(r.center) for r in self.sectors]

        # Start all drones at the screen center
        self.positions = [self.world_center.copy() for _ in range(4)]

        # For each drone: phase 0 = heading to sector center, phase 1 = patrolling
        self.phase = [0] * 4
        self.current_wp_idx = [0] * 4  # patrol waypoint index (used in phase 1)

        # Build patrol waypoints around each sector (rectangle perimeter, slightly inset)
        inset = self.radius + 4
        self.patrol_paths = []
        for r in self.sectors:
            left   = r.left   + inset
            right  = r.right  - inset
            top    = r.top    + inset
            bottom = r.bottom - inset

            # Clockwise rectangle path: TL -> TR -> BR -> BL
            path = [
                pygame.Vector2(left, top),
                pygame.Vector2(right, top),
                pygame.Vector2(right, bottom),
                pygame.Vector2(left, bottom),
            ]
            self.patrol_paths.append(path)

    def draw(self, surface):
        # (Optional) visualize sectors
        for r in self.sectors:
            pygame.draw.rect(surface, cs.dgreen, r, 1)  # thin black outline

        # (Optional) draw sector centers
        for c in self.sector_centers:
            pygame.draw.circle(surface, (255, 255, 255), (int(c.x), int(c.y)), 3)

        # Draw each drone
        for pos in self.positions:
            pygame.draw.circle(surface, self.color, (int(pos.x), int(pos.y)), self.radius)

    def move(self, dt: float):
        # max movement per frame
        step = self.speed * dt

        for i in range(4):
            pos = self.positions[i]

            if self.phase[i] == 0:
                # Move to sector center
                target = self.sector_centers[i]
                new_pos = move_towards(pos, target, step)

                # If reached the center, switch to patrol phase
                if new_pos.distance_to(target) == 0:
                    self.phase[i] = 1
                    self.current_wp_idx[i] = 0
                self.positions[i] = new_pos

            else:
                # Patrol around the sector’s perimeter waypoints
                path = self.patrol_paths[i]
                wp_i = self.current_wp_idx[i]
                target = path[wp_i]

                new_pos = move_towards(pos, target, step)
                self.positions[i] = new_pos

                # If we reached the waypoint, advance to the next (loop)
                if new_pos.distance_to(target) == 0:
                    self.current_wp_idx[i] = (wp_i + 1) % len(path)

            # Keep each drone fully inside its sector (safety clamp)
            r = self.sectors[i]
            self.positions[i].x = max(r.left + self.radius,  min(self.positions[i].x, r.right  - self.radius))
            self.positions[i].y = max(r.top  + self.radius,  min(self.positions[i].y, r.bottom - self.radius))
