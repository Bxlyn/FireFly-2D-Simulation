# FireFly 2D Wildfire Simulation

> **Grand Challenges Project** — A 2D, real‑time wildfire simulation built with **Python + Pygame**.  
> A squad of autonomous drones survey a landscape, detect fires, and “dispatch” suppression to stop spread.  
> The sim logs operational events and produces a **dashboard‑style summary** with detection, area, and **economic impact** metrics (vs. a conventional‑detection baseline).

<p align="center">
  <!-- Replace with actual path -->
  <img src="docs/screenshots/cover.png" alt="FireFly 2D Simulation — cover" width="75%">
</p>

---

## Table of Contents

- [Demo](#demo)
- [Features](#features)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Controls & Shortcuts](#controls--shortcuts)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Metrics & Economics](#metrics--economics)
- [Reproducibility](#reproducibility)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Cite / Acknowledgments](#cite--acknowledgments)
- [License](#license)

---

## Demo

> Add images or GIFs showing the sim and summary. Keep files under `docs/screenshots/`.

- **Start screen**  
  ![Start Screen](docs/screenshots/start_screen.png "Start Screen")

- **In‑sim: drones scanning and detecting**  
  ![In Simulation](docs/screenshots/in_sim.png "In Simulation")

- **Incident dispatch and suppression ring**  
  ![Dispatch](docs/screenshots/dispatch.png "Dispatch")

- **Summary dashboard (post‑run)**  
  ![Summary](docs/screenshots/summary.png "Summary Dashboard")

---

## Features

- **Autonomous multi‑drone search**  
  4 drones split the map into sectors and plan targets with a lightweight Monte‑Carlo belief model.

- **Real‑time fire spread**  
  Cellular automaton with wind/slope/fuel effects and stochastic spotting.

- **Incident lifecycle**  
  Confirmed detections create **incidents**; after a short delay, a suppression zone goes live and prevents further spread inside the tagged cluster.

- **Event log**  
  Terminal log for *DETECT*, *DISPATCH*, *EXTINGUISHED* events with time and area snapshots.

- **Summary dashboard (no scrolling)**  
  Run time, detection quality, drone performance, totals, **economic impact** (vs. conventional‑detection baseline).

- **Configurable scale**  
  Converts px→m and sim‑seconds→IRL minutes for intuitive reporting.

---

## How It Works

- **`core/fire.py`**  
  A Rothermel‑inspired cellular model tracks each grid cell as `UNBURNED`, `BURNING`, `BURNED`, or `BARRIER`.  
  Wind & slope bias the **rate of spread**; **spotting** can ignite down‑wind embers.  
  On detection, nearby burning cells are **tagged** to an incident. When suppression is live, **tagged cells stop spreading** and burn out faster.

- **`core/drone.py`**  
  Drones carry a circular FOV. A detection is confirmed when the **burning fraction** in FOV stays above a threshold for a short confirmation time.  
  Each drone alternates phases: `APPROACH → SEARCH → HOLD/RETURN → RECHARGE`.  
  Movement & battery usage are simulated; distances and average speeds are estimated from motion.

- **`ui/summary_screen.py`**  
  Shows 6 cards: *Run Time*, *Drone Performance*, *Fire Detection*, *Economic Impact*, *Totals*, *Incidents & Events*.

- **Economics**  
  Compares the **actual final area** with an **upper‑bound baseline** modeling *conventional detection* with a delay and an assumed ROS (rate of spread):  
  \( A_{\text{baseline per fire}} \approx \pi (ROS \cdot delay)^2 \).  
  Cost is computed with a configurable **cost per hectare**.

---

## Installation

> Requires Python **3.10+**.

```bash
# 1) Clone
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

# 2) (Optional but recommended) Create a virtual env
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3) Install dependencies
pip install -r requirements.txt
# If you don't have a requirements file yet:
pip install pygame>=2.4
```

---

## Quick Start

```bash
python main.py
```

**In the sim:**
- Left‑click to ignite a spot fire (configurable radius).
- Watch drones detect and dispatch suppression.
- Press **Esc** (or close the window) to exit to the **Summary Dashboard**.

<p align="center">
  <!-- Replace with actual path -->
  <img src="docs/screenshots/in_sim.png" alt="In Simulation" width="70%">
</p>

---

## Controls & Shortcuts

- **Left‑click** — Ignite a fire at the cursor (radius configurable).
- **Esc** — End simulation and open the summary.
- **Window close** — Same as Esc.

(Optionally document any additional keys you added.)

---

## Project Structure

```
.
├── main.py
├── core/
│   ├── fire.py         # Fire CA model, incidents, suppression, metrics
│   ├── drone.py        # 4-drone controller, search/hold/return logic, HUD
│   └── compost.py      # Home/base (spawn) UI element
├── ui/
│   ├── start_screen.py   # Start menu
│   └── summary_screen.py # Dashboard-style summary (no scrolling)
├── configs/
│   └── settings.py     # All tunables (screen, sim scale, fire model, drones, economics)
├── docs/
│   └── screenshots/    # <-- Put README images here
└── requirements.txt
```

---

## Configuration

All parameters live in **`configs/settings.py`**. Common ones:

### Display & Time
- `screen_width`, `screen_height`, `fps`
- `sim_to_real_min_per_sec` — IRL minutes per simulation second (for readable times)

### Drones
- `speed`, `startX`, `startY`, `start_delay`, `drone_radius`
- FOV: `fov_angle_deg`, `altitude_px`, `fov_alpha`
- Search (MC): `mc_cell_px`, `mc_candidates`, `mc_replan_seconds`, `mc_cost_per_px`, `mc_detect_strength`, `mc_diffusion`
- Duty/Battery: `duty_work_seconds`, `duty_recharge_seconds`, `battery_return_threshold`, `battery_reserve_seconds`
- Detection debounce: `det_min_frac`, `det_confirm_time`, `det_cooldown_s`

### Fire model
- Grid: `fire_cell_px`, `fire_rng_seed`
- ROS & ignition: `fire_ros_scale`, `fire_base_ros_pxps`, `fire_k_ignite`
- Wind: `fire_wind_speed`, `fire_wind_dir_deg`, `fire_c_w`, `fire_b_w`
- Slope: `fire_slope_deg`, `fire_slope_dir_deg`, `fire_c_s`, `fire_b_s`
- Fuel & moisture: `fire_fuel_mean`, `fire_fuel_var`, `fire_moisture_live`, `fire_moisture_ext`
- Burn timing: `fire_burn_duration`
- Barriers & spotting: `fire_barrier_density`, `fire_spot_chance`, `fire_spot_max_cells`

### Incidents & Suppression
- Merge radius: `incident_merge_radius_px`
- Monitor radius: `incident_monitor_radius_px`
- Suppression: `incident_suppress_radius_px`, `stop_after_detect_delay`, `suppress_grow_speed_pxps`, `quench_burn_boost`

### User Interaction
- Manual ignition radius: `click_ignite_radius_px`
- Background random ignitions: `bg_ignitions_per_s`

### Scale
- Pixels to meters: `meters_per_px` (or derived from target cruise speed)
- HUD toggles/positions, palette colors, etc.

### Economics (baseline vs. sim)
- `econ_currency` (e.g., `"$"` or `"€"`)
- `econ_cost_per_ha`
- `econ_baseline_delay_min` — minutes until detection with **conventional methods**
- `econ_baseline_ros_mps` — assumed **rate of spread** (m/s) during that delay

---

## Metrics & Economics

The summary aggregates everything into six cards:

### Run Time
- **Simulation duration** (seconds)
- **IRL equivalent** using `sim_to_real_min_per_sec`

### Fire Detection
- **Fires detected** (and detection rate if undetected fires occurred)
- **Avg detection time (sim / IRL)**
- **Avg area at first detection** (m²)

### Drone Performance
- **Average speed** (km/h across drones)
- **Per‑drone distance** (km)

### Totals
- **Total burned area** — *sum of final per‑incident footprints* (m²)  
- **Total scorched area** — **cumulative union** of cells that ever finished burning (BURNED) during this run (m²)  
  - This can be **≥** the sum of incident finals (e.g., undetected episodes or overlap).  
- **Largest footprint** — max final area among incidents (m²)

### Incidents & Events
- **Detected fires**, **Undetected fires**
- **Dispatch events**, **Extinguished events**

### Economic Impact
- **Baseline (conventional)** assumes a detection **delay** and **ROS**; area per fire:
  \[
  A_{\text{baseline}} \approx \pi \cdot (ROS \cdot delay)^2
  \]
- **Baseline loss (conv.)** = \( A_{\text{baseline}} \times N_{\text{fires}} \) → hectares → `econ_cost_per_ha`
- **Potential loss (actual)** = (sum of final areas) → hectares → `econ_cost_per_ha`
- **Estimated money saved** = **Baseline loss − Actual loss**

> ⚠️ **Assumptions matter.** For fair comparisons, cite the chosen `econ_baseline_delay_min`, `econ_baseline_ros_mps`, and `econ_cost_per_ha` in your report.

---

## Reproducibility

- Set `fire_rng_seed` in `configs/settings.py`.
- Log output is printed via a small `LogBus` (timestamps included).  
  Save the console output if you need a paper trail for a run.

---

## Troubleshooting

- **Black window / nothing shows**  
  Make sure you’re on Python 3.10+ and `pygame` ≥ 2.4. Try `pip show pygame`.
- **Fonts too large / clipped**  
  The summary UI auto‑scales fonts to fit one page. Use a 16:9 window (e.g., 1280×720 or 1600×900) for best results.
- **Economic card clipped**  
  The UI switches to a two‑column layout for that card and shrinks fonts as needed. If it still overflows, lower `econ_currency` font size only if you’ve customized the card.
- **No fires detected**  
  Lower `det_min_frac` or `det_confirm_time`, or increase `bg_ignitions_per_s`.

---

## Roadmap

- Save/load runs and **export CSV** metrics
- Optional **screencast** / PNG export hotkey
- Parameter presets (e.g., “windy day”, “dry fuels”)
- Alternate drone strategies (lawnmower, frontier following, etc.)

---

## Cite / Acknowledgments

If you use this in a write‑up:

```
@software{firefly2d_sim,
  title        = {FireFly 2D Wildfire Simulation},
  author       = {<Your Name>},
  year         = {2025},
  url          = {https://github.com/<your-username>/<your-repo>}
}
```

Thanks to open‑source **Pygame** and to prior literature on wildfire spread and UAV search strategies that inspired this educational model.

---

## License

Choose a license and add a `LICENSE` file (MIT recommended for coursework).  
Example:

```
MIT License — see LICENSE for details.
```

---

### Screenshot placeholders (quick copy/paste)

- `docs/screenshots/cover.png`
- `docs/screenshots/start_screen.png`
- `docs/screenshots/in_sim.png`
- `docs/screenshots/dispatch.png`
- `docs/screenshots/summary.png`

> Tip: keep images ~1280px wide for fast GitHub rendering.
