import pygame
import math
import sys
import random
import os
import urllib.request
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

# --- CONFIGURACIÓ INICIAL ---
# Mides de la pantalla i constants de la simulació
WIDTH, HEIGHT = 950, 600
SIM_HEIGHT_OFFSET = 50 # Espai a sota per a la llegenda
FPS = 60 # Perquè vagi fluid
SCALE = 22.0 # Escala per passar de matemàtiques a píxels
M = 2.0 # Aquesta és la massa del forat negre

# Mètode d'integració numèrica actiu.
# Es pot canviar durant la simulació amb:
# 1 = Euler, 2 = Runge-Kutta 2, 3 = Runge-Kutta 4
INTEGRATOR_METHOD = "RK4"
INTEGRATOR_NAMES = {
    "EULER": "Euler",
    "RK2": "Runge-Kutta 2",
    "RK4": "Runge-Kutta 4"
}

# --- PALETA DE COLORS ---
COLOR_BG = (5, 5, 10)
USE_REAL_BACKGROUND = True
SCRIPT_DIR = Path(__file__).resolve().parent

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
background_source = None
background_cache = {
    'key': None,
    'surface': None
}

# --- FUNCIONS ---

# Funció per saber quin és el centre de la simulació
def get_current_center():
    w, h = screen.get_size()
    return w // 2, (h - SIM_HEIGHT_OFFSET) // 2

# Traduir coordenades "reals" de física a píxels de la pantalla
def math_to_screen(x, y):
    cx, cy = get_current_center()
    return int(cx + x * SCALE), int(cy - y * SCALE)

# Manté un valor dins d'un interval.
def clamp(value, low, high):
    return max(low, min(high, value))

def load_real_background():
    global background_source

    if background_source is not None:
        return background_source

    candidate_paths = [
        SCRIPT_DIR / "JWST.jpg",
        SCRIPT_DIR / "images" / "JWST.jpg",
        Path.cwd() / "JWST.jpg",
        Path.cwd() / "images" / "JWST.jpg",
    ]

    # Primer cercam la imatge localment
    for image_path in candidate_paths:
        if image_path.is_file():
            print(f"Fons utilitzat: {image_path}")
            background_source = pygame.image.load(str(image_path)).convert()
            return background_source

    # Si no existeix, intentam descarregar-la de GitHub
    images_dir = SCRIPT_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    downloaded_path = images_dir / "JWST.jpg"

    github_url = (
        "https://raw.githubusercontent.com/"
        "psardf03/ForatNegre/main/images/JWST.jpg"
    )

    try:
        print("No s'ha trobat JWST.jpg. Es descarrega de GitHub...")
        urllib.request.urlretrieve(github_url, str(downloaded_path))

        print(f"Fons utilitzat: {downloaded_path}")
        background_source = pygame.image.load(str(downloaded_path)).convert()
        return background_source

    except Exception as error:
        print("No s'ha pogut carregar ni descarregar JWST.jpg.")
        print("Detall:", error)

        # Fons alternatiu si tot falla
        fallback = pygame.Surface((WIDTH, HEIGHT))
        fallback.fill(COLOR_BG)

        rng = random.Random(4)

        for _ in range(550):
            x = rng.randrange(WIDTH)
            y = rng.randrange(HEIGHT)
            brightness = rng.randrange(150, 256)

            pygame.draw.circle(
                fallback,
                (brightness, brightness, 255),
                (x, y),
                1
            )

        background_source = fallback.convert()
        return background_source

def scale_cover(surface, width, height):
    src_w, src_h = surface.get_size()
    scale = max(width / src_w, height / src_h)
    scaled_w = max(1, int(src_w * scale))
    scaled_h = max(1, int(src_h * scale))
    scaled = pygame.transform.smoothscale(surface, (scaled_w, scaled_h))
    crop = pygame.Rect(
        (scaled_w - width) // 2,
        (scaled_h - height) // 2,
        width,
        height
    )
    return scaled.subsurface(crop).copy()

def build_lensed_background(width, height, center, rs_px, rph_px):
    base = scale_cover(load_real_background(), width, height)

    if np is None:
        return base

    source = pygame.surfarray.array3d(base)
    result = source.copy()
    cx, cy = center
    x = np.arange(width, dtype=np.float32)[:, None]
    y = np.arange(height, dtype=np.float32)[None, :]
    dx = x - cx
    dy = y - cy
    dist = np.sqrt(dx * dx + dy * dy)
    theta = np.arctan2(dy, dx)

    shadow_px = rs_px * 0.95
    lens_outer_px = max(rph_px * 2.45, rs_px + 1)
    lens_t = np.clip((lens_outer_px - dist) / (lens_outer_px - shadow_px), 0.0, 1.0)
    strong_t = np.clip((rph_px * 1.45 - dist) / (rph_px * 1.45 - shadow_px), 0.0, 1.0)
    mask = (dist < lens_outer_px) & (dist > rs_px * 0.35)

    deflection = (rs_px * rs_px) / np.maximum(dist, rs_px * 0.55)
    src_r = np.maximum(1.0, dist - deflection * (0.25 + 0.62 * strong_t) * lens_t)
    ring_mask = dist < rph_px * 1.14
    src_r = np.where(ring_mask, np.maximum(1.0, src_r * 0.72), src_r)

    arc = 0.006 + 0.060 * (strong_t ** 1.4) + 0.010 * lens_t
    samples = []
    for offset in (-arc, -arc * 0.45, 0, arc * 0.45, arc):
        sample_theta = theta + offset
        sx = np.clip(np.rint(cx + np.cos(sample_theta) * src_r).astype(np.int32), 0, width - 1)
        sy = np.clip(np.rint(cy + np.sin(sample_theta) * src_r).astype(np.int32), 0, height - 1)
        samples.append(source[sx, sy])

    lensed = np.maximum.reduce(samples)
    brightness = (1.0 + 0.34 * lens_t)[..., None]
    lensed = np.clip(lensed.astype(np.float32) * brightness, 0, 255).astype(np.uint8)
    result[mask] = lensed[mask]

    return pygame.surfarray.make_surface(result)

def get_lensed_background(width, height, center, rs_px, rph_px):
    key = (width, height, int(center[0]), int(center[1]), int(rs_px), int(rph_px))

    if background_cache['key'] != key:
        background_cache['key'] = key
        background_cache['surface'] = build_lensed_background(width, height, center, rs_px, rph_px)

    return background_cache['surface']

def draw_transparent_rect(surface, color, rect, alpha):
    layer = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    layer.fill((*color, alpha))
    surface.blit(layer, (rect[0], rect[1]))

def draw_soft_star(surface, x, y, size, color, glow=1.0):
    x, y = int(x), int(y)
    if not (-12 <= x <= surface.get_width() + 12 and -12 <= y <= surface.get_height() + 12):
        return

    halo_radius = max(2, int(size * 3.5 * glow))
    halo = pygame.Surface((halo_radius * 2 + 1, halo_radius * 2 + 1), pygame.SRCALPHA)

    for r in range(halo_radius, 0, -1):
        alpha = int(28 * glow * (1 - r / (halo_radius + 1)) ** 2)
        pygame.draw.circle(halo, (*color, alpha), (halo_radius, halo_radius), r)

    surface.blit(halo, (x - halo_radius, y - halo_radius))
    pygame.draw.circle(surface, color, (x, y), max(1, size))

    if size > 1:
        pygame.draw.line(surface, color, (x - size - 1, y), (x + size + 1, y), 1)
        pygame.draw.line(surface, color, (x, y - size - 1), (x, y + size + 1), 1)

# Dibuixa una estrella deformada per una lent gravitacional aproximada.
# No és un traçat de raigs complet: és un efecte visual local que empeny
# la imatge cap a fora i l'estira tangencialment quan s'apropa a l'horitzó.
def draw_lensed_star(surface, center, rel_x, rel_y, size, color, rs_px, rph_px, visible_h):
    cx, cy = center
    dist = math.hypot(rel_x, rel_y)

    if dist <= 0.01:
        return

    shadow_px = rs_px * 0.96
    lens_outer_px = max(rph_px * 2.7, rs_px + 1)

    theta = math.atan2(rel_y, rel_x)
    lens_t = clamp((lens_outer_px - dist) / (lens_outer_px - shadow_px), 0.0, 1.0)
    strong_t = clamp((rph_px * 1.35 - dist) / (rph_px * 1.35 - shadow_px), 0.0, 1.0)

    apparent_dist = dist
    if lens_t > 0:
        deflection = (rs_px * rs_px) / max(dist, rs_px * 0.6)
        apparent_dist += deflection * 0.42 * lens_t

    # Les fonts molt properes a l'ombra es veuen com fragments d'anell.
    if dist < rph_px * 1.15:
        apparent_dist = max(apparent_dist, rph_px * (1.02 + 0.12 * strong_t))
    if dist < shadow_px:
        lens_t = 1.0
        strong_t = 1.0
        apparent_dist = rph_px * 1.14

    x = cx + math.cos(theta) * apparent_dist
    y = cy + math.sin(theta) * apparent_dist

    if not (-30 <= x <= surface.get_width() + 30 and -30 <= y <= visible_h + 30):
        return

    bright = 1.0 + 0.45 * lens_t
    lensed_color = tuple(min(255, int(c * bright)) for c in color)

    if lens_t < 0.18:
        draw_soft_star(surface, x, y, size, lensed_color, 0.65)
        return

    arc_span = 0.018 + 0.16 * (strong_t ** 1.4) + 0.045 * lens_t
    samples = max(4, int(6 + 18 * strong_t))
    pts = []

    for i in range(samples):
        a = -arc_span + (2 * arc_span * i / (samples - 1))
        pts.append((
            int(cx + math.cos(theta + a) * apparent_dist),
            int(cy + math.sin(theta + a) * apparent_dist)
        ))

    width = max(1, int(size + 2 * strong_t))
    glow_width = width + max(2, int(4 * strong_t))
    arc_layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    pygame.draw.lines(arc_layer, (*lensed_color, 42), False, pts, glow_width)
    pygame.draw.lines(arc_layer, (*lensed_color, 110), False, pts, max(1, width + 1))
    surface.blit(arc_layer, (0, 0))
    pygame.draw.aalines(surface, lensed_color, False, pts)

def draw_space_polish(surface, width, sim_h, center):
    overlay = pygame.Surface((width, sim_h), pygame.SRCALPHA)

    for y in range(sim_h):
        t = y / max(1, sim_h - 1)
        alpha = int(34 * (1 - abs(t - 0.5) * 1.8))
        pygame.draw.line(overlay, (10, 18, 34, max(0, alpha)), (0, y), (width, y))

    cx, cy = center
    vignette = pygame.Surface((width, sim_h), pygame.SRCALPHA)
    max_dist = math.hypot(max(cx, width - cx), max(cy, sim_h - cy))
    step = 18
    for y in range(0, sim_h, step):
        for x in range(0, width, step):
            dist = math.hypot(x + step / 2 - cx, y + step / 2 - cy)
            alpha = int(42 * clamp((dist / max_dist - 0.35) / 0.65, 0.0, 1.0))
            pygame.draw.rect(vignette, (0, 0, 0, alpha), (x, y, step, step))

    surface.blit(overlay, (0, 0))
    surface.blit(vignette, (0, 0))

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

# Mètode d'Euler explícit.
# És de primer ordre: és ràpid, però acumula més error.
def euler_step(state, mass, h):
    deriv = get_derivatives(state, mass)

    return [
        state[i] + h * deriv[i]
        for i in range(4)
    ]


# Mètode Runge-Kutta de segon ordre (RK2, punt mig).
# Primer estima la pendent inicial i després avalua la pendent al punt mig.
def rk2_step(state, mass, h):
    k1 = get_derivatives(state, mass)

    mid_state = [
        state[i] + h / 2 * k1[i]
        for i in range(4)
    ]

    k2 = get_derivatives(mid_state, mass)

    return [
        state[i] + h * k2[i]
        for i in range(4)
    ]


# Mètode Runge-Kutta de quart ordre (RK4).
# És més costós que Euler i RK2, però dona molta més precisió per cada pas.
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


# Tria quin mètode d'integració s'empra en cada pas.
def integration_step(state, mass, h, method):
    if method == "EULER":
        return euler_step(state, mass, h)

    if method == "RK2":
        return rk2_step(state, mass, h)

    # Per defecte, RK4.
    return rk4_step(state, mass, h)


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

        test_st = integration_step(
            test_st,
            M,
            calculate_step(rc, M),
            INTEGRATOR_METHOD
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

        p['state'] = integration_step(p['state'], M, h, INTEGRATOR_METHOD)

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

is_dragging = False  # Variable per saber si estem arrossegant el ratolí

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
                active_photons.append(data)  # L'afegeim a l'array perquè es renderitzi

        # Si estem movent el ratolí mentre apretam
        elif event.type == pygame.MOUSEMOTION and is_dragging:

            curr_math = screen_to_math(*event.pos)

        # Events del teclat
        elif event.type == pygame.KEYDOWN:

            if event.key == pygame.K_c:
                active_photons.clear()  # C: Netejam la pantalla si ja hi ha massa línies

            elif event.key == pygame.K_1:
                INTEGRATOR_METHOD = "EULER"
                active_photons.clear()

            elif event.key == pygame.K_2:
                INTEGRATOR_METHOD = "RK2"
                active_photons.clear()

            elif event.key == pygame.K_3:
                INTEGRATOR_METHOD = "RK4"
                active_photons.clear()

            elif event.key == pygame.K_UP:
                M = min(5.0, M + 0.1)  # Pujam la massa i escombram la pantalla perquè els fotons ja no tindrien sentit
                active_photons.clear()

            elif event.key == pygame.K_DOWN:
                M = max(1.0, M - 0.1)  # Baixam la massa, però no menys d'1
                active_photons.clear()

    # Toca moure la física de tots els fotons que estiguin vius a la pantalla
    for p in active_photons:

        if p['alive']:
            update_photon(p)

    b_crit = 3 * math.sqrt(3) * M
    b_px = int(b_crit * SCALE)
    rs_px = int(2 * M * SCALE)  # Radi de Schwarzschild en píxels
    rph_px = int(3 * M * SCALE)  # Esfera de fotons en píxels

    if USE_REAL_BACKGROUND:
        screen.blit(
            get_lensed_background(curr_w, curr_sim_h, (cx, cy), rs_px, rph_px),
            (0, 0)
        )
    else:
        screen.fill(COLOR_BG)

    # 1. Zones de fons (superposades amb transparència sobre la imatge real)
    # CORREGIT: Clamped per evitar que es dibuixin fora de curr_sim_h i facin requadres estranys
    draw_transparent_rect(screen, ZONE_DISP_COL, (0, 0, curr_w, clamp(cy - b_px, 0, curr_sim_h)), 72)

    y_top_capt = clamp(cy - b_px, 0, curr_sim_h)
    y_bot_capt = clamp(cy + b_px, 0, curr_sim_h)
    draw_transparent_rect(screen, ZONE_CAPT_COL, (0, y_top_capt, curr_w, y_bot_capt - y_top_capt), 92)

    draw_transparent_rect(screen, ZONE_DISP_COL, (0, y_bot_capt, curr_w, clamp(curr_sim_h - y_bot_capt, 0, curr_sim_h)),
                          72)

    # Línies exactes del límit crític superior i inferior (només si estan dins la pantalla visible)
    if cy - b_px < curr_sim_h:
        pygame.draw.line(screen, ZONE_CRIT_COL, (0, cy - b_px), (curr_w, cy - b_px), 2)
    if cy + b_px < curr_sim_h:
        pygame.draw.line(screen, ZONE_CRIT_COL, (0, cy + b_px), (curr_w, cy + b_px), 2)

    if not USE_REAL_BACKGROUND:
        draw_space_polish(screen, curr_w, curr_sim_h, (cx, cy))

        # 2. Estrelles procedurals, només si no s'usa la imatge real de fons
        for s in stars_data:
            draw_lensed_star(
                screen,
                (cx, cy),
                s['rel_x'],
                s['rel_y'],
                s['size'],
                s['color'],
                rs_px,
                rph_px,
                curr_sim_h
            )

    # 3. Forat Negre i Esfera Fotons
    pygame.draw.circle(screen, BLACK, (cx, cy), rs_px)
    pygame.draw.circle(screen, GRAY, (cx, cy), rs_px, 2)

    pygame.draw.circle(screen, TRAJ_CRIT, (cx, cy), rph_px, 2)
    pygame.draw.circle(screen, (120, 100, 0), (cx, cy), rph_px + 2, 1)

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

            bg = pygame.Surface((txt_w + 8, txt_h + 4), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 180))

            screen.blit(bg, (pos_x - 4, pos_y - 2))
            screen.blit(txt, (pos_x, pos_y))

    # 5. Barra d'Escala i UI
    pygame.draw.line(screen, WHITE, (curr_w - 150, 35), (curr_w - 50, 35), 2)

    txt_esc = font.render(f"{100 / SCALE:.1f} AU", True, WHITE)
    screen.blit(txt_esc, (curr_w - 100 - txt_esc.get_width() // 2, 15))

    screen.blit(
        font_bold.render(
            f"Massa (M): {M:.1f} | bcrit: {b_crit:.2f} | mètode: {INTEGRATOR_NAMES[INTEGRATOR_METHOD]}",
            True,
            WHITE
        ),
        (20, 20)
    )

    # --- AFEGIT: TEXT DE CRÈDIT JWST ---
    # Es renderitza un text petit a la cantonada inferior dreta de la simulació
    txt_credit = font.render("Credit: JWST", True, (150, 150, 150))
    # Ho col·loquem 5 píxels a l'esquerra del marge dret i 20 píxels per sobre de la llegenda
    screen.blit(txt_credit, (curr_w - txt_credit.get_width() - 10, curr_sim_h - 20))

    txt_controls = font.render("Controls: 1 Euler | 2 RK2 | 3 RK4 | C neteja | ↑/↓ massa", True, WHITE)
    screen.blit(txt_controls, (20, curr_sim_h - 20))

    # --- PREDICCIÓ VISUAL ---
    if is_dragging:
        pygame.draw.line(
            screen,
            BLUE_AIM,
            math_to_screen(*start_math),
            math_to_screen(*curr_math),
            1
        )

        p_prev = get_physics_from_input(*start_math, *curr_math)

        if p_prev:
            t_st = list(p_prev['state'])
            pts_p = []

            for i in range(400):
                h = calculate_step(t_st[0], M)
                t_st = integration_step(t_st, M, h, INTEGRATOR_METHOD)

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
                pygame.draw.lines(screen, p_prev['color'], False, pts_p, 1)

    # Llegenda Ampliada (a la part inferior)
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
            pygame.draw.rect(screen, col, (x_pos, curr_sim_h + 15, 20, 20))
        else:
            pygame.draw.circle(screen, col, (x_pos + 10, curr_sim_h + 25), 9, 2)

        screen.blit(font.render(txt, True, WHITE), (x_pos + 30, curr_sim_h + 18))

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
