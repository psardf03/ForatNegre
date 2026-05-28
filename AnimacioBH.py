import pygame
import math
import sys
import random
import cv2
import numpy as np
import os

# --- INICIALITZACIÓ I DETECCIÓ DE PANTALLA ---
pygame.init()
# Obtenim les dimensions del monitor per assegurar una renderització a resolució nativa
info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h

print(f"El vídeo es guardarà a: {os.getcwd()}")
print(f"Resolució detectada: {WIDTH}x{HEIGHT}")

# Inicialització de la finestra en mode pantalla completa per a l'exportació cinemàtica
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Black Hole Physics Simulation - Full Cinematic")
clock = pygame.time.Clock()

# --- CONFIGURACIÓ ---
FPS = 60  # Tassa de fotogrames per segon objectiu pel motor gràfic i el codificador de vídeo
M = 2.0  # Massa del forat negre (amb unitats normalitzades)
SCALE = (HEIGHT / 800) * 22.0  # Factor d'escala per mapejar coordenades físiques a píxels de pantalla
H_BASE = 0.02  # Pas d'integració temporal base per al mètode RK4

LIMIT_TRAJECTORIES = 7  # Nombre màxim de geodèsiques simultànies per cicle abans del reset
TEMPS_PAUSA_FINAL = 2500  # Temps de retenció en mil·lisegons en completar el clúster de trajectòries

# Paràmetres d'inclinació per a la matriu de projecció pseudo-3D de l'embut de curvatura
MAX_TILT = 1.4
DEPTH_MULTI = -300.0  # Multiplicador de profunditat de l'espai embegut

# Definició de vectors de color (RGB) per a la interfície i els resultats de les geodèsiques
BLACK_VOID = (0, 0, 0)
SPACE_BG = (5, 5, 12)
GRID_COLOR = (30, 120, 150)
PHOTON_SPHERE_COLOR = (255, 160, 0)
CYAN_TRAJ = (0, 255, 255)  # Trajectòries de dispersió (b > b_crit)
RED_TRAJ = (255, 45, 45)  # Trajectòries de captura (b < b_crit)
STARS_WHITE = (220, 220, 255)

# --- CONFIGURACIÓ DEL VÍDEO ---
nom_arxiu = "simulacio_black_hole_cinematic.mp4"
fourcc = cv2.VideoWriter_fourcc(*'avc1')  # Còdec H264 via OpenH264 / AVC per a alta compresso-qualitat

# Instanciació del pipeline d'escriptura de vídeo de OpenCV
video_writer = cv2.VideoWriter(
    nom_arxiu,
    fourcc,
    FPS,
    (int(WIDTH), int(HEIGHT))
)

# Control d'errors en la inicialització del fitxer de sortida del frame buffer
if not video_writer.isOpened():
    print("ERROR: No s'ha pogut crear el vídeo")
    sys.exit()

# Generació pseudo-aleatòria de la distribució d'estrelles de fons per a l'efecte de camp estel·lar
stars = [((random.randint(0, WIDTH), random.randint(0, HEIGHT)), random.randint(1, 2)) for _ in range(400)]


# --- FÍSICA ---
# Resolució del sistema d'equacions diferencials de les geodèsiques
def get_derivatives(state, mass):
    r, phi, pr, p_phi = state
    # Condició de contorn interna: sota l'horitzó d'esdeveniments ($r <= 2M$) la física s'atura
    if r <= 2.0 * mass: return [0, 0, 0, 0]
    f = 1.0 - (2.0 * mass / r)
    dr = f * pr
    dphi = p_phi / (r ** 2)
    dpr = (p_phi ** 2 / r ** 3) - (mass / r ** 2) * ((1.0 / f ** 2) + pr ** 2)
    return [dr, dphi, dpr, 0]


# Algorisme d'integració numèrica de Runge-Kutta de 4t Ordre (RK4)

def rk4_step(state, mass, h):
    k1 = get_derivatives(state, mass)
    k2 = get_derivatives([state[i] + h / 2 * k1[i] for i in range(4)], mass)
    k3 = get_derivatives([state[i] + h / 2 * k2[i] for i in range(4)], mass)
    k4 = get_derivatives([state[i] + h * k3[i] for i in range(4)], mass)
    return [state[i] + (h / 6) * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) for i in range(4)]


# Generador de condicions inicials (Shedding) de fotons asimptòtics des de l'infinit espacial ($r_0 = 25M$)
def spawn_photon():
    angle_spawn = random.uniform(0, 2 * math.pi)
    r0 = 25.0
    b_crit = 3 * math.sqrt(3) * M  # Paràmetre d'impacte crític teòric ($b_{\text{crit}} \approx 5.196M$)
    r_val = random.random()
    # Mostreig estratificat per assegurar representació de captures, dispersions i òrbitas quasi-crítiques
    if r_val < 0.30:
        b = random.uniform(0.1, b_crit - 1.5)
    elif r_val < 0.60:
        b = b_crit + random.uniform(2.5, 10.0)
    else:
        b = b_crit + random.uniform(-0.05, 0.05)  # Zona asimptòtica a l'esfera de fotons
    if random.random() > 0.5: b *= -1  # Simetria respecte l'eix d'aproximació (sentit horari / antihorari)
    p_phi = b  # El moment angular en la mètrica és equivalent al paràmetre d'impacte b
    f0 = 1.0 - (2.0 * M / r0)
    # Càlcul del moment radial inicial a partir de l'equació de l'energia de la mètrica (condició de nul·litat)
    pr2 = (1.0 / f0 ** 2) - (b ** 2 / (f0 * r0 ** 2))
    pr0 = -math.sqrt(max(0, pr2))  # Negatiu perquè el fotó és sempre entrant (infalling)
    return {'state': [r0, angle_spawn, pr0, p_phi], 'b': b, 'points_polar': [], 'alive': True}


# --- RENDERITZAT ---
# Projecció d'un diagrama d'encastament (embedding diagram) bidimensional en un espai 3D simulat
def project_3d(r_math, phi, tilt):
    x = r_math * SCALE * math.cos(phi)
    y = r_math * SCALE * math.sin(phi)
    R_S_screen = 2.0 * M * SCALE
    # Funció hiperbòlica per modelar analògicament la deformació espacial de l'embut d'Einstein-Rosen
    z_embut = DEPTH_MULTI * (R_S_screen / max(r_math * SCALE, R_S_screen)) ** 2 * (tilt / MAX_TILT)
    # Aplicació de la matriu de rotació sobre l'eix X (projecció de perspectiva isomètrica/paral·laxi)
    y_proj = y * math.cos(tilt) - z_embut * math.sin(tilt)
    return int(WIDTH / 2 + x), int(HEIGHT / 2 + y_proj)


# Subsistema gràfic unificat per al tractament de la malla espai-temps i l'horitzó d'esdeveniments
def draw_black_hole_unified(tilt):
    R_S_screen = 2.0 * M * SCALE
    center = (WIDTH // 2, HEIGHT // 2)
    # Renderitzat de la malla de coordenades (grid) si l'angle de visió de la càmera es desvia del pla equatorial
    if tilt > 0.01:
        alpha_grid = min(255, max(0, int(255 * (tilt / MAX_TILT))))
        # Cercles concèntrics de coordenades radials
        for i in range(1, 12):
            r = 2.0 * M + i * 2
            pts = [project_3d(r, math.radians(a), tilt) for a in range(0, 361, 15)]
            pygame.draw.lines(screen, (*GRID_COLOR, alpha_grid), False, pts, 1)
        # Línies de coordenades angulars (asímutes)
        for a in range(0, 360, 30):
            pts = [project_3d(2.0 * M + i * 2, math.radians(a), tilt) for i in range(12)]
            pygame.draw.lines(screen, (*GRID_COLOR, alpha_grid), False, pts, 1)

    # Dibuix de l'Esfera de Fotons ($r = 3M$)
    r_photon = 3.0 * M
    pts_photon = [project_3d(r_photon, math.radians(a), tilt) for a in range(0, 361, 10)]
    pygame.draw.polygon(screen, (100, 60, 0), pts_photon, 6)
    pygame.draw.polygon(screen, PHOTON_SPHERE_COLOR, pts_photon, 3)

    bh_radius = int(R_S_screen)
    # Generació de l'aura d'atenuació mitjançant blending alfabètic (simulació de dispersió/absorció de fons)
    for i in range(15, 0, -1):
        dist_radius = bh_radius + i * 2
        s = pygame.Surface((dist_radius * 2, dist_radius * 2), pygame.SRCALPHA)
        alpha = int(120 * (1 - i / 15))
        pygame.draw.circle(s, (0, 0, 0, alpha), (dist_radius, dist_radius), dist_radius)
        screen.blit(s, (center[0] - dist_radius, center[1] - dist_radius))

    # Renderitzat de la singularitat/horitzó d'esdeveniments com un cos negre perfecte
    pygame.draw.circle(screen, BLACK_VOID, center, bh_radius)
    pygame.draw.circle(screen, (50, 50, 80), center, bh_radius, 2)


# --- BUCLE PRINCIPAL ---
# Autòmat o Màquina d'Estats per gestionar la seqüència cinemàtica de la simulació
estat = "INTRO_PAUSA"
frame_count = 0
tilt_actual = 0.0
fase_sim = "ESPERA"
fotons_acabats = []
foton_actual = None
temps_pausa = 0

try:
    while True:
        # Gestió d'esdeveniments d'entrada (Input poller) per a interrupció d'emergència
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    raise KeyboardInterrupt

        screen.fill(SPACE_BG)

        # Renderitzat del fons estel·lar aplicant una màscara d'oclusió a la zona de la "shadow" del forat negre
        center_scr = pygame.Vector2(WIDTH // 2, HEIGHT // 2)
        R_S_px = 2.0 * M * SCALE
        R_Photon_px = 3.0 * M * SCALE
        for pos, size in stars:
            dist = center_scr.distance_to(pygame.Vector2(pos))
            if R_S_px < dist < R_Photon_px: continue
            pygame.draw.circle(screen, STARS_WHITE, pos, size)

        # Màquina d'estats d'animació temporal: Control cinemàtic del moviment de càmera (Tilt)
        if estat == "INTRO_PAUSA":
            frame_count += 1
            if frame_count > 60:
                estat = "MOSTRAR_CURVATURA"
                frame_count = 0
        elif estat == "MOSTRAR_CURVATURA":
            tilt_actual += 0.0015  # Velocitat de baixada suau de la lent angular
            if tilt_actual >= MAX_TILT:
                tilt_actual = MAX_TILT
                estat = "PAUSA_CURVATURA"
                frame_count = 0  # REINICI CRÍTIC pel temporitzador de l'estat següent
        elif estat == "PAUSA_CURVATURA":
            frame_count += 1
            if frame_count > 700:  # Finestra temporal d'exhibició del pou de potencial geomètric en 3D
                estat = "TORNAR_AL_PLA"
                frame_count = 0
        elif estat == "TORNAR_AL_PLA":
            tilt_actual -= 0.002  # Restitutció de la perspectiva al pla equatorial bidimensional
            if tilt_actual <= 0:
                tilt_actual = 0
                estat = "SIMULACIO"
                foton_actual = spawn_photon()
                fase_sim = "DIBUIXANT"

        # Execució de la dinàmica de sistemes per a les geodèsiques de fotons actius
        if fase_sim == "DIBUIXANT" and foton_actual:
            if foton_actual['alive']:
                r_act = foton_actual['state'][0]
                # Algorisme adaptatiu per al pas de temps: redueix el pas $h$ quan s'apropa a l'horitzó
                # per minimitzar l'acumulació d'errors numèrics a zones amb gradients de curvatura infinits
                h = max(0.001, H_BASE * min(1.0, (r_act - 2 * M) / M + 0.05))

                # Sub-stepping loop: integra 12 passos temporals per fotograma gràfic per optimitzar el rendiment
                for _ in range(12):
                    foton_actual['state'] = rk4_step(foton_actual['state'], M, h)
                    r, phi = foton_actual['state'][0], foton_actual['state'][1]
                    foton_actual['points_polar'].append((r, phi))  # Registre de la traça històrica
                    # Condicions de parada: absorció irreversible de l'horitzó, escapament asimptòtic o desbordament de memòria
                    if r <= 2.005 * M or r > 50 or len(foton_actual['points_polar']) > 10000:
                        foton_actual['alive'] = False
                        break
            else:
                # El fotó ha mort; s'emmagatzema l'historial a la llista d'estàtics i s'avalua la continuïtat
                fotons_acabats.append(foton_actual)
                if len(fotons_acabats) >= LIMIT_TRAJECTORIES:
                    fase_sim = "PAUSA"
                    temps_pausa = pygame.time.get_ticks()
                else:
                    foton_actual = spawn_photon()  # Generació del següent element del clúster

        # Gestió del bucle de regeneració del clúster un cop completat el límit de trajectòries escrites
        elif fase_sim == "PAUSA" and pygame.time.get_ticks() - temps_pausa > TEMPS_PAUSA_FINAL:
            fotons_acabats = []
            foton_actual = spawn_photon()
            fase_sim = "DIBUIXANT"

        # --- PROCESSAMENT GRÀFIC DE LES TRAJECTÒRIES ---
        b_crit = 3 * math.sqrt(3) * M
        if fase_sim != "ESPERA":
            # Dibuixat dels feixos de llum integrats prèviament (trajectòries passades d'atenuació gràfica)
            for p in fotons_acabats:
                col = RED_TRAJ if abs(p['b']) < b_crit else CYAN_TRAJ
                # Conversió de coordenades polars $(\sim\text{físiques})$ a cartesianes de pantalla 3D per a cada node
                pts_screen = [project_3d(pt[0], pt[1], tilt_actual) for pt in p['points_polar']]
                if len(pts_screen) > 1:
                    pygame.draw.lines(screen, [c // 2 for c in col], False, pts_screen,
                                      1)  # Canal Alfa simulat dividint intensitat
            # Dibuixat de la geodèsica activa en temps real
            if foton_actual:
                col_act = RED_TRAJ if abs(foton_actual['b']) < b_crit else CYAN_TRAJ
                pts_act = [project_3d(pt[0], pt[1], tilt_actual) for pt in foton_actual['points_polar']]
                if len(pts_act) > 1:
                    pygame.draw.lines(screen, col_act, False, pts_act, 2)
                    pygame.draw.circle(screen, col_act, pts_act[-1], 3)  # Node frontal (cap del fotó)

        # Superposició de la singularitat geomètrica (capa superior del motor gràfic Painter's Algorithm)
        draw_black_hole_unified(tilt_actual)

        pygame.display.flip()

        # --- PIPELINE DE CAPTURA DE VÍDEO (PIXEL BUFFER EXTRACTION) ---
        # Extracció de la matriu de píxels tridimensional de la memòria de vídeo (VRAM) de Pygame
        pixels = pygame.surfarray.array3d(screen)
        # Transposició matricial de coordenades: de format Pygame (X, Y, RGB) a OpenCV (Y, X, RGB)
        pixels = pixels.transpose([1, 0, 2])
        # Conversió del model de color de RGB a BGR, requeriment natiu de l'estructura OpenCV de manipulació d'imatges
        pixels = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
        # Escriptura del frame resultant al contenidor MP4
        video_writer.write(pixels)

        clock.tick(FPS)

except KeyboardInterrupt:
    print("Gravació finalitzada per l'usuari.")
finally:
    # Tancament net de recursos del sistema: alliberament del descriptor de fitxer del vídeo i tancament de Pygame
    video_writer.release()
    pygame.quit()
    sys.exit()