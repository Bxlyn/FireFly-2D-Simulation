import pygame
import configs.settings as cs
import math


def run_summary_screen(screen: pygame.Surface, clock: pygame.time.Clock, summary: dict):
    """
    Draws a clean exit summary interface.
    summary = {
        "sim_time": float,
        "irl_time": str,
        "fires_detected": int,
        "avg_detect_time_sim": float,
        "avg_detect_time_irl": str,
        "avg_detect_area_m2": float,
        "avg_final_area_m2": float,
        "biggest_fire_m2": float,
        "total_burned_m2": float,
        "total_scorched_m2": float,
        "undetected_fires": int,
        "drone_avg_speed_kmh": float,
        "drone_distances_km": list,
        "dispatch_events": int,
        "extinguished_events": int,
        "user_ignitions": int,
    }
    """

    W, H = screen.get_size()
    bg = cs.dgreen4
    title_color = (255, 230, 160)
    header_color = (240, 240, 240)
    text_color = (220, 220, 220)

    title_font = pygame.font.Font(None, 72)
    header_font = pygame.font.Font(None, 42)
    text_font = pygame.font.Font(None, 30)

    def draw_line(text, y):
        srf = text_font.render(text, True, text_color)
        rect = srf.get_rect(center=(W // 2, y))
        screen.blit(srf, rect)

    running = True
    scroll_y = 0
    scroll_speed = 45

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_RETURN, pygame.K_SPACE):
                    return

            if event.type == pygame.MOUSEWHEEL:
                scroll_y += event.y * scroll_speed

        screen.fill(bg)

        # TITLE
        title_srf = title_font.render("Simulation Summary", True, title_color)
        screen.blit(title_srf, title_srf.get_rect(center=(W // 2, 70 + scroll_y)))

        y = 150 + scroll_y

        # Section 1 — Time
        header = header_font.render("Run Time", True, header_color)
        screen.blit(header, header.get_rect(center=(W // 2, y)))
        y += 40
        draw_line(f"Simulation duration: {summary['sim_time']:.2f} sec", y); y += 35
        draw_line(f"IRL equivalent: {summary['irl_time']}", y); y += 55

        # Section 2 — Detection Metrics
        header = header_font.render("Fire Detection", True, header_color)
        screen.blit(header, header.get_rect(center=(W // 2, y)))
        y += 40

        if summary["fires_detected"] == 0:
            draw_line("No fires were detected during the simulation.", y); y += 55
        else:
            draw_line(f"Fires detected: {summary['fires_detected']}", y); y += 35
            draw_line(f"Avg detection time: {summary['avg_detect_time_sim']:.2f} sec "
                      f"(≈ {summary['avg_detect_time_irl']})", y); y += 35
            draw_line(f"Avg fire area at detection: {summary['avg_detect_area_m2']:.1f} m²", y); y += 35
            draw_line(f"Avg final area (after extinguish): {summary['avg_final_area_m2']:.1f} m²", y); y += 35
            draw_line(f"Largest fire footprint: {summary['biggest_fire_m2']:.1f} m²", y); y += 55

        # Section 3 — Global Fire Damage
        header = header_font.render("Total Damage", True, header_color)
        screen.blit(header, header.get_rect(center=(W // 2, y)))
        y += 40

        draw_line(f"Total burned area: {summary['total_burned_m2']:.1f} m²", y); y += 35
        draw_line(f"Total scorched area: {summary['total_scorched_m2']:.1f} m²", y); y += 35
        draw_line(f"Undetected Fire: {summary['undetected_fires']}", y); y += 55

        # Section 4 — Drone Performance
        header = header_font.render("Drone Performance", True, header_color)
        screen.blit(header, header.get_rect(center=(W // 2, y)))
        y += 40

        draw_line(f"Average drone speed: {summary['drone_avg_speed_kmh']:.1f} km/h", y); y += 35

        for d, dist in enumerate(summary["drone_distances_km"]):
            draw_line(f"Drone {d+1} distance traveled: {dist:.2f} km", y); y += 35

        y += 20
        draw_line(f"Dispatch events: {summary['dispatch_events']}", y); y += 35
        draw_line(f"Extinguish events: {summary['extinguished_events']}", y); y += 55

        # Section 5 — User Actions
        header = header_font.render("User Interaction", True, header_color)
        screen.blit(header, header.get_rect(center=(W // 2, y)))
        y += 40
        draw_line(f"Manual ignitions: {summary['user_ignitions']}", y); y += 60

        # Footer
        footer = text_font.render("Press ESC / ENTER / SPACE to exit", True, (200, 200, 200))
        screen.blit(footer, footer.get_rect(center=(W // 2, H - 40)))

        pygame.display.flip()
        clock.tick(cs.fps)
