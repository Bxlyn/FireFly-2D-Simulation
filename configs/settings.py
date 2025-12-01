# configs/settings.py

# --- Screen ---
screen_width  = 1280
screen_height = 720
fps           = 60

# --- Colors ---
dgreen      = (0, 100, 0)
dgreen2     = (1, 50, 32)
dgreen3     = (2, 48, 32)
dgreen4     = (6, 64, 43)
forestgreen = (34, 139, 34)
blue        = (0, 0, 255)
cyellow     = (150, 100, 50)

# HUD colors
battery_low_color   = (220, 70, 60)
battery_med_color   = (230, 200, 40)
battery_high_color  = (60, 200, 90)
hud_text_color      = (240, 240, 240)

# --- Drones ---
startX        = 640
startY        = 360
speed         = 80          # px/s
start_delay   = 2           # s
drone_radius  = 7           # body draw radius (px)

# Vertical FOV (downward-looking footprint)
fov_angle_deg = 90
altitude_px   = 90
fov_alpha     = 70

# --- Monte-Carlo routing (belief-driven) ---
mc_cell_px          = 16
mc_candidates       = 60
mc_replan_seconds   = 0.7
mc_cost_per_px      = 0.0008
mc_detect_strength  = 0.85
mc_diffusion        = 0.06
show_belief_heatmap = False
heatmap_alpha       = 120

# --- Duty cycle & battery/RTB ---
duty_work_seconds       = 25.0
duty_recharge_seconds   = 3.0
duty_jitter_frac        = 0.25
show_battery_hud        = True
battery_world_bars      = True
battery_panel           = True
battery_panel_pos       = (12, 12)
battery_panel_width     = 240
battery_bar_h           = 10
battery_low_threshold   = 0.20
battery_med_threshold   = 0.50
battery_return_threshold = 0.20
battery_reserve_seconds  = 3.0

# --- Fire (CA + Rothermel-inspired) ---
fire_cell_px         = 8
fire_rng_seed        = 2024

# Keep spread moderate for demo
fire_ros_scale       = 0.5
fire_base_ros_pxps   = 8.0
fire_k_ignite        = 0.6

# Wind (0°→, 90°↓)
fire_wind_speed      = 8.0
fire_wind_dir_deg    = 25.0
fire_c_w             = 0.045
fire_b_w             = 1.4

# Slope
fire_slope_deg       = 5.0
fire_slope_dir_deg   = 180.0
fire_c_s             = 0.08
fire_b_s             = 2.0

# Fuel / moisture
fire_moisture_live   = 0.18
fire_moisture_ext    = 0.35
fire_fuel_mean       = 1.0
fire_fuel_var        = 0.25

# Burn timing
fire_burn_duration   = 18.0

# Barriers / spotting
fire_barrier_density = 0.01
fire_spot_chance     = 0.0002
fire_spot_max_cells  = 10

# Visuals
fire_show_grid       = False
fire_alpha_fire      = 175
fire_draw_smoke      = False
fire_show_zone_ring  = False   # do NOT draw suppression ring

# --- Detection (deterministic, debounced) ---
det_min_frac       = 0.010   # ≥ 1% of FOV burning
det_confirm_time   = 0.50    # must persist ≥ this time
det_cooldown_s     = 3.0
det_false_pos      = 0.0
marker_ttl         = 4.0

# --- Incident tracking & suppression ---
incident_merge_radius_px    = 100
incident_monitor_radius_px  = 140
incident_suppress_radius_px = 90
stop_after_detect_delay     = 2.0
suppress_grow_speed_pxps    = 160.0
quench_burn_boost           = 6.0
suppress_wet                = 0.0
suppress_fuel_reduction     = 0.0
suppress_extinguish         = False
fire_burned_regen_seconds   = 25.0

# --- Demo knobs (main.py uses these) ---
bg_ignitions_per_s     = 0.004
click_ignite_radius_px = 10

# --- Under-drone incident coordinates label ---
show_incident_coords   = True
incident_coords_color  = (240, 240, 240)
incident_coords_bg     = (20, 20, 20, 180)

# --- Station (compost) ---
cradius = 48

# --- IRL Adaptation ---
# Minutes of "real world" per 1 simulation second (e.g., 3.33 => 10 min in 3 sim sec)
sim_to_real_min_per_sec = 10.0 / 3.0

# --- Real-world spatial scale (px → m) ---
# meters per pixel. Tune this to your map; 0.2 m/px is a reasonable demo value.
meters_per_px = 0.2

# Optional reference cruise speed for logs
hybrid_vtol_cruise_kmh = 72.0

# --- Console log retention (terminal) ---
max_log_lines = 2000
metrics_log_period_s = 1.0

# --- Economic baseline (IRL conventional detection) ---
# You can change these to test different baselines.
econ_currency = "$"
econ_cost_per_ha = 11599.58            # average fully-loaded loss per hectare
econ_baseline_delay_min = 20.0        # conventional detection delay (minutes)
econ_baseline_ros_mps   = 1.2         # average ROS (m/s) until conventional detection
