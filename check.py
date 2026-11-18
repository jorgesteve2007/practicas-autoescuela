import os, re, random, time, pickle, json, datetime, requests
from pathlib import Path
from bs4 import BeautifulSoup

time.sleep(random.uniform(0, 60))

LOGIN_URL = "https://app.practicavial.com/login"
URL = "https://app.practicavial.com/mi-calendario"
DEBUG = False   # True solo para depurar: el log es público

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
    hoy = datetime.date.today().isoformat()
    libres = {}
    for modal in soup.select("div.modal-practiques[id^=modal-dia-]"):
        fecha = modal["id"][len("modal-dia-"):][:10]
        if fecha < hoy:
            continue
        filas = modal.select("tr.box-practica.success")   # solo libres, no las tuyas
        horas = []
        for tr in filas:
            t = tr.select_one(".practica-time")
            if not t:
                continue
            for b in t.select(".badge"):
                b.extract()
            hora = re.sub(r"\s+", " ", t.get_text(" ", strip=True))
            hora = re.split(r"\s*[-–]\s*", hora)[0]   # solo la hora de inicio
            horas.append(hora)
        if not horas:
            continue
        try:
            sabado = datetime.date.fromisoformat(fecha).weekday() == 5
        except ValueError:
            sabado = False
        if DEBUG:
            print("DIAG", fecha, "libres:", len(horas))
        libres[fecha] = [sabado, len(horas), sorted(horas)]
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
    print("Login ->", r2.status_code, "| token:", bool(tok))


valor = leer()
if valor is None:
    login()
    valor = leer()
if valor is None:
    r = s.get(URL, timeout=30)
    t = BeautifulSoup(r.text, "html.parser").title
    print("Estado:", r.status_code, "| Título:", t.get_text(strip=True) if t else None)
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
    cambios = []
    for f, (sab, n, horas) in valor.items():
        _, horas_ant = datos_antes(ultimo.get(f))
        nuevas = [h for h in horas if h not in horas_ant]
        if nuevas:
            cambios.append((f, sab, n, horas))
    if cambios:
        resumen = []
        detalle = []
        for f, sab, n, horas in cambios:
            marca = " SÁBADO, cuesta dinero extra" if sab else ""
            resumen.append(f"{f} ({n}){marca}")
            detalle.append(f"{f}: " + ", ".join(horas))
        texto = ("Hay prácticas libres:\n" + "\n".join(resumen)
                 + "\n\nHoras:\n" + "\n".join(detalle))
        requests.post(f"https://ntfy.sh/{TOPIC}", data=texto.encode("utf-8"),
                      headers={"Title": "Autoescuela", "Priority": "high",
                               "Click": "https://app.practicavial.com/mi-calendario"})
last_f.write_text(json.dumps(valor))
