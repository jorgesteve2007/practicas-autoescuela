import os, re, random, time, pickle, json, datetime, requests
from pathlib import Path
from bs4 import BeautifulSoup

time.sleep(random.uniform(0, 60))

LOGIN_URL = "https://app.practicavial.com/login"
URL = "https://app.practicavial.com/mi-calendario"
HORA = re.compile(r"\b\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\b")
DEBUG = False   # pon False cuando todo funcione

TOPIC = os.environ["NTFY_TOPIC"]
d = Path("state"); d.mkdir(exist_ok=True)
cookies_f, last_f = d / "cookies.pkl", d / "last.txt"

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0"
if cookies_f.exists():
    s.cookies.update(pickle.loads(cookies_f.read_bytes()))

def leer():
    r = s.get(URL, timeout=30)
    cookies_f.write_bytes(pickle.dumps(s.cookies))
    soup = BeautifulSoup(r.text, "html.parser")
    if not soup.select_one("#llegenda-calendari"):
        return None
    libres = {}
    for dia in soup.select("div.day[data-dia]"):
        clases = set(dia.get("class", []))
        if "past" in clases:
            continue
        # 1 y 3: el nº de prácticas libres sale del .circle,
        # tenga o no el día prácticas reservadas (has-practica)
        c = dia.select_one(".circle")
        if c is None:
            continue
        try:
            huecos = int(c.get_text(strip=True))
        except ValueError:
            continue
        if huecos < 1:
            continue
        fecha = dia["data-dia"][:10]
        try:
            sabado = datetime.date.fromisoformat(fecha).weekday() == 5
        except ValueError:
            sabado = False
        # 2: horas, si aparecen en el HTML del día (texto o atributos)
        html_dia = str(dia)
        horas = sorted(set(re.sub(r"\s+", "", h) for h in HORA.findall(html_dia)))
        if DEBUG:
            print("DIAG", fecha, "huecos:", huecos, "horas:", horas,
                  "| HTML:", re.sub(r"\s+", " ", html_dia)[:300])
        libres[fecha] = [sabado, huecos, horas]
    return libres

def login():
    h = {"Referer": LOGIN_URL, "Origin": "https://app.practicavial.com",
         "Accept": "text/html,application/xhtml+xml",
         "Accept-Language": "es-ES,es;q=0.9"}
    r = s.get(LOGIN_URL, timeout=30)
    tok = BeautifulSoup(r.text, "html.parser").select_one("input[name=_token]")
    r2 = s.post(LOGIN_URL, timeout=30, headers=h, data={
        "_token": tok["value"] if tok else "",
        "username": os.environ["WEB_USER"].strip(),
        "password": os.environ["WEB_PASS"].strip(),
    })
    print("Login ->", r2.status_code)

valor = leer()
if valor is None:
    login()
    valor = leer()
if valor is None:
    raise SystemExit("No se encontró el calendario (¿login fallido?)")

print("Resumen:", {f: v[1] for f, v in valor.items()})

try:
    ultimo = json.loads(last_f.read_text()) if last_f.exists() else None
except ValueError:
    ultimo = None

def datos_antes(a):
    # compatible con estados antiguos (bool o [sabado, huecos])
    if isinstance(a, list) and len(a) >= 3:
        return a[1], set(a[2])
    if isinstance(a, list) and len(a) == 2:
        return a[1], set()
    return (0, set()) if a is None else (1, set())

if ultimo is not None:
    lineas = []
    for f, (sab, n, horas) in valor.items():
        n_ant, horas_ant = datos_antes(ultimo.get(f))
        if n > n_ant or (set(horas) - horas_ant and n_ant > 0 and horas_ant):
            tipo = "SÁBADO, cuesta dinero extra" if sab else "día normal"
            h = ", ".join(horas) if horas else "hora no disponible"
            lineas.append(f"{f} ({tipo}): {n} práctica(s) libre(s) · {h}")
    if lineas:
        total = ", ".join(f"{f[5:]}: {v[1]}" for f, v in valor.items())
        requests.post(f"https://ntfy.sh/{TOPIC}",
                      data="Hay prácticas libres:\n" + "\n".join(lineas)
                           + f"\n\nTotal ahora → {total}",
                      headers={"Title": "Autoescuela", "Priority": "high",
                               "Click": "https://app.practicavial.com/mi-calendario"})
last_f.write_text(json.dumps(valor))
