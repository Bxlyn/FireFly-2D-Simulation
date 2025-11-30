# ui/summary_screen.py
import math
import pygame
import configs.settings as cs


# --------- Small helpers ---------
def _fmt_m2(v: float) -> str:
    if v is None:
        return "0 m²"
    try:
        v = float(v)
    except Exception:
        return "0 m²"
    if v < 1_000:
        return f"{v:.0f} m²"
    if v < 1_000_000:
        return f"{v/1_000:.1f}k m²"
    return f"{v/1_000_000:.2f}M m²"


def _fmt_s(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        return "0.00 s"
    return f"{v:.2f} s"


def _fmt_km(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        return "0.00 km"
    return f"{v:.2f} km"


def _clamp(v, a, b):
    return max(a, min(b, v))


def _draw_round_rect(srf, rect, color, radius=12):
    pygame.draw.rect(srf, color, rect, border_radius=radius)


def _draw_shadow(srf, rect, radius=16, spread=6, alpha=70):
    """Soft shadow behind cards."""
    x, y, w, h = rect
    shadow = pygame.Surface((w + spread * 2, h + spread * 2), pygame.SRCALPHA)
    pygame.draw.rect(
        shadow,
        (0, 0, 0, alpha),
        (spread, spread, w, h),
        border_radius=radius + 2
    )
    srf.blit(shadow, (x - spread, y - spread))


def _draw_header_bar(surface, W, title):
    """Fixed top header; returns header height."""
    bar_h = 70
    header = pygame.Surface((W, bar_h), pygame.SRCALPHA)
    # subtle gradient
    for y in range(bar_h):
        a = 210 - int(90 * (y / bar_h))
        pygame.draw.line(header, (0, 0, 0, a), (0, y), (W, y), 1)
    surface.blit(header, (0, 0))

    title_font = pygame.font.Font(None, 52)
    sub_font = pygame.font.Font(None, 28)
    title_srf = title_font.render(title, True, (255, 234, 190))
    surface.blit(title_srf, title_srf.get_rect(midleft=(24, bar_h // 2)))

    sub = "ESC / ENTER / SPACE to exit • PgUp/PgDn, Home/End to scroll"
    sub_srf = sub_font.render(sub, True, (210, 210, 210))
    surface.blit(sub_srf, sub_srf.get_rect(midright=(W - 24, bar_h // 2)))

    return bar_h


def _progress_ring(surface, cx, cy, r, ratio, thickness=16,
                   bg_col=(40, 40, 40), fg_col=(255, 215, 120)):
    """Draw a donut progress ring 0..1."""
    pygame.draw.circle(surface, bg_col, (cx, cy), r, thickness)
    ratio = _clamp(ratio, 0.0, 1.0)
    if ratio <= 0:
        return
    start = -math.pi / 2
    end = start + ratio * 2 * math.pi
    rect = pygame.Rect(cx - r, cy - r, 2 * r, 2 * r)
    pygame.draw.arc(surface, fg_col, rect, start, end, thickness)


def _mini_bar_chart(surface, rect, values, labels, *,
                    bar_color=(120, 190, 255), grid=True, max_value=None):
    """Simple horizontal bar chart."""
    x, y, w, h = rect
    pad = 12
    n = len(values)
    if n == 0:
        return

    if grid:
        lines = 4
        for i in range(1, lines + 1):
            lx = x + pad + (w - 2 * pad) * (i / (lines + 1))
            pygame.draw.line(surface, (55, 55, 55), (lx, y + pad), (lx, y + h - pad), 1)

    max_v = max(values) if (max_value is None) else max_value
    max_v = max(max_v, 1e-6)
    row_h = (h - 2 * pad) / n
    font = pygame.font.Font(None, 28)
    for i, v in enumerate(values):
        by = y + pad + i * row_h
        lh = row_h * 0.65
        lw = (w - 150 - 3 * pad) * (v / max_v)
        label_srf = font.render(labels[i], True, (220, 220, 220))
        surface.blit(label_srf, (x + pad, by + (lh - label_srf.get_height()) / 2))
        bx = x + 120
        pygame.draw.rect(surface, (40, 40, 40), (bx, by, w - bx - pad, lh), border_radius=6)
        pygame.draw.rect(surface, bar_color, (bx, by, lw, lh), border_radius=6)
        val_srf = font.render(_fmt_km(v), True, (230, 230, 230))
        surface.blit(val_srf, (x + w - pad - val_srf.get_width(), by + (lh - val_srf.get_height()) / 2))


def _vertical_gradient(surface, top_color, bottom_color):
    W, H = surface.get_size()
    for y in range(H):
        t = y / max(1, H - 1)
        r = int(top_color[0] * (1 - t) + bottom_color[0] * t)
        g = int(top_color[1] * (1 - t) + bottom_color[1] * t)
        b = int(top_color[2] * (1 - t) + bottom_color[2] * t)
        pygame.draw.line(surface, (r, g, b), (0, y), (W, y), 1)


# --------- Main UI ---------
def run_summary_screen(screen: pygame.Surface, clock: pygame.time.Clock, summary: dict):
    """
    Dashboard-like summary screen with robust scrolling.
    Controls:
      - Mouse wheel / two-finger: scroll
      - ↑ / ↓ : step scroll (hold supported)
      - PgUp / PgDn : page scroll
      - Home / End : jump to top/bottom
      - ESC / ENTER / SPACE or window close: exit
    """
    W, H = screen.get_size()
    bg = cs.dgreen4 if hasattr(cs, "dgreen4") else (6, 64, 43)
    bg2 = cs.dgreen3 if hasattr(cs, "dgreen3") else (2, 48, 32)

    # Fonts
    H1 = pygame.font.Font(None, 44)
    H2 = pygame.font.Font(None, 34)
    TXT = pygame.font.Font(None, 28)
    BIG = pygame.font.Font(None, 56)

    # Theme
    card_bg = (24, 28, 25, 225)
    accent = (255, 215, 120)
    text = (225, 225, 225)
    subtext = (200, 200, 200)
    ok = (120, 200, 140)
    warn = (240, 170, 60)
    danger = (230, 90, 80)

    # Extract summary with defaults
    s = summary or {}
    sim_time = float(s.get("sim_time", 0.0))
    irl_time = str(s.get("irl_time", "~0.0m"))
    fires_detected = int(s.get("fires_detected", 0))
    undetected = int(s.get("undetected_fires", 0))
    total_episodes = fires_detected + undetected
    detect_rate = (fires_detected / total_episodes) if total_episodes > 0 else 0.0

    avg_detect_time_sim = float(s.get("avg_detect_time_sim", 0.0))
    avg_detect_time_irl = str(s.get("avg_detect_time_irl", "~0.0m"))
    avg_detect_area_m2 = float(s.get("avg_detect_area_m2", 0.0))
    avg_final_area_m2 = float(s.get("avg_final_area_m2", 0.0))
    biggest_fire_m2 = float(s.get("biggest_fire_m2", 0.0))
    total_burned_m2 = float(s.get("total_burned_m2", 0.0))
    total_scorched_m2 = float(s.get("total_scorched_m2", 0.0))

    dispatch_events = int(s.get("dispatch_events", 0))
    extinguished_events = int(s.get("extinguished_events", 0))
    user_ignitions = int(s.get("user_ignitions", 0))

    drone_avg_speed = float(s.get("drone_avg_speed_kmh", 0.0))
    drone_distances_km = list(s.get("drone_distances_km", [0.0, 0.0, 0.0, 0.0]))
    if len(drone_distances_km) < 4:
        drone_distances_km += [0.0] * (4 - len(drone_distances_km))
    labels = [f"Drone {i+1}" for i in range(4)]

    # Layout constants (match draw code)
    GAP = 18
    MARGIN = 20
    COL_W = (W - MARGIN * 2 - GAP) // 2
    HEADER_H = 70
    ROW1_H = 110
    ROW2_H = 250  # Detection
    ROW3_H = 250  # Performance
    ROW4_H = 135  # Events / User cards (same height)

    # --- Scrolling setup ---
    scroll_y = 0
    SCROLL_MOUSE = 60
    SCROLL_KEY = 50
    PAGE_FACTOR = 0.85  # fraction of viewport for page scroll
    pygame.key.set_repeat(250, 35)  # hold-to-scroll

    def _content_height():
        """Pre-compute full content height for clamping (independent of scroll)."""
        y = HEADER_H + GAP           # after header
        y += ROW1_H + GAP            # overview row
        y += ROW2_H + GAP            # detection/damage row
        y += ROW3_H + GAP            # performance row
        y += ROW4_H                  # events/user row
        y += 80                      # bottom hint & padding
        return y

    running = True
    while running:
        # --- Handle input ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return

            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_RETURN, pygame.K_SPACE):
                    return

                accel = 3 if (event.mod & pygame.KMOD_SHIFT) else 1

                if event.key in (pygame.K_DOWN, pygame.K_s):
                    scroll_y -= SCROLL_KEY * accel
                elif event.key in (pygame.K_UP, pygame.K_w):
                    scroll_y += SCROLL_KEY * accel
                elif event.key == pygame.K_PAGEDOWN:
                    scroll_y -= int(H * PAGE_FACTOR)
                elif event.key == pygame.K_PAGEUP:
                    scroll_y += int(H * PAGE_FACTOR)
                elif event.key == pygame.K_END:
                    min_scroll = min(0, H - _content_height())
                    scroll_y = min_scroll
                elif event.key == pygame.K_HOME:
                    scroll_y = 0

            # Modern wheel event
            if event.type == pygame.MOUSEWHEEL:
                # Pygame: event.y > 0 is wheel UP; < 0 is wheel DOWN.
                # We want DOWN to move to later content (more negative scroll_y).
                scroll_y += event.y * SCROLL_MOUSE

            # Legacy wheel events (some platforms)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:   # wheel up
                    scroll_y += SCROLL_MOUSE
                elif event.button == 5: # wheel down
                    scroll_y -= SCROLL_MOUSE

        # Clamp scroll BEFORE drawing for immediate effect
        content_h = _content_height()
        min_scroll = min(0, H - content_h)  # negative when content taller than viewport
        scroll_y = _clamp(scroll_y, min_scroll, 0)

        # --- Draw background & header ---
        screen.fill(bg)
        _vertical_gradient(screen, bg, bg2)
        header_h = _draw_header_bar(screen, W, "Simulation Summary")

        # Content origin
        y0 = header_h + GAP + scroll_y

        # === ROW 1: Overview (full width) ===
        card1_h = ROW1_H
        card1_rect = pygame.Rect(MARGIN, y0, W - 2 * MARGIN, card1_h)
        _draw_shadow(screen, card1_rect)
        _draw_round_rect(screen, card1_rect, (24, 28, 25, 225), 12)

        col_pad = 24
        third = (card1_rect.width - col_pad * 2) // 3
        left_x = card1_rect.x + col_pad
        mid_x = left_x + third
        right_x = mid_x + third

        screen.blit(H2.render("Run Time", True, (245, 245, 245)), (left_x, card1_rect.y + 12))
        screen.blit(TXT.render(f"Simulation: {sim_time:.2f} s", True, text), (left_x, card1_rect.y + 44))
        screen.blit(TXT.render(f"IRL equivalent: {irl_time}", True, text), (left_x, card1_rect.y + 72))

        screen.blit(H2.render("Episodes", True, (245, 245, 245)), (mid_x, card1_rect.y + 12))
        screen.blit(TXT.render(f"Detected: {fires_detected}", True, text), (mid_x, card1_rect.y + 44))
        screen.blit(TXT.render(f"Undetected: {undetected}", True, text), (mid_x, card1_rect.y + 72))

        screen.blit(H2.render("Events", True, (245, 245, 245)), (right_x, card1_rect.y + 12))
        screen.blit(TXT.render(f"Dispatch: {dispatch_events}", True, text), (right_x, card1_rect.y + 44))
        screen.blit(TXT.render(f"Extinguished: {extinguished_events}", True, text), (right_x, card1_rect.y + 72))

        # === ROW 2: Detection (left) + Damage (right) ===
        y2 = card1_rect.bottom + GAP
        det_rect = pygame.Rect(MARGIN, y2, COL_W, ROW2_H)
        dmg_rect = pygame.Rect(MARGIN + COL_W + GAP, y2, COL_W, ROW2_H)

        # Detection card
        _draw_shadow(screen, det_rect)
        _draw_round_rect(screen, det_rect, (24, 28, 25, 225), 12)
        screen.blit(H1.render("Detection", True, (245, 245, 245)), (det_rect.x + 16, det_rect.y + 12))

        ring_cx = det_rect.x + 90
        ring_cy = det_rect.y + 140
        ring_r = 60
        rate_col = ok if detect_rate >= 0.8 else (warn if detect_rate >= 0.5 else danger)
        _progress_ring(screen, ring_cx, ring_cy, ring_r, detect_rate, thickness=16,
                       bg_col=(45, 45, 45), fg_col=rate_col)
        pct_txt = BIG.render(f"{int(round(detect_rate * 100))}%", True, (240, 240, 240))
        screen.blit(pct_txt, pct_txt.get_rect(center=(ring_cx, ring_cy)))
        screen.blit(TXT.render("detection rate", True, subtext),
                    (ring_cx - 60, ring_cy + ring_r + 10))

        dx = det_rect.x + 180
        dy = det_rect.y + 64
        line_gap = 34
        screen.blit(TXT.render(f"Avg time to detect: {_fmt_s(avg_detect_time_sim)}  (≈ {avg_detect_time_irl})", True, text),
                    (dx, dy)); dy += line_gap
        screen.blit(TXT.render(f"Avg area at detect: {_fmt_m2(avg_detect_area_m2)}", True, text),
                    (dx, dy)); dy += line_gap
        screen.blit(TXT.render(f"Incidents (detected): {fires_detected}", True, text),
                    (dx, dy)); dy += line_gap
        screen.blit(TXT.render(f"Episodes (undetected): {undetected}", True, text),
                    (dx, dy))

        # Damage card
        _draw_shadow(screen, dmg_rect)
        _draw_round_rect(screen, dmg_rect, (24, 28, 25, 225), 12)
        screen.blit(H1.render("Damage", True, (245, 245, 245)), (dmg_rect.x + 16, dmg_rect.y + 12))

        dx = dmg_rect.x + 16
        dy = dmg_rect.y + 64
        screen.blit(TXT.render(f"Total burned area: {_fmt_m2(total_burned_m2)}", True, text),
                    (dx, dy)); dy += line_gap
        screen.blit(TXT.render(f"Total scorched (ever): {_fmt_m2(total_scorched_m2)}", True, text),
                    (dx, dy)); dy += line_gap
        screen.blit(TXT.render(f"Avg final area (per incident): {_fmt_m2(avg_final_area_m2)}", True, text),
                    (dx, dy)); dy += line_gap
        screen.blit(TXT.render(f"Largest fire footprint: {_fmt_m2(biggest_fire_m2)}", True, text),
                    (dx, dy))

        # === ROW 3: Drone Performance (full width) ===
        y3 = max(det_rect.bottom, dmg_rect.bottom) + GAP
        perf_rect = pygame.Rect(MARGIN, y3, W - 2 * MARGIN, ROW3_H)
        _draw_shadow(screen, perf_rect)
        _draw_round_rect(screen, perf_rect, (24, 28, 25, 225), 12)
        screen.blit(H1.render("Drone Performance", True, (245, 245, 245)), (perf_rect.x + 16, perf_rect.y + 12))
        screen.blit(TXT.render(f"Average speed: {drone_avg_speed:.1f} km/h", True, text),
                    (perf_rect.x + 16, perf_rect.y + 56))

        chart_rect = pygame.Rect(perf_rect.x + 12, perf_rect.y + 90, perf_rect.width - 24, perf_rect.height - 110)
        _mini_bar_chart(screen, chart_rect, drone_distances_km, labels, bar_color=(120, 190, 255), grid=True)

        # === ROW 4: Interaction & Events (two small cards) ===
        y4 = perf_rect.bottom + GAP
        events_rect = pygame.Rect(MARGIN, y4, COL_W, ROW4_H)
        user_rect = pygame.Rect(MARGIN + COL_W + GAP, y4, COL_W, ROW4_H)

        _draw_shadow(screen, events_rect)
        _draw_round_rect(screen, events_rect, (24, 28, 25, 225), 12)
        screen.blit(H1.render("Events", True, (245, 245, 245)), (events_rect.x + 16, events_rect.y + 12))
        screen.blit(TXT.render(f"Dispatch events: {dispatch_events}", True, text),
                    (events_rect.x + 16, events_rect.y + 56))
        screen.blit(TXT.render(f"Extinguished events: {extinguished_events}", True, text),
                    (events_rect.x + 16, events_rect.y + 86))

        _draw_shadow(screen, user_rect)
        _draw_round_rect(screen, user_rect, (24, 28, 25, 225), 12)
        screen.blit(H1.render("User Interaction", True, (245, 245, 245)), (user_rect.x + 16, user_rect.y + 12))
        screen.blit(TXT.render(f"Manual ignitions: {user_ignitions}", True, text),
                    (user_rect.x + 16, user_rect.y + 56))

        # Footer hint
        hint_font = pygame.font.Font(None, 26)
        hint = hint_font.render("Scroll: Mouse wheel / PgUp/PgDn • Home/End jump", True, (210, 210, 210))
        screen.blit(hint, hint.get_rect(midbottom=(W // 2, H - 10)))

        pygame.display.flip()
        clock.tick(getattr(cs, "fps", 60))
