# FireFly 2D Wildfire Simulation

**Grand Challenges Project Prototype** — A 2D, real‑time wildfire simulation built with **Python + Pygame**.  

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
