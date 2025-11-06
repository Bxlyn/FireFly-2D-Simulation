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
      - all start at the compost center area (spaced apart inside the compost circle)
      - each assigned one quadrant (sector)
      - phase 1: go to the sector center
      - phase 2: patrol the sector perimeter (clockwise)
    """
    def __init__(self, x, y, speed, *, start_delay, compost=None):
        self.radius = 10
        self.speed = float(speed)             # units/second
        self.color = cs.blue

        w, h = cs.screen_width, cs.screen_height
        cx, cy = w // 2, h // 2

        # World / compost center
        if compost is not None:
            self.world_center = compost.pos.copy()
            compost_radius = compost.radius
        else:
            self.world_center = pygame.Vector2(cx, cy)
            compost_radius = max(32, self.radius * 3)  # fallback

        # Define quadrants (TL, TR, BL, BR)
        self.sectors = [
            pygame.Rect(0,      0,      w // 2, h // 2),  # 0: TL
            pygame.Rect(w // 2, 0,      w // 2, h // 2),  # 1: TR
            pygame.Rect(0,      h // 2, w // 2, h // 2),  # 2: BL
            pygame.Rect(w // 2, h // 2, w // 2, h // 2),  # 3: BR
        ]

        self.sector_centers = [pygame.Vector2(r.center) for r in self.sectors]

        # --- Spawn 4 drones inside the compost circle, one per slice ---
        # Order angles correspond to sectors above: TL, TR, BL, BR
        # TL=135°, TR=45°, BL=225°, BR=315°
        # Place them on a circle inside the compost, with margin so circles don't clip.
        spawn_ring = max(self.radius + 4, min(compost_radius - self.radius - 4, compost_radius * 0.66))
        spawn_angles = [135, 45, 225, 315]
        self.positions = []
        for ang in spawn_angles:
            offset = pygame.Vector2(spawn_ring, 0).rotate(ang)
            self.positions.append(self.world_center + offset)

        # State
        self.phase = [0] * 4          # 0: go-to-center, 1: patrol
        self.current_wp_idx = [0] * 4

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

        # Launch delay
        self.start_delay = float(start_delay)
        self._elapsed = 0.0

    def draw(self, surface):
        # (Optional) visualize sector bounds
        for r in self.sectors:
            pygame.draw.rect(surface, cs.dgreen, r, 1)

        # Draw each drone
        for pos in self.positions:
            pygame.draw.circle(surface, self.color, (int(pos.x), int(pos.y)), self.radius)

    def move(self, dt: float):
        if self._elapsed < self.start_delay:
            self._elapsed += dt
            return  # stay parked in compost slices

        step = self.speed * dt

        for i in range(4):
            pos = self.positions[i]

            if self.phase[i] == 0:
                # Move to sector center
                target = self.sector_centers[i]
                new_pos = move_towards(pos, target, step)
                if new_pos.distance_to(target) == 0:
                    self.phase[i] = 1
                    self.current_wp_idx[i] = 0
                self.positions[i] = new_pos
            else:
                # Patrol along perimeter waypoints
                path = self.patrol_paths[i]
                wp_i = self.current_wp_idx[i]
                target = path[wp_i]
                new_pos = move_towards(pos, target, step)
                self.positions[i] = new_pos
                if new_pos.distance_to(target) == 0:
                    self.current_wp_idx[i] = (wp_i + 1) % len(path)

            # Safety clamp: keep inside own sector
            r = self.sectors[i]
            self.positions[i].x = max(r.left + self.radius,  min(self.positions[i].x, r.right  - self.radius))
            self.positions[i].y = max(r.top  + self.radius,  min(self.positions[i].y, r.bottom - self.radius))
