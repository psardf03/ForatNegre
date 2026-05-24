import pygame
import math
import sys
import random

# --- CONFIGURACIÓ INICIAL ---
WIDTH, HEIGHT = 950, 600
SIM_HEIGHT_OFFSET = 50
FPS = 60
SCALE = 22.0
M = 2.0

# --- PALETA DE COLORS ---
COLOR_BG = (5, 5, 10)

ZONE_DISP_COL = (10, 8, 20)
ZONE_CAPT_COL = (25, 8, 8)
ZONE_CRIT_COL = (45, 40, 10)

TRAJ_DISP = (0, 255, 200)
TRAJ_CAPT = (255, 80, 80)
TRAJ_CRIT = (255, 220, 0)
BLUE_AIM = (50, 80, 200)

WHITE = (220, 220, 220)
GRAY = (100, 100, 100)
BLACK = (0, 0, 0)

pygame.init()

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Schwarzschild - Simulació de Geodèsiques")

clock = pygame.time.Clock()

try:
    font = pygame.font.SysFont("Consolas", 13)
    font_bold = pygame.font.SysFont("Consolas", 15, bold=True)
except:
    font = pygame.font.SysFont("Arial", 13)
    font_bold = pygame.font.SysFont("Arial", 15, bold=True)

# --- GENERACIÓ D'ESTRELLES (DENSITAT VARIABLE) ---
stars_data = []

for _ in range(350):
    stars_data.append({
        'rel_x': random.uniform(-1000, 1000),
        'rel_y': random.uniform(-1000, 1000),
        'size': random.choice([1, 1, 2]),
        'color': (
            random.randint(200, 255),
            random.randint(200, 255),
            random.randint(220, 255)
        )
    })

for _ in range(200):
    angle = random.uniform(0, 2 * math.pi)
    dist = random.uniform(3 * M * SCALE, 15 * M * SCALE)

    stars_data.append({
        'rel_x': dist * math.cos(angle),
        'rel_y': dist * math.sin(angle),
        'size': 1,
        'color': (255, 255, random.randint(200, 255))
    })

active_photons = []

# --- FUNCIONS ---

def get_current_center():
    w, h = screen.get_size()
    return w // 2, (h - SIM_HEIGHT_OFFSET) // 2


def math_to_screen(x, y):
    cx, cy = get_current_center()
    return int(cx + x * SCALE), int(cy - y * SCALE)


def screen_to_math(sx, sy):
    cx, cy = get_current_center()
    return (sx - cx) / SCALE, (cy - sy) / SCALE


def get_derivatives(state, mass):
    r, phi, pr, p_phi = state

    if r <= 2.01 * mass:
        return [0, 0, 0, 0]

    f = 1.0 - (2.0 * mass / r)

    dr = f * pr
    dphi = p_phi / (r ** 2)

    dpr = (
        (p_phi ** 2 / r ** 3)
        - (mass / r ** 2) * ((1.0 / f ** 2) + pr ** 2)
    )

    return [dr, dphi, dpr, 0]


def rk4_step(state, mass, h):

    k1 = get_derivatives(state, mass)

    k2 = get_derivatives(
        [state[i] + h / 2 * k1[i] for i in range(4)],
        mass
    )

    k3 = get_derivatives(
        [state[i] + h / 2 * k2[i] for i in range(4)],
        mass
    )

    k4 = get_derivatives(
        [state[i] + h * k3[i] for i in range(4)],
        mass
    )

    return [
        state[i] + (h / 6) *
        (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i])
        for i in range(4)
    ]


def calculate_step(r, mass):
    return 0.001 if abs(r - 3 * mass) < 0.1 else 0.04


def get_physics_from_input(sx, sy, ex, ey, is_h=False):

    r0 = math.hypot(sx, sy)

    if r0 <= 2.1 * M:
        return None

    phi0 = math.atan2(sy, sx)

    if is_h:
        vx, vy = (-1.0 if sx > 0 else 1.0), 0.0
    else:
        vx, vy = (ex - sx) * 0.15, (ey - sy) * 0.15

    L = (sx * vy - sy * vx)

    b = abs(L)
    b_crit = 3 * math.sqrt(3) * M

    f0 = 1.0 - (2.0 * M / r0)

    pr2 = (
        (1.0 / (f0 ** 2))
        - (L ** 2 / (f0 * r0 ** 2))
    )

    if pr2 < 0:
        return None

    state = [
        r0,
        phi0,
        (vx * (sx / r0) + vy * (sy / r0)) / f0,
        L
    ]

    test_st = list(state)
    fate = "escape"

    for _ in range(4000):

        rc = test_st[0]

        if rc <= 2.05 * M:
            fate = "capture"
            break

        elif rc > 120:
            break

        test_st = rk4_step(
            test_st,
            M,
            calculate_step(rc, M)
        )

    col = (
        TRAJ_CRIT
        if abs(b - b_crit) < 0.04
        else (
            TRAJ_CAPT
            if fate == "capture"
            else TRAJ_DISP
        )
    )

    return {
        'state': state,
        'points_math': [],
        'alive': True,
        'color': col,
        'captured': False,
        'b': b,
        'start_math': (sx, sy)
    }


def update_photon(p):

    for _ in range(12):

        if not p['alive']:
            break

        h = calculate_step(p['state'][0], M)

        p['state'] = rk4_step(p['state'], M, h)

        r = p['state'][0]
        phi = p['state'][1]

        if r <= 2.05 * M:
            p['alive'] = False
            p['captured'] = True
            break

        p['points_math'].append((
            r * math.cos(phi),
            r * math.sin(phi)
        ))

        if r > 150 or len(p['points_math']) > 8000:
            p['alive'] = False


# --- BUCLE PRINCIPAL ---

is_dragging = False

start_math = (0, 0)
curr_math = (0, 0)

running = True

while running:

    curr_w, curr_h = screen.get_size()
    curr_sim_h = curr_h - SIM_HEIGHT_OFFSET

    cx, cy = get_current_center()

    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:

            is_dragging = True
            mouse_start_pos = event.pos

            start_math = screen_to_math(*event.pos)

        elif (
            event.type == pygame.MOUSEBUTTONUP
            and event.button == 1
            and is_dragging
        ):

            is_dragging = False

            dist = math.hypot(
                event.pos[0] - mouse_start_pos[0],
                event.pos[1] - mouse_start_pos[1]
            )

            data = get_physics_from_input(
                *start_math,
                *curr_math,
                is_h=(dist < 5)
            )

            if data:
                active_photons.append(data)

        elif event.type == pygame.MOUSEMOTION and is_dragging:

            curr_math = screen_to_math(*event.pos)

        elif event.type == pygame.KEYDOWN:

            if event.key == pygame.K_c:
                active_photons.clear()

            elif event.key == pygame.K_UP:
                M = min(5.0, M + 0.1)
                active_photons.clear()

            elif event.key == pygame.K_DOWN:
                M = max(1.0, M - 0.1)
                active_photons.clear()

    for p in active_photons:

        if p['alive']:
            update_photon(p)

    screen.fill(COLOR_BG)

    # 1. Zones de fons

    b_crit = 3 * math.sqrt(3) * M
    b_px = int(b_crit * SCALE)

    pygame.draw.rect(
        screen,
        ZONE_DISP_COL,
        (0, 0, curr_w, cy - b_px)
    )

    pygame.draw.rect(
        screen,
        ZONE_CAPT_COL,
        (0, cy - b_px, curr_w, 2 * b_px)
    )

    pygame.draw.rect(
        screen,
        ZONE_DISP_COL,
        (0, cy + b_px, curr_w, curr_sim_h - (cy + b_px))
    )

    pygame.draw.line(
        screen,
        ZONE_CRIT_COL,
        (0, cy - b_px),
        (curr_w, cy - b_px),
        2
    )

    pygame.draw.line(
        screen,
        ZONE_CRIT_COL,
        (0, cy + b_px),
        (curr_w, cy + b_px),
        2
    )

    # 2. Estrelles

    rs_px = int(2 * M * SCALE)
    rph_px = int(3 * M * SCALE)

    for s in stars_data:

        # Posició pantalla
        xr = cx + s['rel_x']
        yr = cy + s['rel_y']

        # Distància al centre del BH
        dist = math.hypot(
            xr - cx,
            yr - cy
        )

        # Eliminar estrelles entre 2M i 3M
        if rs_px < dist < rph_px:
            continue

        # Dibuixar només les visibles
        if 0 <= xr <= curr_w and 0 <= yr <= curr_sim_h:
            pygame.draw.circle(
                screen,
                s['color'],
                (int(xr), int(yr)),
                s['size']
            )

    # 3. Forat Negre i Esfera Fotons

    pygame.draw.circle(screen, BLACK, (cx, cy), rs_px)
    pygame.draw.circle(screen, GRAY, (cx, cy), rs_px, 2)

    pygame.draw.circle(
        screen,
        TRAJ_CRIT,
        (cx, cy),
        rph_px,
        2
    )

    pygame.draw.circle(
        screen,
        (120, 100, 0),
        (cx, cy),
        rph_px + 2,
        1
    )

    # 4. Trajectòries i Equacions

    for p in active_photons:

        if len(p['points_math']) > 1:

            pts = [
                math_to_screen(mx, my)
                for mx, my in p['points_math']
            ]

            pygame.draw.lines(
                screen,
                p['color']
                if p['alive'] or not p['captured']
                else (180, 0, 0),
                False,
                pts,
                2
            )

            sx, sy = math_to_screen(*p['start_math'])

            txt = font.render(
                f"(dr/dφ)² = r⁴/{p['b'] ** 2:.1f} - r²(1 - {2 * M:.1f}/r)",
                True,
                p['color']
            )

            txt_w = txt.get_width()
            txt_h = txt.get_height()

            if sx + 12 + txt_w > curr_w:
                pos_x = sx - txt_w - 12
            else:
                pos_x = sx + 12

            pos_y = sy - 8

            if pos_y < 0:
                pos_y = sy + 15

            bg = pygame.Surface(
                (txt_w + 8, txt_h + 4),
                pygame.SRCALPHA
            )

            bg.fill((0, 0, 0, 180))

            screen.blit(bg, (pos_x - 4, pos_y - 2))
            screen.blit(txt, (pos_x, pos_y))

    # 5. Barra d'Escala i UI

    pygame.draw.line(
        screen,
        WHITE,
        (curr_w - 150, 35),
        (curr_w - 50, 35),
        2
    )

    txt_esc = font.render(
        f"{100 / SCALE:.1f} AU",
        True,
        WHITE
    )

    screen.blit(
        txt_esc,
        (curr_w - 100 - txt_esc.get_width() // 2, 15)
    )

    screen.blit(
        font_bold.render(
            f"Massa (M): {M:.1f} | bcrit: {b_crit:.2f}",
            True,
            WHITE
        ),
        (20, 20)
    )

    # --- PREDICCIÓ VISUAL RESTAURADA ---

    if is_dragging:

        pygame.draw.line(
            screen,
            BLUE_AIM,
            math_to_screen(*start_math),
            math_to_screen(*curr_math),
            1
        )

        p_prev = get_physics_from_input(
            *start_math,
            *curr_math
        )

        if p_prev:

            t_st = list(p_prev['state'])
            pts_p = []

            for i in range(400):

                h = calculate_step(t_st[0], M)

                t_st = rk4_step(t_st, M, h)

                if i % 2 == 0:

                    pts_p.append(
                        math_to_screen(
                            t_st[0] * math.cos(t_st[1]),
                            t_st[0] * math.sin(t_st[1])
                        )
                    )

                if t_st[0] <= 2.05 * M or t_st[0] > 100:
                    break

            if len(pts_p) > 1:

                pygame.draw.lines(
                    screen,
                    p_prev['color'],
                    False,
                    pts_p,
                    1
                )

    # -----------------------------------

    # Llegenda Ampliada

    pygame.draw.rect(
        screen,
        (20, 20, 30),
        (0, curr_sim_h, curr_w, SIM_HEIGHT_OFFSET)
    )

    labels = [
        (ZONE_DISP_COL, "Dispersió", "rect"),
        (ZONE_CAPT_COL, "Captura", "rect"),
        (ZONE_CRIT_COL, "Límit Crític", "rect"),
        (GRAY, "Horitzó d'esdeveniments (2M)", "circle"),
        (TRAJ_CRIT, "Esfera de fotons (3M)", "circle")
    ]

    step_x = curr_w // len(labels)

    for i, (col, txt, shape) in enumerate(labels):

        x_pos = 15 + i * step_x

        if shape == "rect":

            pygame.draw.rect(
                screen,
                col,
                (x_pos, curr_sim_h + 15, 20, 20)
            )

        else:

            pygame.draw.circle(
                screen,
                col,
                (x_pos + 10, curr_sim_h + 25),
                9,
                2
            )

        screen.blit(
            font.render(txt, True, WHITE),
            (x_pos + 30, curr_sim_h + 18)
        )

    pygame.display.flip()

    clock.tick(FPS)

pygame.quit()