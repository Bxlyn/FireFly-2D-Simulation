# ui/summary_screen.py
import math
import pygame
import configs.settings as cs


def run_summary_screen(screen: pygame.Surface, clock: pygame.time.Clock, summary: dict):
    """
    Dashboard-style summary with NO scrolling.
    Ensures all content (especially Economic Impact) is fully visible by:
      1) auto-fitting rows in the card,
      2) auto-switching the Economic card to a 2-column layout if needed,
      3) and, if still necessary, shrinking fonts for that card just enough to fit.

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

    def fit_font(size_pt: int) -> pygame.font.Font:
        # Scale fonts relative to a 1280x720 baseline so the whole dashboard fits
        W, H = screen.get_size()
        scale = min(W / 1280.0, H / 720.0)
        px = max(12, int(size_pt * scale))
        return pygame.font.Font(None, px)

    # Card renderer that avoids writing attributes to pygame.Surface
    # and can switch to two columns or shrink fonts if needed.
    def draw_card(surface: pygame.Surface,
                  rect: pygame.Rect,
                  title: str,
                  rows: list,
                  allow_two_columns: bool = False):

        # Create the card canvas
        card = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        card.fill(card_bg)

        # Accent bar
        pygame.draw.rect(
            card, (255, 215, 120, 180),
            (0, 0, rect.width, max(4, int(4 * scale_y))),
            border_top_left_radius=8, border_top_right_radius=8
        )

        # Title
        ts = header_font.render(title, True, header_color)
        card.blit(ts, (pad_x, pad_y))

        # Content region geometry
        content_top = pad_y + ts.get_height() + int(8 * scale_y)
        content_bottom = rect.height - pad_y
        available_h = max(0, content_bottom - content_top)

        # Base line height from current fonts
        base_label_h = label_font.get_height()
        base_value_h = value_font.get_height()
        base_line_h = max(base_label_h, base_value_h)

        def render_one_column(lf: pygame.font.Font, vf: pygame.font.Font, y0: int, line_h: int):
            y = y0
            for label, value in rows:
                ls = lf.render(label, True, label_color)
                vs = vf.render(value, True, value_color)
                # Prevent overflow horizontally
                if vs.get_width() > rect.width - (pad_x * 2):
                    vs = lf.render(value, True, value_color)
                card.blit(ls, (pad_x, y))
                card.blit(vs, (rect.width - pad_x - vs.get_width(), y))
                y += line_h

        def render_two_columns(lf: pygame.font.Font, vf: pygame.font.Font, y0: int, line_h: int):
            rows_per_col = math.ceil(len(rows) / 2)
            left_rows = rows[:rows_per_col]
            right_rows = rows[rows_per_col:]

            col_gap_inner = int(18 * scale_y)
            col_w = (rect.width - pad_x * 2 - col_gap_inner) // 2
            x_left = pad_x
            x_right = pad_x + col_w + col_gap_inner

            # Left column
            y = y0
            for label, value in left_rows:
                ls = lf.render(label, True, label_color)
                vs = vf.render(value, True, value_color)
                if vs.get_width() > col_w:
                    vs = lf.render(value, True, value_color)
                card.blit(ls, (x_left, y))
                card.blit(vs, (x_left + col_w - vs.get_width(), y))
                y += line_h

            # Right column
            y = y0
            for label, value in right_rows:
                ls = lf.render(label, True, label_color)
                vs = vf.render(value, True, value_color)
                if vs.get_width() > col_w:
                    vs = lf.render(value, True, value_color)
                card.blit(ls, (x_right, y))
                card.blit(vs, (x_right + col_w - vs.get_width(), y))
                y += line_h

        rows_n = max(1, len(rows))
        needed_h_one = rows_n * base_line_h

        if needed_h_one <= available_h:
            # Fits in one column with current fonts
            render_one_column(label_font, value_font, content_top, base_line_h)
        else:
            if allow_two_columns:
                rows_per_col = math.ceil(rows_n / 2)
                needed_h_two = rows_per_col * base_line_h

                if needed_h_two <= available_h:
                    # Fits in two columns at current size
                    render_two_columns(label_font, value_font, content_top, base_line_h)
                else:
                    # Two columns still too tall → shrink fonts proportionally
                    shrink_two = max(0.50, min(1.0, available_h / float(max(1, needed_h_two))))
                    lf = fit_font(int(LABEL_BASE_PT * shrink_two))
                    vf = fit_font(int(VALUE_BASE_PT * shrink_two))
                    line_h = max(lf.get_height(), vf.get_height())
                    # Clamp line height to pack exactly
                    max_line_h = max(14, available_h // rows_per_col)
                    line_h = min(line_h, max_line_h)
                    render_two_columns(lf, vf, content_top, line_h)
            else:
                # One column too tall and two columns not allowed → shrink
                shrink = max(0.50, min(1.0, available_h / float(max(1, needed_h_one))))
                lf = fit_font(int(LABEL_BASE_PT * shrink))
                vf = fit_font(int(VALUE_BASE_PT * shrink))
                line_h = max(lf.get_height(), vf.get_height())
                max_line_h = max(14, available_h // rows_n)
                line_h = min(line_h, max_line_h)
                render_one_column(lf, vf, content_top, line_h)

        # Blit card to screen
        surface.blit(card, rect.topleft)

    # ----------------------------
    # Colors, Fonts, Metrics
    # ----------------------------
    W, H = screen.get_size()
    bg = getattr(cs, "dgreen4", (6, 64, 43))
    card_bg = (20, 20, 20, 180)
    title_color = (255, 230, 160)
    header_color = (240, 240, 240)
    value_color = (230, 230, 230)
    label_color = (200, 200, 200)

    scale_y = min(W / 1280.0, H / 720.0)

    # Base font sizes (points) for fit_font()
    TITLE_BASE_PT  = 64
    HEADER_BASE_PT = 30
    LABEL_BASE_PT  = 22
    VALUE_BASE_PT  = 28
    FOOT_BASE_PT   = 22

    # Fonts (responsive to window)
    title_font  = fit_font(TITLE_BASE_PT)
    header_font = fit_font(HEADER_BASE_PT)
    label_font  = fit_font(LABEL_BASE_PT)
    value_font  = fit_font(VALUE_BASE_PT)
    foot_font   = fit_font(FOOT_BASE_PT)

    # Padding
    pad_x = int(14 * scale_y)
    pad_y = int(12 * scale_y)
    margin = int(24 * scale_y)
    col_gap = int(24 * scale_y)
    row_gap = int(18 * scale_y)

    # Economic params
    currency = summary.get("econ_currency", "€")

    # Derived stats
    fires_detected = int(summary.get("fires_detected", 0))
    undetected = int(summary.get("undetected_fires", 0))
    episodes = fires_detected + undetected
    detect_rate = (fires_detected / episodes * 100.0) if episodes else 0.0

    # ----------------------------
    # Grid Geometry (2 cols x 3 rows)
    # ----------------------------
    # Reserve top for title and bottom for footer
    title_srf = title_font.render("Simulation Summary", True, title_color)
    title_h = title_srf.get_height()
    footer_srf = foot_font.render("ESC / ENTER / SPACE to exit", True, (200, 200, 200))
    footer_h = footer_srf.get_height()

    top_y = margin + title_h + margin
    bottom_y = H - margin - footer_h - margin
    content_h = max(100, bottom_y - top_y)

    # Left column: uniform thirds
    rows_per_col = 3
    row_h_left = (content_h - row_gap * (rows_per_col - 1)) // rows_per_col

    # Right column: allocate more height to the Economic card
    r1_ratio, r2_ratio, r3_ratio = 0.28, 0.44, 0.28
    total_ratio = r1_ratio + r2_ratio + r3_ratio
    r1_h = int((content_h - row_gap * 2) * (r1_ratio / total_ratio))
    r2_h = int((content_h - row_gap * 2) * (r2_ratio / total_ratio))
    r3_h = content_h - row_gap * 2 - r1_h - r2_h

    # 2 equal columns
    col_w = (W - margin * 2 - col_gap) // 2
    left_x = margin
    right_x = margin + col_w + col_gap

    # Card rects (left col: uniform)
    L1 = pygame.Rect(left_x,  top_y + 0 * (row_h_left + row_gap), col_w, row_h_left)
    L2 = pygame.Rect(left_x,  top_y + 1 * (row_h_left + row_gap), col_w, row_h_left)
    L3 = pygame.Rect(left_x,  top_y + 2 * (row_h_left + row_gap), col_w, row_h_left)

    # Right column rects (biased heights)
    R1 = pygame.Rect(right_x, top_y,                       col_w, r1_h)
    R2 = pygame.Rect(right_x, top_y + r1_h + row_gap,      col_w, r2_h)   # Economic Impact (taller)
    R3 = pygame.Rect(right_x, top_y + r1_h + row_gap + r2_h + row_gap, col_w, r3_h)

    # ----------------------------
    # Prepare Card Data
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

    econ_rows = [
        ("Baseline cost / ha",        f"{currency}{cost_per_ha:,.0f}"),
        ("Potential loss (actual)",   fmt_money(pot_loss, currency)),
        ("Baseline loss (conv.)",     fmt_money(base_loss, currency)),
        ("Estimated money saved",     fmt_money(saved_upper, currency)),
        ("Final area (all incidents)", fmt_area(total_final_m2)),
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
    # Render Loop (no scrolling)
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

        # Title
        screen.blit(title_srf, title_srf.get_rect(midtop=(W // 2, margin)))

        # Cards
        draw_card(screen, L1, "Run Time", time_rows, allow_two_columns=False)
        draw_card(screen, R1, "Drone Performance", drone_rows, allow_two_columns=False)

        draw_card(screen, L2, "Fire Detection", det_rows, allow_two_columns=False)
        draw_card(screen, R2, "Economic Impact", econ_rows, allow_two_columns=True)  # special handling

        draw_card(screen, L3, "Totals", totals_rows, allow_two_columns=False)
        draw_card(screen, R3, "Incidents & Events", incidents_rows, allow_two_columns=False)

        # Footer
        screen.blit(footer_srf, footer_srf.get_rect(midbottom=(W // 2, H - margin)))

        pygame.display.flip()
        clock.tick(getattr(cs, "fps", 60))
