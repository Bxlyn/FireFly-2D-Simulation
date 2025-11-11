# Screen dimensions
screen_width = 1280
screen_height = 720

# Colors
dgreen = (0, 100, 0)
dgreen2 = (1, 50, 32)
dgreen3 = (2, 48, 32)
dgreen4 = (6, 64, 43)
forestgreen = (34, 139, 34)
blue = (0, 0, 255)
cyellow = (150, 100, 50)

# Drones
startX = 640
startY = 360
speed = 80
start_delay = 2
drone_radius = 7     # body draw radius (px)

# Vertical FOV (downward-looking)
fov_angle_deg = 90   # 80–100 realistic
altitude_px = 90     # bigger => bigger FOV footprint
fov_alpha = 70       # transparency of FOV disk

#Monte-Carlo
mc_cell_px = 16            # grid cell size. 12-24 is typical; smaller = finer belief, slower
mc_candidates = 60         # random candidates sampled per replan
mc_replan_seconds = 0.7    # how often to resample targets if we haven't arrived
mc_cost_per_px = 0.0008    # travel cost weight in utility (probability units per pixel)
mc_detect_strength = 0.85   # fraction removed from belief inside FOV each observation
mc_diffusion = 0.06         # probability diffusion per update (0..1). 0=static, 0.05-0.1=gentle drift
show_belief_heatmap = False # overlay heatmap (can be slow)
heatmap_alpha = 120         # heatmap opacity (0..255)

# --- Duty cycle (periodic recharge) ---
duty_work_seconds = 25.0     # time away from base before returning
duty_recharge_seconds = 3.0  # 2..5 seconds typical recharge dwell time
duty_jitter_frac = 0.25      # ±25% jitter so drones don't all return together


# Compost
cradius = 48

# Misc
fire = 2.5
fps = 60
