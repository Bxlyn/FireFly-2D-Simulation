# ui/start_screen.py
import math
import pygame
import configs.settings as cs


def run_start_screen(screen: pygame.Surface, clock: pygame.time.Clock,
                     title: str = "FireFly 2D Simulation") -> bool:
    """
    Simple start screen. Returns True to start the simulation, False to quit.
    Controls:
      - SPACE / ENTER / Left-click = Start
      - ESC / Q / Window close     = Quit
    """
    W, H = screen.get_size()
    bg = getattr(cs, "dgreen4", (6, 64, 43))
    title_color = (240, 240, 240)
    accent = (255, 215, 120)
    text_color = (220, 220, 220)

    # Fonts
    title_font = pygame.font.Font(None, int(min(W, H) * 0.12))   # scalable big title
    subtitle_font = pygame.font.Font(None, int(min(W, H) * 0.038))
    hint_font = pygame.font.Font(None, int(min(W, H) * 0.034))

    # Pre-render title (static)
    title_srf = title_font.render(title, True, title_color)
    title_rect = title_srf.get_rect(center=(W // 2, H // 2 - int(H * 0.12)))

    # A soft outline for the title (drop shadow effect)
    shadow = pygame.Surface((title_rect.width + 6, title_rect.height + 6), pygame.SRCALPHA)
    shadow_alpha = 90
    pygame.draw.rect(shadow, (0, 0, 0, shadow_alpha), shadow.get_rect(), border_radius=8)

    # Loop state
    t = 0.0

    while True:
        # --- events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    return False
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    # Clear any queued events so they don't leak into the sim
                    pygame.event.clear()
                    return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pygame.event.clear()
                return True

        # --- draw background
        screen.fill(bg)

        # gradient wash (subtle)
        # use a vertical alpha gradient overlay
        grad = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(H):
            a = int(40 * (1.0 - y / H))
            pygame.draw.line(grad, (0, 0, 0, a), (0, y), (W, y))
        screen.blit(grad, (0, 0))

        # draw title + shadow
        shadow_rect = shadow.get_rect(center=(title_rect.centerx + 2, title_rect.centery + 2))
        screen.blit(shadow, shadow_rect)
        screen.blit(title_srf, title_rect)

        # subtitle
        subtitle_txt = "Autonomous Wildfire Patrol • Drones + Stochastic Spread"
        sub_srf = subtitle_font.render(subtitle_txt, True, text_color)
        sub_rect = sub_srf.get_rect(center=(W // 2, title_rect.centery + title_rect.height // 2 + 30))
        screen.blit(sub_srf, sub_rect)

        # blinking hint
        t += clock.get_time() / 1000.0
        pulse = 0.5 + 0.5 * math.sin(t * 3.2)  # 0..1
        a = int(140 + 115 * pulse)
        hint = "Press SPACE / ENTER or CLICK to start • ESC to quit"
        hint_srf = hint_font.render(hint, True, accent)
        # apply alpha pulse
        hint_srf.set_alpha(a)
        hint_rect = hint_srf.get_rect(center=(W // 2, H // 2 + int(H * 0.10)))
        screen.blit(hint_srf, hint_rect)

        # footer controls
        foot_txt = "Left-click: ignite a spot fire  •  Esc: quit  •  Watch terminal for live logs"
        foot_srf = hint_font.render(foot_txt, True, (210, 210, 210))
        foot_rect = foot_srf.get_rect(center=(W // 2, H - 36))
        screen.blit(foot_srf, foot_rect)

        pygame.display.flip()
        clock.tick(getattr(cs, "fps", 60))
