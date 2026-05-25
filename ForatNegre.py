import pygame
import math
import sys
import random

# --- CONFIGURACIÓ INICIAL ---
# Mides de la pantalla i constants de la simulació
WIDTH, HEIGHT = 950, 600
SIM_HEIGHT_OFFSET = 50 # Espai a sota per a la llegenda
FPS = 60 # Perquè vagi fluid
SCALE = 22.0 # Escala per passar de matemàtiques a píxels
M = 2.0 # Aquesta és la massa del forat negre

# --- PALETA DE COLORS ---
COLOR_BG = (5, 5, 10)

# Colors per les zones geomètriques d'impacte
ZONE_DISP_COL = (10, 8, 20)
ZONE_CAPT_COL = (25, 8, 8)
ZONE_CRIT_COL = (45, 40, 10)

# Colors segons què li passa al fotó (s'escapa, cau al forat, o es queda orbitant)
TRAJ_DISP = (0, 255, 200) # Verd/Cian per dispersió
TRAJ_CAPT = (255, 80, 80) # Vermell si cau a l'horitzó d'esdeveniments
TRAJ_CRIT = (255, 220, 0) # Groc si frega l'esfera de fotons
BLUE_AIM = (50, 80, 200) # Línia d'apuntar quan s'arrossega el ratolí

WHITE = (220, 220, 220)
GRAY = (100, 100, 100)
BLACK = (0, 0, 0)

pygame.init()

# Creem la finestra
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

# Posam 350 estrelles random de fons
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

active_photons = [] # Aquí guardarem totes les línies de llum que anem disparant

# --- FUNCIONS ---

# Funció per saber quin és el centre de la simulació
def get_current_center():
    w, h = screen.get_size()
    return w // 2, (h - SIM_HEIGHT_OFFSET) // 2

# Traduir coordenades "reals" de física a píxels de la pantalla
def math_to_screen(x, y):
    cx, cy = get_current_center()
    return int(cx + x * SCALE), int(cy - y * SCALE)

# El mateix però al revés (del ratolí a física)
def screen_to_math(sx, sy):
    cx, cy = get_current_center()
    return (sx - cx) / SCALE, (cy - sy) / SCALE

# les derivades de les equacions geodèsiques en mètrica de Schwarzschild
def get_derivatives(state, mass):
    r, phi, pr, p_phi = state

    # Si ja ha travessat l'horitzó d'esdeveniments (2M), es queda allà, no cal calcular res més
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

# Mètode Runge-Kutta de quart ordre (RK4).
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

# Ajustam el pas de temps (h). Si estem a prop de l'esfera de fotons (3M),
# fem passos més petits
def calculate_step(r, mass):
    return 0.001 if abs(r - 3 * mass) < 0.1 else 0.04

# Agafa els clics del ratolí i ho converteix en un fotó amb trajectòria
def get_physics_from_input(sx, sy, ex, ey, is_h=False):

    r0 = math.hypot(sx, sy)

    # Si hem fet clic dins del forat negre, no volem disparar res
    if r0 <= 2.1 * M:
        return None

    phi0 = math.atan2(sy, sx)

    # Això és per si hem fet només un clic ràpid o hem arrossegat per donar velocitat
    if is_h:
        vx, vy = (-1.0 if sx > 0 else 1.0), 0.0
    else:
        vx, vy = (ex - sx) * 0.15, (ey - sy) * 0.15

    # Moment angular (L) del fotó
    L = (sx * vy - sy * vx)

    b = abs(L)
    b_crit = 3 * math.sqrt(3) * M # Paràmetre d'impacte crític

    f0 = 1.0 - (2.0 * M / r0)

    pr2 = (
        (1.0 / (f0 ** 2))
        - (L ** 2 / (f0 * r0 ** 2))
    )

    # Condició invàlida, descartem el fotó
    if pr2 < 0:
        return None

    state = [
        r0,
        phi0,
        (vx * (sx / r0) + vy * (sy / r0)) / f0,
        L
    ]

    # Ara simulam mentalment el futur d'aquest fotó (sense dibuixar-lo) per saber el seu color
    test_st = list(state)
    fate = "escape"

    for _ in range(4000):

        rc = test_st[0]

        if rc <= 2.05 * M:
            fate = "capture" # RIP, s'ha caigut al forat negre
            break

        elif rc > 120:
            break # S'ha salvat, ha sortit volant lluny

        test_st = rk4_step(
            test_st,
            M,
            calculate_step(rc, M)
        )

    # Triam el color segons com de prop ha passat o si ha estat capturat
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

# Calculam els nous punts per on passa la línia cada vegada que actualitzam la pantalla
def update_photon(p):

    # Calculam 12 passos de cop cada frame, perquè no vagi tan lent
    for _ in range(12):

        if not p['alive']:
            break

        h = calculate_step(p['state'][0], M)

        p['state'] = rk4_step(p['state'], M, h)

        r = p['state'][0]
        phi = p['state'][1]

        # Si cau al forat..., s'acaba
        if r <= 2.05 * M:
            p['alive'] = False
            p['captured'] = True
            break

        # Afegim el punt per dibuixar la línia després
        p['points_math'].append((
            r * math.cos(phi),
            r * math.sin(phi)
        ))

        # Posam límits per no guardar memòria infinita si se'n va súper lluny
        if r > 150 or len(p['points_math']) > 8000:
            p['alive'] = False


# --- BUCLE PRINCIPAL ---

is_dragging = False # Variable per saber si estem arrossegant el ratolí

start_math = (0, 0)
curr_math = (0, 0)

running = True

while running:

    curr_w, curr_h = screen.get_size()
    curr_sim_h = curr_h - SIM_HEIGHT_OFFSET

    cx, cy = get_current_center()

    for event in pygame.event.get():

        # Per tancar la pestanya bé
        if event.type == pygame.QUIT:
            running = False

        # Si cliquem l'esquerra del ratolí (començo a apuntar)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:

            is_dragging = True
            mouse_start_pos = event.pos

            start_math = screen_to_math(*event.pos)

        # Si deixem anar el clic (disparem el fotó)
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

            # Si quasi no hem mogut el ratolí, el disparam horitzontal
            data = get_physics_from_input(
                *start_math,
                *curr_math,
                is_h=(dist < 5)
            )

            if data:
                active_photons.append(data) # L'afegeim a l'array perquè es renderitzi

        # Si estem movent el ratolí mentre apretam
        elif event.type == pygame.MOUSEMOTION and is_dragging:

            curr_math = screen_to_math(*event.pos)

        # Events del teclat
        elif event.type == pygame.KEYDOWN:

            if event.key == pygame.K_c:
                active_photons.clear() # C: Netejam la pantalla si ja hi ha massa línies

            elif event.key == pygame.K_UP:
                M = min(5.0, M + 0.1) # Pujam la massa i escombram la pantalla perquè els fotons ja no tindrien sentit
                active_photons.clear()

            elif event.key == pygame.K_DOWN:
                M = max(1.0, M - 0.1) # Baixam la massa, però no menys d'1
                active_photons.clear()

    # Toca moure la física de tots els fotons que estiguin vius a la pantalla
    for p in active_photons:

        if p['alive']:
            update_photon(p)

    screen.fill(COLOR_BG)

    # 1. Zones de fons (Aquelles franges horitzontals de colors)

    b_crit = 3 * math.sqrt(3) * M
    b_px = int(b_crit * SCALE)

    # Pintam la zona on es dispersen
    pygame.draw.rect(
        screen,
        ZONE_DISP_COL,
        (0, 0, curr_w, cy - b_px)
    )

    # Pintam la banda central de "zona de perill" (captura)
    pygame.draw.rect(
        screen,
        ZONE_CAPT_COL,
        (0, cy - b_px, curr_w, 2 * b_px)
    )

    # Pintam l'altra zona de dispersió (a sota)
    pygame.draw.rect(
        screen,
        ZONE_DISP_COL,
        (0, cy + b_px, curr_w, curr_sim_h - (cy + b_px))
    )

    # Línies exactes del límit crític superior i inferior
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

    rs_px = int(2 * M * SCALE) # Radi de Schwarzschild en píxels
    rph_px = int(3 * M * SCALE) # Esfera de fotons en píxels

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

    # Un cercle ben negre per al forat (2M)
    pygame.draw.circle(screen, BLACK, (cx, cy), rs_px)
    pygame.draw.circle(screen, GRAY, (cx, cy), rs_px, 2) # i un contorn per si de cas no es veu

    # Un altre cercle per la Photon Sphere a 3M, amb el color crític
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

            # Dibuixam el fil de la trajectòria
            pygame.draw.lines(
                screen,
                p['color']
                if p['alive'] or not p['captured']
                else (180, 0, 0), # Si es mor al final, el fem vermell fosc
                False,
                pts,
                2
            )

            # Aquí escrivim l'equació a sobre de cada línia d'inici
            sx, sy = math_to_screen(*p['start_math'])

            txt = font.render(
                f"(dr/dφ)² = r⁴/{p['b'] ** 2:.1f} - r²(1 - {2 * M:.1f}/r)",
                True,
                p['color']
            )

            txt_w = txt.get_width()
            txt_h = txt.get_height()

            # Ajustam on posam el text perquè no surti per la dreta de la pantalla
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

            # Li posam un fonduet negre al text perquè es pugui llegir a sobre de les estrelles
            bg.fill((0, 0, 0, 180))

            screen.blit(bg, (pos_x - 4, pos_y - 2))
            screen.blit(txt, (pos_x, pos_y))

    # 5. Barra d'Escala i UI

    # Barra d'1 Astronomical Unit a dalt a la dreta
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

    # Info important (M i b_crit) a dalt a l'esquerra
    screen.blit(
        font_bold.render(
            f"Massa (M): {M:.1f} | bcrit: {b_crit:.2f}",
            True,
            WHITE
        ),
        (20, 20)
    )

    # --- PREDICCIÓ VISUAL RESTAURADA ---

    # Si estem apuntant... (aquell "laser" que et diu per on anirà abans de deixar anar)
    if is_dragging:

        # Línia blava cap enrere, indica de on i cap a on disparam
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

        # Calculam una minitrajectòria provisional i la pintam fineta
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

    # Llegenda Ampliada (a la part inferior)

    # Quadre de sota on posam què vol dir cada color
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

    # Un petit for perquè escrigui tots els labels sense picar-los un a un
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

    # Aquí s'acaba de dibuixar tot el frame, li ensenyem a l'usuari
    pygame.display.flip()

    clock.tick(FPS)

pygame.quit() 
