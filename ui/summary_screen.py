# ui/summary_screen.py
import pygame
import configs.settings as cs


def run_summary_screen(screen: pygame.Surface, clock: pygame.time.Clock, summary: dict):
    """
    Dashboard-like summary screen with scrolling.
    Keys: ESC/Q/ENTER/SPACE to exit; Up/Down/PageUp/PageDown or MouseWheel to scroll.
    """

    W, H = screen.get_size()
    bg = cs.dgreen4
    title_color = (255, 230, 160)
    card_bg = (20, 20, 20, 180)
    header_color = (240, 240, 240)
    value_color = (230, 230, 230)
    label_color = (200, 200, 200)

    title_font  = pygame.font.Font(None, 72)
    header_font = pygame.font.Font(None, 38)
    label_font  = pygame.font.Font(None, 26)
    value_font  = pygame.font.Font(None, 32)
    foot_font   = pygame.font.Font(None, 26)

    currency = summary.get("econ_currency", "€")

    def fmt_area(m2: float) -> str:
        if m2 < 1000:
            return f"{m2:.0f} m²"
        elif m2 < 100000:
            return f"{m2/1_000:.1f}k m²"
        else:
            return f"{m2/10_000:.2f} ha"

    def fmt_money(x: float) -> str:
        # Compact: 0 decimals for big numbers; 2 decimals for small
        if abs(x) >= 1000:
            return f"{currency}{x:,.0f}"
        return f"{currency}{x:,.2f}"

    # Card drawing helper
    def draw_card(surface, x, y, w, h, title, rows):
        # rows: list[(label, value)]
        card = pygame.Surface((w, h), pygame.SRCALPHA)
        card.fill(card_bg)
        # title
        ts = header_font.render(title, True, header_color)
        card.blit(ts, (16, 12))
        # rows
        yy = 56
        for label, value in rows:
            ls = label_font.render(label, True, label_color)
            vs = value_font.render(value, True, value_color)
            card.blit(ls, (16, yy))
            card.blit(vs, (w - vs.get_width() - 16, yy))
            yy += 34
        surface.blit(card, (x, y))

    # Layout parameters
    margin = 24
    col_w = (W - margin * 3) // 2
    card_h = 200  # base height for cards in grid
    y_gap = 18

    running = True
    scroll_y = 0
    scroll_step = 60  # per wheel 'tick' or arrow press

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_RETURN, pygame.K_SPACE):
                    return
                # Scroll keys
                if event.key in (pygame.K_DOWN, pygame.K_s):
                    scroll_y -= scroll_step
                if event.key in (pygame.K_UP, pygame.K_w):
                    scroll_y += scroll_step
                if event.key == pygame.K_PAGEUP:
                    scroll_y += 3 * scroll_step
                if event.key == pygame.K_PAGEDOWN:
                    scroll_y -= 3 * scroll_step
            if event.type == pygame.MOUSEWHEEL:
                # Per pygame docs: y>0 wheel up; we move content down (increase scroll_y)
                scroll_y += event.y * scroll_step

        screen.fill(bg)

        # Title
        title_srf = title_font.render("Simulation Summary", True, title_color)
        screen.blit(title_srf, title_srf.get_rect(midtop=(W // 2, 28 + scroll_y)))

        # Start grid below title
        y0 = 110 + scroll_y

        # --- Column 1: Time & Detection ---
        x1 = margin
        y = y0

        # Time card
        draw_card(
            screen, x1, y, col_w, card_h,
            "Run Time",
            [
                ("Simulation duration", f"{summary['sim_time']:.2f} s"),
                ("IRL equivalent",      f"{summary['irl_time']}"),
                ("Dispatch events",     f"{summary.get('dispatch_events', 0)}"),
                ("Extinguish events",   f"{summary.get('extinguished_events', 0)}"),
            ],
        )
        y += card_h + y_gap

        # Detection card
        fires_detected = int(summary.get("fires_detected", 0))
        if fires_detected > 0:
            det_rows = [
                ("Fires detected",        f"{fires_detected}"),
                ("Avg detection (sim)",   f"{summary['avg_detect_time_sim']:.2f} s"),
                ("Avg detection (IRL)",   f"{summary['avg_detect_time_irl']}"),
                ("Avg area @ detect",     fmt_area(summary['avg_detect_area_m2'])),
            ]
        else:
            det_rows = [
                ("Fires detected", "0"),
                ("Avg detection",  "—"),
                ("Avg area @ detect", "—"),
                ("", ""),
            ]

        draw_card(screen, x1, y, col_w, card_h, "Fire Detection", det_rows)
        y += card_h + y_gap

        # Totals card
        draw_card(
            screen, x1, y, col_w, card_h,
            "Totals",
            [
                ("Total burned area",  fmt_area(summary.get("total_burned_m2", 0.0))),
                ("Total scorched area",fmt_area(summary.get("total_scorched_m2", 0.0))),
                ("Largest footprint",  fmt_area(summary.get("biggest_fire_m2", 0.0))),
                ("Undetected fires",   f"{summary.get('undetected_fires', 0)}"),
            ],
        )

        # --- Column 2: Drone & Economics ---
        x2 = margin * 2 + col_w
        y = y0

        # Drone performance
        rows = [("Avg speed", f"{summary.get('drone_avg_speed_kmh', 0.0):.1f} km/h")]
        dists = summary.get("drone_distances_km", [0, 0, 0, 0])
        for i, km in enumerate(dists, 1):
            rows.append((f"Drone {i} distance", f"{km:.2f} km"))
        # Ensure card tall enough
        drone_h = max(card_h, 56 + 34 * len(rows) + 16)
        draw_card(screen, x2, y, col_w, drone_h, "Drone Performance", rows)
        y += drone_h + y_gap

        # Economic impact
        pot_loss       = float(summary.get("econ_potential_loss", 0.0))
        base_loss      = float(summary.get("econ_baseline_loss_upper", 0.0))
        saved_upper    = float(summary.get("econ_saved_upper", 0.0))
        cost_per_ha    = float(summary.get("econ_cost_per_ha", 10000.0))
        total_final_m2 = float(summary.get("total_burned_m2", 0.0))
        total_detect_m2= float(summary.get("total_detect_area_m2", 0.0))

        econ_rows = [
            ("Baseline cost / ha",      f"{currency}{cost_per_ha:,.0f}"),
            ("Potential loss (actual)", fmt_money(pot_loss)),
            ("Upper-bound baseline",    fmt_money(base_loss)),
            ("Estimated money saved",   fmt_money(saved_upper)),
        ]
        # Show areas (for context)
        econ_rows.append(("Final area (all incidents)", fmt_area(total_final_m2)))
        if total_detect_m2 > 0:
            econ_rows.append(("Area @ first detection (sum)", fmt_area(total_detect_m2)))

        econ_h = max(card_h, 56 + 34 * len(econ_rows) + 16)
        draw_card(screen, x2, y, col_w, econ_h, "Economic Impact", econ_rows)
        y += econ_h + y_gap

        # Footer
        footer = foot_font.render(
            "ESC / ENTER / SPACE to exit • Up/Down/PageUp/PageDown or Mouse Wheel to scroll",
            True, (200, 200, 200)
        )
        screen.blit(footer, footer.get_rect(midbottom=(W // 2, H - 16)))

        pygame.display.flip()
        clock.tick(cs.fps)
