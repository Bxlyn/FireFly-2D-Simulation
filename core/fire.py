# core/fire.py
import math
import random
from typing import List, Tuple, Optional, Dict, Any

import pygame
import configs.settings as cs


class Fire:
    """
    Stochastic CA + Rothermel-inspired spread with INCIDENT suppression.
    Tracks detection times, area at detection, final footprint, dispatch/extinguish counts,
    cumulative scorched area, and user ignitions.
    """

    UNBURNED = 0
    BURNING  = 1
    BURNED   = 2
    BARRIER  = 3

    def __init__(self, cell_px: Optional[int] = None, seed: Optional[int] = None):
        # Grid
        self.cell = int(cell_px if cell_px is not None else getattr(cs, "fire_cell_px", 8))
        self.GW = cs.screen_width  // self.cell
        self.GH = cs.screen_height // self.cell
        self.cell_diag = self.cell * math.sqrt(2.0)

        # RNG
        self.rng = random.Random(seed if seed is not None else getattr(cs, "fire_rng_seed", 2024))

        # Physics
        self.ros_scale   = float(getattr(cs, "fire_ros_scale", 1.0))
        self.R0          = float(getattr(cs, "fire_base_ros_pxps", 16.0))
        self.k_ignite    = float(getattr(cs, "fire_k_ignite", 1.0))

        # Wind
        self.wind_speed   = float(getattr(cs, "fire_wind_speed", 18.0))
        self.wind_dir_deg = float(getattr(cs, "fire_wind_dir_deg", 25.0))
        wd = math.radians(self.wind_dir_deg)
        self.wind_unit = (math.cos(wd), math.sin(wd))
        self.c_w = float(getattr(cs, "fire_c_w", 0.045))
        self.b_w = float(getattr(cs, "fire_b_w", 1.4))

        # Slope
        self.slope_deg     = float(getattr(cs, "fire_slope_deg", 5.0))
        self.slope_dir_deg = float(getattr(cs, "fire_slope_dir_deg", 180.0))
        sd = math.radians(self.slope_dir_deg)
        self.slope_unit = (math.cos(sd), math.sin(sd))
        self.tan_slope  = math.tan(math.radians(self.slope_deg))
        self.c_s = float(getattr(cs, "fire_c_s", 0.08))
        self.b_s = float(getattr(cs, "fire_b_s", 2.0))

        # Fuel / moisture
        self.moisture_live = float(getattr(cs, "fire_moisture_live", 0.18))
        self.moisture_ext  = float(getattr(cs, "fire_moisture_ext", 0.35))
        self.fuel_load_mean= float(getattr(cs, "fire_fuel_mean", 1.0))
        self.fuel_load_var = float(getattr(cs, "fire_fuel_var",  0.25))

        # Burn timing
        self.burn_duration = float(getattr(cs, "fire_burn_duration", 18.0))

        # Barriers / spotting
        self.barrier_density = float(getattr(cs, "fire_barrier_density", 0.01))
        self.spot_chance     = float(getattr(cs, "fire_spot_chance", 0.0002))
        self.spot_max_cells  = int(getattr(cs, "fire_spot_max_cells", 10))

        # Visuals
        self.show_grid      = bool(getattr(cs, "fire_show_grid", False))
        self.alpha_fire     = int(getattr(cs, "fire_alpha_fire", 175))
        self.show_zone_ring = bool(getattr(cs, "fire_show_zone_ring", False))

        # Fields
        N = self.GW * self.GH
        self.state: List[int]    = [self.UNBURNED] * N
        self.burn_t: List[float] = [0.0] * N
        self.sim_t = 0.0
        self.t_ignited: List[float] = [math.inf] * N
        self.fuel:  List[float]  = [0.0] * N
        self.moist: List[float]  = [0.0] * N

        # Incident tags per cell (0 = no incident)
        self.tag: List[int]      = [0] * N

        # Burned-area recovery
        self.recover_T = float(getattr(cs, "fire_burned_regen_seconds", 25.0))
        self.regen_t: List[float] = [0.0] * N
        self._regen_accum = 0.0

        # px → m mapping convenience
        mpp = None
        for key in ("meters_per_px", "px_to_meter"):
            if hasattr(cs, key):
                v = float(getattr(cs, key))
                if v > 0.0:
                    mpp = v
                    break
        if mpp is None:
            # Fallback to speed mapping
            spx = float(getattr(cs, "speed", 80.0))
            tgt_kmh = float(getattr(cs, "hybrid_vtol_cruise_kmh", 72.0))
            self._px_to_m = (tgt_kmh / 3.6) / max(spx, 1e-6)
        else:
            self._px_to_m = mpp

        # Neighborhood (8)
        self.neigh = [(-1, 0, self.cell), ( 1, 0, self.cell),
                      ( 0,-1, self.cell), ( 0, 1, self.cell),
                      (-1,-1, self.cell_diag), ( 1,-1, self.cell_diag),
                      ( 1, 1, self.cell_diag), (-1, 1, self.cell_diag)]

        # Active frontier
        self.active: List[int] = []

        # Overlay
        self.overlay = pygame.Surface((cs.screen_width, cs.screen_height), pygame.SRCALPHA)

        # Incidents and suppression
        self.incidents: List[Dict[str, Any]] = []
        self._next_incident_id = 1
        self._merge_r2   = float(getattr(cs, "incident_merge_radius_px", 100)) ** 2
        self._monitor_r  = float(getattr(cs, "incident_monitor_radius_px", 140))
        self._zone_r0    = float(getattr(cs, "incident_suppress_radius_px", 90))
        self._delay_s    = float(getattr(cs, "stop_after_detect_delay", 2.0))
        self._grow_v     = float(getattr(cs, "suppress_grow_speed_pxps", 160.0))
        self._quench     = float(getattr(cs, "quench_burn_boost", 6.0))

        # Metrics
        self.det_times: List[float] = []          # sim seconds to detection
        self.detect_areas_m2: List[float] = []    # area at detection (m²)
        self.final_areas_m2: List[float] = []     # final area (m²)
        self.dispatch_count: int = 0
        self.extinguished_count: int = 0
        self.user_ignitions: int = 0

        # Cumulative scorched: unique cells that ever reached BURNED
        self._ever_burned: List[bool] = [False] * N

        # Episodes with no incident (extinguished before any detection)
        self.undetected_count: int = 0
        self._episode_has_incident: bool = False

        self._init_terrain()

    # ----- helpers -----
    @property
    def px_to_m(self) -> float:
        return self._px_to_m

    @property
    def cell_area_m2(self) -> float:
        return (self.cell * self._px_to_m) ** 2

    def _init_terrain(self):
        for gy in range(self.GH):
            for gx in range(self.GW):
                idx = self._idx(gx, gy)
                jitter = (self.rng.random() * 2 - 1) * self.fuel_load_var
                self.fuel[idx] = max(0.1, self.fuel_load_mean * (1.0 + jitter))
                m_jit = (self.rng.random() * 2 - 1) * 0.05
                self.moist[idx] = max(0.0, min(1.0, self.moisture_live + m_jit))
                if self.rng.random() < self.barrier_density:
                    self.state[idx] = self.BARRIER

    def _idx(self, gx: int, gy: int) -> int: return gy * self.GW + gx
    def _gxgy(self, idx: int) -> Tuple[int, int]: return (idx % self.GW, idx // self.GW)
    def _center_px(self, gx: int, gy: int) -> Tuple[float, float]:
        return (gx * self.cell + 0.5 * self.cell, gy * self.cell + 0.5 * self.cell)

    # ----- ignition -----
    def ignite_world(self, x_px: float, y_px: float, radius_px: int = 0):
        self.user_ignitions += 1
        gx = int(x_px // self.cell); gy = int(y_px // self.cell)
        if radius_px <= 0:
            self._ignite_cell(gx, gy)
        else:
            r_cells = max(0, int(radius_px // self.cell))
            for oy in range(-r_cells, r_cells + 1):
                for ox in range(-r_cells, r_cells + 1):
                    if ox * ox + oy * oy <= r_cells * r_cells:
                        self._ignite_cell(gx + ox, gy + oy)

    def random_ignitions(self, lam_per_s: float, dt: float):
        if self.rng.random() < lam_per_s * dt:
            gx = self.rng.randrange(self.GW)
            gy = self.rng.randrange(self.GH)
            self._ignite_cell(gx, gy)

    def _ignite_cell(self, gx: int, gy: int):
        if not (0 <= gx < self.GW and 0 <= gy < self.GH): return
        idx = self._idx(gx, gy)
        if self.state[idx] == self.UNBURNED and self.fuel[idx] > 0.0:
            self.state[idx] = self.BURNING
            self.burn_t[idx] = 0.0
            self.t_ignited[idx] = self.sim_t
            self.active.append(idx)

    # ----- detection helper -----
    def burning_fraction_in_disc(self, x_px: float, y_px: float, r_px: float) -> Tuple[float, list]:
        c = self.cell; r2 = r_px * r_px
        gx0 = max(0, int((x_px - r_px) // c))
        gx1 = min(self.GW - 1, int((x_px + r_px) // c))
        gy0 = max(0, int((y_px - r_px) // c))
        gy1 = min(self.GH - 1, int((y_px + r_px) // c))
        inside = 0; burning = 0; hotspots = []
        for gy in range(gy0, gy1 + 1):
            cy = gy * c + 0.5 * c
            dy2 = (cy - y_px) * (cy - y_px)
            for gx in range(gx0, gx1 + 1):
                cx = gx * c + 0.5 * c
                dx = cx - x_px
                if dx * dx + dy2 <= r2:
                    inside += 1
                    idx = self._idx(gx, gy)
                    if self.state[idx] == self.BURNING:
                        burning += 1
                        hotspots.append((cx, cy))
        frac = (burning / inside) if inside > 0 else 0.0
        return frac, hotspots

    # ----- area / footprint -----
    def footprint_in_disc(self, x_px: float, y_px: float, r_px: float) -> Dict[str, float]:
        c = self.cell; r2 = r_px * r_px
        gx0 = max(0, int((x_px - r_px) // c))
        gx1 = min(self.GW - 1, int((x_px + r_px) // c))
        gy0 = max(0, int((y_px - r_px) // c))
        gy1 = min(self.GH - 1, int((y_px + r_px) // c))
        inside = 0; burning = 0; burned = 0
        for gy in range(gy0, gy1 + 1):
            cy = gy * c + 0.5 * c
            dy2 = (cy - y_px) * (cy - y_px)
            for gx in range(gx0, gx1 + 1):
                cx = gx * c + 0.5 * c
                dx = cx - y_px + (cx - cx)  # placeholder to avoid lint noise
                dx = cx - x_px
                if dx * dx + dy2 <= r2:
                    inside += 1
                    idx = self._idx(gx, gy)
                    st = self.state[idx]
                    if st == self.BURNING:
                        burning += 1
                    elif st == self.BURNED:
                        burned += 1
        cell_area_m2 = self.cell_area_m2
        return {
            "inside_cells": inside,
            "burning_cells": burning,
            "burned_cells": burned,
            "cells_fire": burning + burned,
            "cell_area_m2": cell_area_m2,
            "area_m2_burning": burning * cell_area_m2,
            "area_m2_burned":  burned * cell_area_m2,
            "area_m2_total":   (burning + burned) * cell_area_m2,
        }

    def incident_footprint(self, inc_id: int) -> Dict[str, float]:
        inc = self.get_incident(inc_id)
        if not inc:
            return {
                "inside_cells": 0, "burning_cells": 0, "burned_cells": 0,
                "cells_fire": 0, "cell_area_m2": self.cell_area_m2,
                "area_m2_burning": 0.0, "area_m2_burned": 0.0, "area_m2_total": 0.0
            }
        return self.footprint_in_disc(inc["cx"], inc["cy"], inc["monitor_r"])

    def _incident_area_by_tag_m2(self, inc_id: int) -> float:
        cA = self.cell_area_m2
        total_cells = 0
        N = self.GW * self.GH
        for idx in range(N):
            if self.tag[idx] == inc_id:
                st = self.state[idx]
                if st == self.BURNING or st == self.BURNED:
                    total_cells += 1
        return total_cells * cA

    # ----- incidents -----
    def _estimate_ignited_time_near(self, cx: float, cy: float, r: float) -> float:
        c = self.cell; r2 = r * r
        gx0 = max(0, int((cx - r) // c)); gx1 = min(self.GW - 1, int((cx + r) // c))
        gy0 = max(0, int((cy - r) // c)); gy1 = min(self.GH - 1, int((cy + r) // c))
        earliest = math.inf
        for gy in range(gy0, gy1 + 1):
            py = gy * c + 0.5 * c
            for gx in range(gx0, gx1 + 1):
                px = gx * c + 0.5 * c
                if (px - cx) * (px - cx) + (py - cy) * (py - cy) <= r2:
                    idx = self._idx(gx, gy)
                    if self.state[idx] == self.BURNING:
                        earliest = min(earliest, self.t_ignited[idx])
        return self.sim_t if earliest == math.inf else earliest

    def register_incident(self, cx: float, cy: float) -> Tuple[int, bool]:
        self._episode_has_incident = True

        for inc in self.incidents:
            if inc["active"]:
                if (cx - inc["cx"])**2 + (cy - inc["cy"])**2 <= self._merge_r2:
                    return inc["id"], False

        inc_id = self._next_incident_id; self._next_incident_id += 1
        ign_t  = self._estimate_ignited_time_near(cx, cy, self._monitor_r)
        det_t  = self.sim_t
        det_s  = max(0.0, det_t - ign_t)

        fp = self.footprint_in_disc(cx, cy, self._monitor_r)
        area_at_detect_m2 = fp["area_m2_total"]

        self.det_times.append(det_s)
        self.detect_areas_m2.append(area_at_detect_m2)

        self.incidents.append({
            "id": inc_id,
            "cx": cx, "cy": cy,
            "monitor_r": self._monitor_r,
            "delay": self._delay_s,
            "zone_live": False,
            "zone_r": 0.0,
            "active": True,
            "ignited_t": ign_t,
            "detected_t": det_t,
            "suppressed_t": None,
            "extinguished_t": None,
            "detect_area_m2": area_at_detect_m2,
            "final_area_m2": None,
            "announced_suppression": False,
            "announced_extinguished": False,
            "_counted_final": False,
        })
        return inc_id, True

    def incident_is_active(self, inc_id: int) -> bool:
        for inc in self.incidents:
            if inc["id"] != inc_id:
                continue

            if inc["zone_live"]:
                # any burning cells with this tag?
                has_burning = False
                for idx in self.active:
                    if self.tag[idx] == inc_id and self.state[idx] == self.BURNING:
                        has_burning = True
                        break

                if has_burning:
                    inc["active"] = True
                    return True

                # transitioned to inactive
                if inc.get("extinguished_t") is None:
                    inc["active"] = False
                    inc["extinguished_t"] = self.sim_t
                    final_area = self._incident_area_by_tag_m2(inc_id)
                    inc["final_area_m2"] = final_area
                    if not inc["_counted_final"]:
                        self.final_areas_m2.append(final_area)
                        inc["_counted_final"] = True
                    self.extinguished_count += 1
                return False

            # pre-live
            frac, _ = self.burning_fraction_in_disc(inc["cx"], inc["cy"], inc["monitor_r"])
            inc["active"] = (frac > 0.0)
            return inc["active"]

        return False

    def _label_incident_cluster(self, inc: dict):
        inc_id = inc["id"]
        cx0, cy0 = inc["cx"], inc["cy"]
        r2 = inc["monitor_r"] * inc["monitor_r"]

        # seeds: burning cells in disk
        seeds = []
        for idx in self.active:
            gx, gy = self._gxgy(idx)
            cx, cy = self._center_px(gx, gy)
            if (cx - cx0)*(cx - cx0) + (cy - cy0)*(cy - cy0) <= r2:
                seeds.append(idx)
        if not seeds and self.active:
            def d2(idxx):
                gx, gy = self._gxgy(idxx)
                px, py = self._center_px(gx, gy)
                return (px - cx0)*(px - cx0) + (py - cy0)*(py - cy0)
            seeds = [min(self.active, key=d2)]

        stack = list(seeds)
        visited = set()
        while stack:
            idx = stack.pop()
            if idx in visited: continue
            visited.add(idx)
            if self.state[idx] != self.BURNING: continue
            if self.tag[idx] == 0:
                self.tag[idx] = inc_id
            gx, gy = self._gxgy(idx)
            for dx, dy, _ in self.neigh:
                ngx = gx + dx; ngy = gy + dy
                if not (0 <= ngx < self.GW and 0 <= ngy < self.GH): continue
                nidx = self._idx(ngx, ngy)
                if nidx in visited: continue
                if self.state[nidx] == self.BURNING and self.tag[nidx] == 0:
                    stack.append(nidx)

    def _update_incidents(self, dt: float):
        for inc in self.incidents:
            if not inc["zone_live"]:
                frac, _ = self.burning_fraction_in_disc(inc["cx"], inc["cy"], inc["monitor_r"])
                if frac <= 0.0:
                    inc["active"] = False
                    continue
                inc["delay"] -= dt
                if inc["delay"] <= 0.0:
                    inc["zone_live"] = True
                    inc["zone_r"] = min(self._zone_r0, inc["monitor_r"])
                    inc["suppressed_t"] = self.sim_t
                    self._label_incident_cluster(inc)
                    self.dispatch_count += 1
            else:
                inc["zone_r"] = min(inc["monitor_r"], inc["zone_r"] + self._grow_v * dt)

    # ----- model core -----
    def _ros_directional(self, dir_unit: Tuple[float, float], fuel: float, moist: float) -> float:
        dryness = max(0.0, 1.0 - (moist / max(1e-6, self.moisture_ext)))
        cos_w = max(0.0, dir_unit[0]*self.wind_unit[0] + dir_unit[1]*self.wind_unit[1])
        phi_w = self.c_w * (max(0.0, self.wind_speed) ** self.b_w) * (cos_w ** max(1.0, self.b_w * 0.5))
        cos_s = max(0.0, dir_unit[0]*self.slope_unit[0] + dir_unit[1]*self.slope_unit[1])
        phi_s = self.c_s * (self.tan_slope ** self.b_s) * (cos_s ** 2.0)
        return self.ros_scale * self.R0 * (1.0 + phi_w + phi_s) * max(0.0, fuel) * dryness

    def _ember_spot(self, src_gx: int, src_gy: int):
        if self.rng.random() >= self.spot_chance: return
        dist_cells = self.rng.randint(1, max(1, self.spot_max_cells))
        wx, wy = self.wind_unit
        dx = 1 if wx > 0.2 else (-1 if wx < -0.2 else 0)
        dy = 1 if wy > 0.2 else (-1 if wy < -0.2 else 0)
        if dx == 0 and dy == 0: return
        self._ignite_cell(src_gx + dist_cells * dx, src_gy + dist_cells * dy)

    def _recover_burned(self, dt: float):
        if self.recover_T <= 0.0:
            return
        self._regen_accum += dt
        if self._regen_accum < 0.25:
            return
        step = self._regen_accum
        self._regen_accum = 0.0
        N = self.GW * self.GH
        for idx in range(N):
            if self.state[idx] == self.BURNED:
                self.regen_t[idx] += step
                if self.regen_t[idx] >= self.recover_T:
                    jitter = (self.rng.random() * 2 - 1) * self.fuel_load_var
                    self.fuel[idx] = max(0.1, self.fuel_load_mean * (1.0 + jitter))
                    m_jit = (self.rng.random() * 2 - 1) * 0.05
                    self.moist[idx] = max(0.0, min(1.0, self.moisture_live + m_jit))
                    self.state[idx] = self.UNBURNED
                    self.burn_t[idx] = 0.0
                    self.regen_t[idx] = 0.0
                    self.tag[idx] = 0  # clear stale tag

    def update(self, dt: float):
        had_burning = (len(self.active) > 0)
        if not had_burning:
            self._episode_has_incident = False

        self.sim_t += dt
        self._update_incidents(dt)

        if not self.active:
            self._recover_burned(dt)
            if had_burning and not self.active and not self._episode_has_incident:
                self.undetected_count += 1
            return

        next_active: List[int] = []
        seen_next = set()
        live_tag_ids = {inc["id"] for inc in self.incidents if inc.get("zone_live", False)}

        for idx in self.active:
            if self.state[idx] != self.BURNING:
                continue

            tagged = (self.tag[idx] in live_tag_ids)
            boost = (1.0 + self._quench) if tagged else 1.0
            self.burn_t[idx] += dt * boost

            if self.burn_t[idx] >= self.burn_duration:
                self.state[idx] = self.BURNED
                self._ever_burned[idx] = True
                continue

            next_active.append(idx)

            if tagged:
                continue

            gx, gy = self._gxgy(idx)
            for dx, dy, dpx in self.neigh:
                ngx = gx + dx; ngy = gy + dy
                if not (0 <= ngx < self.GW and 0 <= ngy < self.GH): continue
                nidx = self._idx(ngx, ngy)
                if self.state[nidx] != self.UNBURNED: continue

                mag = math.hypot(dx, dy) + 1e-12
                diru = (dx / mag, dy / mag)
                R = self._ros_directional(diru, fuel=self.fuel[nidx], moist=self.moist[nidx])
                lam = self.k_ignite * (R * dt / max(dpx, 1e-6))
                p_ignite = 1.0 - math.exp(-max(0.0, lam))
                if self.rng.random() < p_ignite:
                    self.state[nidx] = self.BURNING
                    self.burn_t[nidx] = 0.0
                    self.t_ignited[nidx] = self.sim_t
                    if nidx not in seen_next:
                        next_active.append(nidx); seen_next.add(nidx)

            if not tagged and self.spot_chance > 0.0:
                self._ember_spot(gx, gy)

        self.active = next_active
        self._recover_burned(dt)

    # ----- drawing -----
    def draw(self, surface: pygame.Surface):
        self.overlay.fill((0, 0, 0, 0))
        c = self.cell
        for gy in range(self.GH):
            for gx in range(self.GW):
                idx = self._idx(gx, gy)
                st = self.state[idx]
                if st == self.BARRIER:
                    pygame.draw.rect(self.overlay, (120, 120, 120, 180), (gx * c, gy * c, c, c))
                elif st == self.BURNING:
                    t = max(0.0, min(1.0, self.burn_t[idx] / self.burn_duration))
                    r = min(255, 200 + int(55 * (1.0 - t)))
                    g = max(10,  30  - int(25 * t))
                    pygame.draw.rect(self.overlay, (r, g, 0, self.alpha_fire), (gx * c, gy * c, c, c))
                elif st == self.BURNED:
                    pygame.draw.rect(self.overlay, (30, 30, 30, 140), (gx * c, gy * c, c, c))

        if self.show_zone_ring:
            for inc in self.incidents:
                if inc.get("zone_live", False) and inc["zone_r"] > 2:
                    pygame.draw.circle(self.overlay, (70, 120, 255, 160),
                                       (int(inc["cx"]), int(inc["cy"])), int(inc["zone_r"]), 2)

        surface.blit(self.overlay, (0, 0))

        if self.show_grid:
            for x in range(0, cs.screen_width, c):
                pygame.draw.line(surface, (20, 20, 20), (x, 0), (x, cs.screen_height), 1)
            for y in range(0, cs.screen_height, c):
                pygame.draw.line(surface, (20, 20, 20), (0, y), (cs.screen_width, y), 1)

    # ----- accessors / flags -----
    def get_incident(self, inc_id: int):
        for inc in self.incidents:
            if inc["id"] == inc_id:
                return inc
        return None

    def mark_incident_announced(self, inc_id: int, what: str):
        inc = self.get_incident(inc_id)
        if not inc: return
        key = f"announced_{what}"
        if key in inc:
            inc[key] = True

    # ----- metrics -----
    def compute_metrics(self, m_per_px: float) -> Dict[str, float]:
        c = self.cell
        W, H = self.GW, self.GH
        burning_cells_now = 0
        burned_cells_now  = 0
        perim_edges = 0

        def in_bounds(x, y): return (0 <= x < W) and (0 <= y < H)
        FIRE_SET = (self.BURNING, self.BURNED)

        for gy in range(H):
            for gx in range(W):
                idx = self._idx(gx, gy)
                st = self.state[idx]
                if st not in FIRE_SET:
                    continue
                if st == self.BURNING:
                    burning_cells_now += 1
                elif st == self.BURNED:
                    burned_cells_now += 1
                for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    ngx, ngy = gx + dx, gy + dy
                    if not in_bounds(ngx, ngy):
                        perim_edges += 1
                    else:
                        nidx = self._idx(ngx, ngy)
                        if self.state[nidx] not in FIRE_SET:
                            perim_edges += 1

        ever_burned_cells = sum(1 for v in self._ever_burned if v)

        mpp = float(m_per_px)
        cell_area_px2 = c * c
        burning_m2  = burning_cells_now * cell_area_px2 * (mpp * mpp)
        burned_m2   = burned_cells_now  * cell_area_px2 * (mpp * mpp)
        ever_m2     = ever_burned_cells * cell_area_px2 * (mpp * mpp)
        footprint_m2 = burning_m2 + burned_m2
        perimeter_m = perim_edges * (c * mpp)

        return {
            "perimeter_m": perimeter_m,
            "burning_area_ha": burning_m2  / 10_000.0,
            "scorched_area_ha": ever_m2    / 10_000.0,
            "footprint_area_ha": footprint_m2 / 10_000.0
        }

    def compute_local_metrics(self, cx: float, cy: float, r_px: float, m_per_px: float) -> Dict[str, float]:
        c = self.cell; r2 = r_px * r_px
        gx0 = max(0, int((cx - r_px) // c))
        gx1 = min(self.GW - 1, int((cx + r_px) // c))
        gy0 = max(0, int((cy - r_px) // c))
        gy1 = min(self.GH - 1, int((cy + r_px) // c))

        burning_cells = 0
        burned_cells  = 0

        for gy in range(gy0, gy1 + 1):
            py = gy * c + 0.5 * c
            dy2 = (py - cy) * (py - cy)
            for gx in range(gx0, gx1 + 1):
                px = gx * c + 0.5 * c
                dx = px - cx
                if dx * dx + dy2 > r2:
                    continue
                idx = self._idx(gx, gy)
                st = self.state[idx]
                if st == self.BURNING:
                    burning_cells += 1
                elif st == self.BURNED:
                    burned_cells += 1

        mpp = float(m_per_px)
        cell_area_px2 = c * c
        burning_m2 = burning_cells * cell_area_px2 * (mpp * mpp)
        burned_m2  = burned_cells  * cell_area_px2 * (mpp * mpp)
        return {
            "burning_area_ha": burning_m2 / 10_000.0,
            "scorched_area_ha": burned_m2  / 10_000.0,    # local now-burned
            "footprint_area_ha": (burning_m2 + burned_m2) / 10_000.0,
            "burning_cells": burning_cells,
            "burned_cells":  burned_cells,
            "footprint_cells": burning_cells + burned_cells
        }

    # ----- finalize snapshot for summary -----
    def snapshot_finalize_open_incidents(self):
        """
        When the sim stops, snapshot current footprint for any incident without a final area.
        Does not force-announce UI events; only ensures final_areas_m2 includes all incidents once.
        """
        for inc in self.incidents:
            if inc.get("final_area_m2") is None:
                # Prefer tag-based footprint if tags exist; else use monitor disk footprint
                area = self._incident_area_by_tag_m2(inc["id"])
                if area <= 0.0:
                    fp = self.footprint_in_disc(inc["cx"], inc["cy"], inc["monitor_r"])
                    area = fp["area_m2_total"]
                inc["final_area_m2"] = area
                if not inc.get("_counted_final", False):
                    self.final_areas_m2.append(area)
                    inc["_counted_final"] = True
