import os, random, time, pickle, json, datetime, requests
from pathlib import Path
from bs4 import BeautifulSoup

time.sleep(random.uniform(0, 60))  # intervalo real 4-6 min

LOGIN_URL = "https://app.practicavial.com/login"
URL = "https://app.practicavial.com/mi-calendario"

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
    for i, dia in enumerate(soup.select("div.day")):
        clases = set(dia.get("class", []))
        if "blank" in clases or "has-practica" in clases:
            continue
        fecha = dia.get("data-date")
        if fecha:
            try:
                sabado = datetime.date.fromisoformat(fecha[:10]).weekday() == 5
            except ValueError:
                sabado = i % 7 == 5
        else:
            fecha = dia.get_text(strip=True)
            sabado = i % 7 == 5
        libres[fecha] = sabado
    return libres

def login():
    r = s.get(LOGIN_URL, timeout=30)
    tok = BeautifulSoup(r.text, "html.parser").select_one("input[name=_token]")
    s.post(LOGIN_URL, timeout=30, data={
        "_token": tok["value"] if tok else "",
        "login": os.environ["WEB_USER"],
        "password": os.environ["WEB_PASS"],
    })
    print("login hecho")

valor = leer()
if valor is None:
    login()
    valor = leer()
if valor is None:
    r = s.get(URL, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    t = soup.title
    print("Estado:", r.status_code, "| URL final:", r.url,
          "| Título:", t.get_text(strip=True) if t else None)
    print("Tiene leyenda:", "llegenda-calendari" in r.text,
          "| Tiene formulario login:", "form-login" in r.text,
          "| Nº de div.day:", len(soup.select("div.day")))
    raise SystemExit("No se encontró el calendario (¿login fallido?)")
try:
    ultimo = json.loads(last_f.read_text()) if last_f.exists() else None
except ValueError:
    ultimo = None

if ultimo is not None:
    nuevos = [f for f in valor if f not in ultimo]
    if nuevos:
        lineas = [f"{f}: SÁBADO, cuesta dinero extra" if valor[f] else f"{f}: día normal"
                  for f in nuevos]
        requests.post(f"https://ntfy.sh/{TOPIC}",
                      data="Hay prácticas libres:\n" + "\n".join(lineas),
                      headers={"Title": "Autoescuela", "Priority": "high"})
last_f.write_text(json.dumps(valor))
