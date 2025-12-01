# ui/summary_screen.py
import pygame
import configs.settings as cs


def run_summary_screen(screen: pygame.Surface, clock: pygame.time.Clock, summary: dict):
    """
    Dashboard-style summary with NO scrolling.
    Layout: 2 columns x 3 rows of cards that fit in the viewport.
    Exit keys: ESC / Q / ENTER / SPACE
    """

    # ----------------------------
    # Helpers
    # ----------------------------
    def fmt_area(m2: float) -> str:
        if m2 < 1_000:
            return f"{m2:.0f} m²"
        if m2 < 100_000:
            return f"{m2/1_000:.1f}k m²"
        return f"{m2/10_000:.2f} ha"

    def fmt_money(x: float, currency: str) -> str:
        if abs(x) >= 1000:
            return f"{currency}{x:,.0f}"
        return f"{currency}{x:,.2f}"

    def fit_font(size: int) -> pygame.font.Font:
        W, H = screen.get_size()
        scale = min(W / 1280.0, H / 720.0)
        px = max(12, int(size * scale))
        return pygame.font.Font(None, px)

    # ----------------------------
    # Colors, Fonts, Layout
    # ----------------------------
    W, H = screen.get_size()
    bg = getattr(cs, "dgreen4", (6, 64, 43))
    card_bg = (20, 20, 20, 180)
    title_color = (255, 230, 160)
    header_color = (240, 240, 240)
    value_color = (230, 230, 230)
    label_color = (200, 200, 200)

    scale_y = min(W / 1280.0, H / 720.0)
    title_font  = fit_font(64)
    header_font = fit_font(30)
    label_font  = fit_font(22)
    value_font  = fit_font(28)
    foot_font   = fit_font(22)

    pad_x = int(14 * scale_y)
    pad_y = int(12 * scale_y)
    margin = int(24 * scale_y)
    col_gap = int(24 * scale_y)
    row_gap = int(18 * scale_y)

    currency = summary.get("econ_currency", "$")

    # --- card renderer (uses fonts computed above) ---
    def draw_card(surface: pygame.Surface, rect: pygame.Rect, title: str, rows):
        card = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        card.fill(card_bg)

        # Accent bar
        pygame.draw.rect(card, (255, 215, 120, 180), (0, 0, rect.width, max(4, int(4 * scale_y))),
                         border_top_left_radius=8, border_top_right_radius=8)

        # Title
        ts = header_font.render(title, True, header_color)
        card.blit(ts, (pad_x, pad_y))

        # Rows (auto-fit)
        content_top = pad_y + ts.get_height() + int(8 * scale_y)
        content_bottom = rect.height - pad_y
        available = max(0, content_bottom - content_top)
        n = max(1, len(rows))
        line_h = int(26 * scale_y)
        if n * line_h > available:
            line_h = max(18, available // n)

        y = content_top
        for label, value in rows:
            ls = label_font.render(label, True, label_color)
            vs = value_font.render(value, True, value_color)
            if vs.get_width() > rect.width - (pad_x * 2):
                vs = label_font.render(value, True, value_color)
            card.blit(ls, (pad_x, y))
            card.blit(vs, (rect.width - pad_x - vs.get_width(), y))
            y += line_h

        surface.blit(card, rect.topleft)

    # ----------------------------
    # Derived stats
    # ----------------------------
    fires_detected = int(summary.get("fires_detected", 0))
    undetected = int(summary.get("undetected_fires", 0))
    episodes = fires_detected + undetected
    detect_rate = (fires_detected / episodes * 100.0) if episodes else 0.0

    # Baseline params (for label)
    baseline_delay_min = float(summary.get("econ_baseline_delay_min", 20.0))
    baseline_ros_mps   = float(summary.get("econ_baseline_ros_mps", 1.2))

    # ----------------------------
    # Grid (2 x 3)
    # ----------------------------
    title_srf = title_font.render("Simulation Summary", True, title_color)
    title_h = title_srf.get_height()
    footer_srf = foot_font.render("ESC / ENTER / SPACE to exit", True, (200, 200, 200))
    footer_h = footer_srf.get_height()

    top_y = margin + title_h + margin
    bottom_y = H - margin - footer_h - margin
    content_h = max(100, bottom_y - top_y)

    rows_cnt = 3
    row_h = (content_h - row_gap * (rows_cnt - 1)) // rows_cnt
    col_w = (W - margin * 2 - col_gap) // 2
    left_x = margin
    right_x = margin + col_w + col_gap

    L1 = pygame.Rect(left_x,  top_y + 0 * (row_h + row_gap), col_w, row_h)
    L2 = pygame.Rect(left_x,  top_y + 1 * (row_h + row_gap), col_w, row_h)
    L3 = pygame.Rect(left_x,  top_y + 2 * (row_h + row_gap), col_w, row_h)

    R1 = pygame.Rect(right_x, top_y + 0 * (row_h + row_gap), col_w, row_h)
    R2 = pygame.Rect(right_x, top_y + 1 * (row_h + row_gap), col_w, row_h)
    R3 = pygame.Rect(right_x, top_y + 2 * (row_h + row_gap), col_w, row_h)

    # ----------------------------
    # Card data
    # ----------------------------
    # Row 1: Time (L) + Drone (R)
    time_rows = [
        ("Simulation duration", f"{summary.get('sim_time', 0.0):.2f} s"),
        ("IRL equivalent",      f"{summary.get('irl_time', '—')}"),
    ]
    drone_rows = [("Avg speed", f"{summary.get('drone_avg_speed_kmh', 0.0):.1f} km/h")]
    dists = summary.get("drone_distances_km", [0, 0, 0, 0])
    for i, km in enumerate(dists, 1):
        drone_rows.append((f"Drone {i} distance", f"{km:.2f} km"))

    # Row 2: Detection (L) + Economics (R)
    if fires_detected > 0:
        det_rows = [
            ("Fires detected",        f"{fires_detected} ({detect_rate:.0f}%)"),
            ("Avg detection (sim)",   f"{summary.get('avg_detect_time_sim', 0.0):.2f} s"),
            ("Avg detection (IRL)",   f"{summary.get('avg_detect_time_irl', '—')}"),
            ("Avg area @ detect",     fmt_area(summary.get('avg_detect_area_m2', 0.0))),
        ]
    else:
        det_rows = [
            ("Fires detected", "0"),
            ("Avg detection",  "—"),
            ("Avg area @ detect", "—"),
        ]

    pot_loss       = float(summary.get("econ_potential_loss", 0.0))
    base_loss      = float(summary.get("econ_baseline_loss_upper", 0.0))
    saved_upper    = float(summary.get("econ_saved_upper", 0.0))
    cost_per_ha    = float(summary.get("econ_cost_per_ha", 10000.0))
    total_final_m2 = float(summary.get("total_burned_m2", 0.0))
    total_detect_m2= float(summary.get("total_detect_area_m2", 0.0))
    baseline_area_per_fire_m2 = float(summary.get("econ_baseline_area_per_fire_m2", 0.0))
    incidents_counted         = int(summary.get("econ_incidents_counted", 0))

    econ_rows = [
        ("Baseline (conv.)",      f"{baseline_delay_min:.0f} min @ {baseline_ros_mps:.1f} m/s"),
        ("Baseline cost / ha",    f"{currency}{cost_per_ha:,.0f}"),
        ("Potential loss (actual)", fmt_money(pot_loss, currency)),
        ("Baseline loss (conv.)", fmt_money(base_loss, currency)),
        ("Estimated money saved", fmt_money(saved_upper, currency)),
        ("Final area (all incidents)", fmt_area(total_final_m2)),
        (f"Baseline area × {incidents_counted}", fmt_area(baseline_area_per_fire_m2 * max(incidents_counted, 0))),
    ]
    if total_detect_m2 > 0:
        econ_rows.append(("Area @ first detection (sum)", fmt_area(total_detect_m2)))

    # Row 3: Totals (L) + Incidents (R)
    totals_rows = [
        ("Total burned area",   fmt_area(summary.get("total_burned_m2", 0.0))),
        ("Total scorched area", fmt_area(summary.get("total_scorched_m2", 0.0))),
        ("Largest footprint",   fmt_area(summary.get("biggest_fire_m2", 0.0))),
    ]
    incidents_rows = [
        ("Detected fires",      f"{fires_detected}"),
        ("Undetected fires",    f"{undetected}"),
        ("Dispatch events",     f"{summary.get('dispatch_events', 0)}"),
        ("Extinguished events", f"{summary.get('extinguished_events', 0)}"),
    ]

    # ----------------------------
    # Render loop
    # ----------------------------
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_RETURN, pygame.K_SPACE):
                    return

        screen.fill(bg)
        screen.blit(title_srf, title_srf.get_rect(midtop=(W // 2, margin)))

        draw_card(screen, L1, "Run Time", time_rows)
        draw_card(screen, R1, "Drone Performance", drone_rows)
        draw_card(screen, L2, "Fire Detection", det_rows)
        draw_card(screen, R2, "Economic Impact", econ_rows)
        draw_card(screen, L3, "Totals", totals_rows)
        draw_card(screen, R3, "Incidents & Events", incidents_rows)

        screen.blit(footer_srf, footer_srf.get_rect(midbottom=(W // 2, H - margin)))

        pygame.display.flip()
        clock.tick(getattr(cs, "fps", 60))
