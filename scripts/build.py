#!/usr/bin/env python3
"""Genera el boletín diario Phelan-McDermid (sitio estático en docs/).

Solo usa la biblioteca estándar de Python y fuentes gratuitas sin clave:
webs de las asociaciones, Google News, Bing News, PubMed, Europe PMC,
ClinicalTrials.gov, Bluesky y Mastodon.
Todo el texto se traduce al castellano; cada elemento conserva el enlace original.
"""
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATOS = os.path.join(RAIZ, "data")
EDICIONES = os.path.join(DATOS, "ediciones")
DOCS = os.path.join(RAIZ, "docs")
VISTOS = os.path.join(DATOS, "vistos.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MADRID = ZoneInfo("Europe/Madrid")
HOY = dt.datetime.now(MADRID).date()
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- red

def http(url, data=None, headers=None, timeout=25, reintentos=2):
    h = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "es-ES,es;q=0.9,en;q=0.8", "Cookie": "CONSENT=YES+"}
    h.update(headers or {})
    for intento in range(reintentos + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            if intento == reintentos:
                log("  ! error", url[:90], e)
                return None
            time.sleep(2 * (intento + 1))


def http_json(url, **kw):
    txt = http(url, **kw)
    try:
        return json.loads(txt) if txt else None
    except ValueError:
        return None


# ---------------------------------------------------------------- utilidades de texto

def limpiar(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def recortar(texto, n=420):
    texto = limpiar(texto)
    if len(texto) <= n:
        return texto
    corte = texto[:n]
    punto = corte.rfind(". ")
    if punto > n * 0.5:
        return corte[:punto + 1]
    return corte.rsplit(" ", 1)[0] + "…"


def clave_titulo(titulo):
    t = re.sub(r"\s[-–|]\s[^-–|]+$", "", titulo or "")  # quita " - Medio"
    t = re.sub(r"[^\w]+", " ", t.lower()).strip()
    return t[:70]


_cache_trad = {}

PALABRAS_IDIOMA = {
    "es": "el la los las de del que y en un una por para con se su al es son sobre como más síndrome niños estudio",
    "en": "the of and to in is for with on that by from are this as an be study children new syndrome",
    "fr": "le la les des du et en un une pour avec sur est dans par au aux enfants syndrome nouvelle",
    "it": "il lo la gli le di del della e che per con un una sono nel alla bambini sindrome nuova",
    "pt": "o a os as do da dos das e em um uma para com por que não na no crianças síndrome nova",
    "de": "der die das und zu den mit von ist für im ein eine auf dem des nicht kinder syndrom neue",
    "nl": "de het een en van in is op te dat met voor zijn niet aan kinderen syndroom nieuwe",
}
PALABRAS_IDIOMA = {k: set(v.split()) for k, v in PALABRAS_IDIOMA.items()}


def detectar_idioma(texto):
    palabras = re.findall(r"[a-záéíóúàèìòùâêîôûäöüçñ]+", (texto or "").lower())
    puntos = {k: sum(p in v for p in palabras) for k, v in PALABRAS_IDIOMA.items()}
    mejor = max(puntos, key=puntos.get)
    return mejor if puntos[mejor] >= 1 else ""


_bloqueo_trad = {"google": False}


def traducir(texto, pista=""):
    """Traduce al castellano (traductor web gratuito de Google; respaldo MyMemory).
    Devuelve (traducción, idioma_origen). Si no se puede traducir, devuelve el original."""
    texto = (texto or "").strip()
    if not texto:
        return "", ""
    if texto in _cache_trad:
        return _cache_trad[texto]
    idioma = detectar_idioma(texto) or pista
    if idioma == "es":
        return texto, "es"
    salida = None
    if not _bloqueo_trad["google"]:
        datos = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "es", "dt": "t", "q": texto}).encode()
        res = http_json("https://translate.googleapis.com/translate_a/single", data=datos, reintentos=1,
                        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
        if res and res[0]:
            salida = ("".join(p[0] for p in res[0] if p and p[0]), res[2] or idioma)
        else:
            _bloqueo_trad["google"] = True
            log("  ! traductor de Google no disponible: se usa MyMemory")
    if salida is None:
        r2 = http_json("https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(
            {"q": texto[:480], "langpair": "%s|es" % (idioma or "en")}))
        trad = (r2 or {}).get("responseData", {}).get("translatedText") or ""
        if trad and (r2 or {}).get("responseStatus") == 200 and not re.search(
                r"PLEASE SELECT|MYMEMORY WARNING|QUERY LENGTH LIMIT|INVALID", trad):
            salida = (html.unescape(trad), idioma or "en")
    if salida is None:
        return texto, idioma  # sin caché: se reintentará en la próxima ejecución
    _cache_trad[texto] = salida
    time.sleep(0.3)
    return salida


def fecha_rss(txt):
    try:
        return email.utils.parsedate_to_datetime(txt).date()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- noticias

_google = {"pausa": 1.5, "bloqueado": False}


def decodificar_google(link, reintento=True):
    """Convierte un enlace news.google.com/rss/articles/... en la URL original del medio."""
    if _google["bloqueado"]:
        return None
    time.sleep(_google["pausa"])
    try:
        gid = link.split("/articles/")[1].split("?")[0]
        pagina = http("https://news.google.com/articles/" + gid, reintentos=0)
        sig = re.search(r'data-n-a-sg="([^"]+)"', pagina).group(1)
        ts = re.search(r'data-n-a-ts="([^"]+)"', pagina).group(1)
        carga = ["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None,
                                 None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                 gid, int(ts), sig]
        cuerpo = "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", json.dumps(carga)]]]))
        out = http("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=cuerpo.encode(),
                   headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}, reintentos=0)
        arr = json.loads(out.split("\n\n")[1])[:-2]
        url = json.loads(arr[0][2])[1]
        return url if url.startswith("http") else None
    except Exception:  # noqa: BLE001
        # Probablemente límite de peticiones (429): espera, ralentiza y reintenta una vez
        if reintento:
            _google["pausa"] = min(_google["pausa"] * 2, 8)
            time.sleep(30)
            return decodificar_google(link, reintento=False)
        _google["bloqueado"] = True
        log("  ! Google News limita peticiones: se usan sus enlaces de redirección")
        return None


def descripcion_pagina(url):
    """Lee la meta descripción del artículo original para usarla como resumen."""
    pagina = http(url, timeout=15, reintentos=0)
    if not pagina:
        return ""
    for patron in (r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
                   r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description',
                   r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
                   r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description'):
        m = re.search(patron, pagina, re.I)
        if m and len(limpiar(m.group(1))) > 40:
            return limpiar(m.group(1))
    return ""


def google_news(consulta, idiomas, desde):
    items = []
    for hl, gl, ceid in idiomas:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": consulta, "hl": hl, "gl": gl, "ceid": ceid})
        xml = http(url)
        if not xml:
            continue
        try:
            raiz = ET.fromstring(xml)
        except ET.ParseError:
            continue
        for it in raiz.iter("item"):
            f = fecha_rss(it.findtext("pubDate"))
            if not f or f < desde:
                continue
            fuente = it.find("source")
            titulo = limpiar(it.findtext("title"))
            medio = fuente.text if fuente is not None else ""
            if medio and titulo.endswith(" - " + medio):
                titulo = titulo[: -len(" - " + medio)]
            items.append({"titulo": titulo, "link": it.findtext("link"), "medio": medio,
                          "web_medio": fuente.get("url") if fuente is not None else "",
                          "fecha": f.isoformat(), "resumen": "", "origen": "google", "hl": hl.split("-")[0]})
        time.sleep(0.5)
    return items


def bing_news(consulta, desde):
    xml = http("https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": consulta, "format": "rss"}))
    items = []
    if not xml:
        return items
    try:
        raiz = ET.fromstring(xml.encode("utf-8"))
    except ET.ParseError:
        return items
    for it in raiz.iter("item"):
        f = fecha_rss(it.findtext("pubDate"))
        if not f or f < desde:
            continue
        link = it.findtext("link") or ""
        q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
        link = q.get("url", [link])[0]
        medio = ""
        for hijo in it:
            if hijo.tag.endswith("Source"):
                medio = hijo.text or ""
        items.append({"titulo": limpiar(it.findtext("title")), "link": link, "medio": medio,
                      "fecha": f.isoformat(), "resumen": limpiar(it.findtext("description")), "origen": "bing"})
    return items


def buscar_noticias(consultas, cfg, desde):
    todos = []
    for c in consultas:
        log("  noticias:", c)
        todos += bing_news(c, desde)
        todos += google_news(c, cfg["idiomas_google_news"], desde)
    # Bing primero: trae enlace directo y extracto
    unicos = {}
    for it in todos:
        k = clave_titulo(it["titulo"])
        if k and k not in unicos:
            unicos[k] = it
    return list(unicos.values())


def completar_noticia(it):
    if it["origen"] == "google" and "news.google.com" in it["link"]:
        real = decodificar_google(it["link"])
        if real:
            it["link"] = real
    if not it["resumen"] and "news.google.com" not in it["link"]:
        it["resumen"] = descripcion_pagina(it["link"])
    if not it.get("medio"):
        it["medio"] = urllib.parse.urlparse(it["link"]).netloc.replace("www.", "")
    return it


def es_investigacion(it, palabras):
    texto = (it["titulo"] + " " + it.get("resumen", "")).lower()
    return any(re.search(r"(?<!\w)" + re.escape(p), texto) for p in palabras)


def menciona_asociacion(it):
    texto = (it["titulo"] + " " + it.get("resumen", "") + " " + it.get("medio", "")).lower()
    return bool(re.search(r"asociaci[oó]n\s+(s[ií]ndrome\s+(de\s+)?)?phelan", texto)) or "aspm" in texto.split()


# ---------------------------------------------------------------- ciencia

def pubmed(consulta, dias):
    r = http_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "term": consulta, "retmode": "json", "retmax": 60, "reldate": dias,
         "datetype": "edat", "sort": "pub_date"}))
    ids = (r or {}).get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    xml = http("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}))
    items = []
    try:
        raiz = ET.fromstring(xml.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return items
    for art in raiz.iter("PubmedArticle"):
        pmid = art.findtext(".//PMID")
        titulo = limpiar("".join(art.find(".//ArticleTitle").itertext())) if art.find(".//ArticleTitle") is not None else ""
        secciones = []
        for ab in art.findall(".//Abstract/AbstractText"):
            secciones.append(((ab.get("Label") or "").upper(), limpiar("".join(ab.itertext()))))
        resumen = resumen_abstract(secciones)
        revista = art.findtext(".//Journal/Title") or ""
        doi = ""
        for aid in art.findall(".//ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text
        tipos = [t.text or "" for t in art.findall(".//PublicationType")]
        items.append({"titulo": titulo, "resumen": resumen, "medio": revista,
                      "link": "https://pubmed.ncbi.nlm.nih.gov/%s/" % pmid,
                      "doi": "https://doi.org/" + doi if doi else "",
                      "tipo": etiqueta_tipo(tipos), "fecha": HOY.isoformat(), "id": "pmid:" + pmid})
    return items


def resumen_abstract(secciones):
    """Resumen breve: conclusiones si existen; si no, primeras frases del abstract."""
    secciones = [(et, re.sub(r"^(abstract|summary|resumen|background)\s*[:.]?\s*", "", t, flags=re.I))
                 for et, t in secciones if t]
    if not secciones:
        return ""
    for etiqueta, texto in secciones:
        if etiqueta.startswith("CONCLUSION") or etiqueta in ("INTERPRETATION", "SIGNIFICANCE"):
            return recortar(texto, 450)
    todo = " ".join(t for _, t in secciones)
    frases = re.split(r"(?<=[.!?])\s+", todo)
    if len(frases) > 3:
        return recortar(" ".join(frases[:2]) + " … " + frases[-1], 520)
    return recortar(todo, 520)


def etiqueta_tipo(tipos):
    t = " ".join(tipos).lower()
    if "clinical trial" in t:
        return "Ensayo clínico"
    if "review" in t:
        return "Revisión"
    if "case report" in t:
        return "Caso clínico"
    return "Artículo"


def preprints(consulta, desde):
    q = "%s AND SRC:PPR AND FIRST_PDATE:[%s TO %s]" % (consulta, desde.isoformat(), HOY.isoformat())
    r = http_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(
        {"query": q, "format": "json", "resultType": "core", "pageSize": 40}))
    items = []
    for x in (r or {}).get("resultList", {}).get("result", []):
        doi = x.get("doi", "")
        items.append({"titulo": limpiar(x.get("title")), "resumen": resumen_abstract([("", limpiar(x.get("abstractText")))]),
                      "medio": (x.get("bookOrReportDetails") or {}).get("publisher") or "Preprint",
                      "link": "https://doi.org/" + doi if doi else "https://europepmc.org/article/PPR/" + x.get("id", ""),
                      "doi": "", "tipo": "Preprint (sin revisión por pares)",
                      "fecha": x.get("firstPublicationDate", HOY.isoformat()), "id": "ppr:" + x.get("id", "")})
    return items


def ensayos(consulta, desde):
    r = http_json("https://clinicaltrials.gov/api/v2/studies?" + urllib.parse.urlencode({
        "query.term": consulta, "pageSize": 30, "sort": "LastUpdatePostDate:desc",
        "filter.advanced": "AREA[LastUpdatePostDate]RANGE[%s,MAX]" % desde.isoformat()}))
    items = []
    for s in (r or {}).get("studies", []):
        p = s.get("protocolSection", {})
        ident, estado = p.get("identificationModule", {}), p.get("statusModule", {})
        nct = ident.get("nctId", "")
        primera = estado.get("studyFirstPostDateStruct", {}).get("date", "")
        ultima = estado.get("lastUpdatePostDateStruct", {}).get("date", "")
        promotor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
        fases = ", ".join(p.get("designModule", {}).get("phases", []) or []).replace("PHASE", "Fase ").replace("NA", "N/A")
        situacion = estado.get("overallStatus", "").replace("_", " ").capitalize()
        nuevo = primera >= desde.isoformat()
        items.append({"titulo": limpiar(ident.get("briefTitle")),
                      "resumen": recortar(p.get("descriptionModule", {}).get("briefSummary", ""), 450),
                      "medio": promotor, "link": "https://clinicaltrials.gov/study/" + nct, "doi": "",
                      "tipo": ("Nuevo ensayo" if nuevo else "Ensayo actualizado") + (" · " + fases if fases else ""),
                      "extra": "Estado: %s · Última actualización: %s" % (situacion, ultima),
                      "fecha": ultima or HOY.isoformat(),
                      # un ensayo reaparece si se vuelve a actualizar
                      "id": "nct:%s:%s" % (nct, ultima)})
    return items


# ---------------------------------------------------------------- traducción de elementos

def traducir_item(it):
    pista = detectar_idioma(it["titulo"] + " " + (it.get("resumen") or "")) or it.get("hl", "")
    it["titulo_es"], idioma = traducir(it["titulo"], pista)
    it["idioma"] = idioma
    it["resumen_es"] = traducir(it["resumen"], pista)[0] if it.get("resumen") else ""
    it["sin_traducir"] = bool(idioma and idioma != "es" and
                              (it["titulo_es"] == it["titulo"] or (it.get("resumen") and it["resumen_es"] == it["resumen"])))
    return it


def retraducir_pendientes(dias=4):
    """Vuelve a intentar traducir lo que quedó sin traducir en ediciones recientes."""
    for i in range(dias + 1):
        ruta = os.path.join(EDICIONES, (HOY - dt.timedelta(days=i)).isoformat() + ".json")
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8") as f:
            ed = json.load(f)
        cambios = False
        for v in ed["bloques"].values():
            for it in v:
                if it.get("sin_traducir"):
                    traducir_item(it)
                    cambios = cambios or not it["sin_traducir"]
        if cambios:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(ed, f, ensure_ascii=False, indent=1, sort_keys=True)


# ---------------------------------------------------------------- HTML

CSS = """
:root{--bg:#f4f7f2;--card:#ffffff;--ink:#1f2a22;--muted:#56645a;--line:#dde6d8;
--verde-osc:#004b23;--verde:#1a692d;--verde-vivo:#38b000;--lima:#a8d144;--lima-suave:#eef7dc;
--head-bg:#004b23;--head-ink:#ffffff;--link:#1a692d;--tag-bg:#e3f1cf;--tag-ink:#1a692d;--fiable:#38b000}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 Manrope,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
h1,h2,h3,h4{font-family:Montserrat,Manrope,Arial,sans-serif}
.cabecera{background:var(--head-bg);color:var(--head-ink);border-bottom:6px solid var(--verde-vivo)}
.cabecera .in{max-width:860px;margin:0 auto;padding:22px 16px 26px}
.logo{display:inline-block;background:#fff;border-radius:12px;padding:8px 14px}
.logo img{display:block;height:44px;width:auto}
.kicker{margin-top:18px;font:700 12px/1 Montserrat,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--lima)}
h1{font-size:30px;line-height:1.2;margin:8px 0 6px;font-weight:800}
.sub{margin:0;opacity:.85;font-size:15px}
.fecha{margin-top:12px;display:inline-block;background:rgba(255,255,255,.12);padding:4px 12px;border-radius:999px;font-weight:600;font-size:14px}
.wrap{max-width:860px;margin:0 auto;padding:8px 16px 64px}
nav.indice{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 4px}
nav.indice a{font:600 14px Montserrat,sans-serif;padding:7px 14px;border-radius:999px;background:var(--card);border:1px solid var(--line);color:var(--ink);text-decoration:none}
nav.indice a:hover{border-color:var(--verde-vivo)}
nav.indice a span{display:inline-block;margin-left:6px;background:var(--verde);color:#fff;border-radius:999px;padding:0 7px;font-size:12px}
section.bloque{margin-top:36px}
section.bloque>h2{font-size:22px;margin:0 0 4px;color:var(--verde-osc);display:flex;align-items:center;gap:10px;font-weight:800}
.num{display:inline-grid;place-items:center;flex:none;width:32px;height:32px;border-radius:50%;color:#fff;font:800 15px/1 Montserrat,sans-serif}
.b1 .num{background:#004b23}.b2 .num{background:#1a692d}.b3 .num{background:#2f8f00}
.desc{color:var(--muted);font-size:14px;margin:0 0 12px}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--verde);margin:24px 0 10px;font-weight:700;
border-bottom:2px solid var(--lima);padding-bottom:4px;display:inline-block}
article{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:12px}
article.destacado{border-left:6px solid var(--verde-vivo);background:var(--lima-suave)}
article.fiable{border-left:6px solid var(--verde)}
article h4{margin:0 0 6px;font-size:17px;line-height:1.35;font-weight:700}
article h4 a{color:var(--ink);text-decoration:none}article h4 a:hover{color:var(--link);text-decoration:underline}
.meta{font-size:13px;color:var(--muted);margin-bottom:8px;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center}
.tag{font-size:12px;font-weight:700;padding:1px 8px;border-radius:6px;background:var(--tag-bg);color:var(--tag-ink)}
.resumen{margin:0 0 10px;font-size:15px}
.orig{font-size:13px;color:var(--muted);margin:0 0 8px;font-style:italic}
.fuente a{font-size:14px;font-weight:700;color:var(--link);word-break:break-word}
.vacio{color:var(--muted);font-style:italic;background:var(--card);border:1px dashed var(--line);border-radius:12px;padding:14px 18px}
.aviso{font-size:14px;background:var(--lima-suave);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:0 0 12px}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-top:12px}
summary{cursor:pointer;font-weight:700;color:var(--verde)}
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:10px}
td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}
td a,footer a,.archivo a{color:var(--link)}
.tabla{overflow-x:auto}
.archivo ul{list-style:none;padding:0;columns:2}.archivo li{margin:4px 0}
footer{margin-top:48px;border-top:3px solid var(--lima);padding-top:16px;font-size:13px;color:var(--muted)}
@media (max-width:560px){h1{font-size:24px}.archivo ul{columns:1}article{padding:14px}.logo img{height:36px}}
"""

NOMBRES_IDIOMA = {"en": "inglés", "fr": "francés", "it": "italiano", "pt": "portugués", "de": "alemán",
                  "nl": "neerlandés", "ca": "catalán", "gl": "gallego", "eu": "euskera", "ja": "japonés",
                  "zh-CN": "chino", "ko": "coreano", "pl": "polaco", "ru": "ruso", "tr": "turco",
                  "he": "hebreo", "iw": "hebreo", "sv": "sueco", "da": "danés", "no": "noruego", "fi": "finés"}


def e(x):
    return html.escape(x or "", quote=True)


def fecha_larga(d):
    return "%s, %d de %s de %d" % (DIAS[d.weekday()].capitalize(), d.day, MESES[d.month - 1], d.year)


def tarjeta(it, destacado=False):
    idioma = it.get("idioma", "")
    original = ""
    if idioma and not idioma.startswith("es") and it.get("titulo_es") != it["titulo"]:
        original = '<p class="orig">Título original (%s): %s</p>' % (e(NOMBRES_IDIOMA.get(idioma, idioma)), e(it["titulo"]))
    meta = [e(it.get("medio") or "")]
    if it.get("fecha"):
        meta.append(e(it["fecha"]))
    if it.get("extra"):
        meta.append(e(it["extra"]))
    etiqueta = '<span class="tag">%s</span> ' % e(it["tipo"]) if it.get("tipo") else ""
    enlaces = ['<a href="%s" target="_blank" rel="noopener">Fuente original ↗</a>' % e(it["link"])]
    if it.get("doi"):
        enlaces.append('<a href="%s" target="_blank" rel="noopener">DOI / artículo en la revista ↗</a>' % e(it["doi"]))
    resumen = it.get("resumen_es") or ""
    clase = "destacado" if destacado else ("fiable" if it.get("fuente_fiable") else "")
    return """<article%s>
<h4><a href="%s" target="_blank" rel="noopener">%s</a></h4>
<div class="meta">%s</div>
%s%s
<div class="fuente">%s</div>
</article>""" % (' class="%s"' % clase if clase else "", e(it["link"]), e(it.get("titulo_es") or it["titulo"]),
                  etiqueta + "<span>%s</span>" % " · ".join(m for m in meta if m),
                  '<p class="resumen">%s</p>' % e(resumen) if resumen else "", original, " &nbsp;·&nbsp; ".join(enlaces))


def lista(items, vacio, destacado=False):
    if not items:
        return '<p class="vacio">%s</p>' % vacio
    return "\n".join(tarjeta(i, destacado) for i in items)


def tabla_asociaciones(asociaciones):
    filas = []
    for a in sorted((x for x in asociaciones if not x.get("propia")), key=lambda x: (x.get("pais", ""), x["nombre"])):
        redes = " ".join('<a href="%s" target="_blank" rel="noopener">%s</a>' % (e(u), e(r.capitalize()))
                         for r, u in (a.get("redes") or {}).items() if u)
        noticias = ('<a href="%s" target="_blank" rel="noopener">Noticias</a>' % e(a["noticias"])) if a.get("noticias") else ""
        filas.append("<tr><td>%s</td><td><a href=\"%s\" target=\"_blank\" rel=\"noopener\">%s</a></td><td>%s</td><td>%s</td></tr>" % (
            e(a.get("pais", "")), e(a["web"]), e(a["nombre"]), noticias, redes))
    return ('<div class="tabla"><table><tr><th>País</th><th>Organización</th><th>Novedades</th><th>Redes</th></tr>%s</table></div>'
            % "".join(filas))


def tabla_cuentas(cuentas):
    filas = "".join('<tr><td>%s</td><td><a href="%s" target="_blank" rel="noopener">%s</a></td><td>%s</td></tr>' % (
        e(c.get("red", "Web")), e(c["link"]), e(c.get("nombre") or c.get("usuario") or c["link"]), e(c.get("creada", "")))
        for c in sorted(cuentas.values(), key=lambda c: (c.get("red", ""), (c.get("nombre") or "").lower())))
    return '<div class="tabla"><table><tr><th>Red</th><th>Cuenta / web</th><th>Creada</th></tr>%s</table></div>' % filas


def pagina(ed, cfg, fechas, asociaciones, cuentas, ruta_raiz=""):
    d = dt.date.fromisoformat(ed["fecha"])
    b = {k: ed["bloques"].get(k, []) for k in ("asociacion", "menciones", "asoc_noticias", "avances",
                                              "asoc_ciencia", "publicaciones", "ensayos", "organizaciones")}
    n1 = len(b["asociacion"]) + len(b["menciones"]) + len(b["asoc_noticias"])
    n2 = len(b["avances"]) + len(b["asoc_ciencia"]) + len(b["publicaciones"]) + len(b["ensayos"])
    n3 = len(b["organizaciones"])
    anteriores = [f for f in fechas if f != ed["fecha"]][:90]
    archivo = "".join('<li><a href="%sarchivo/%s.html">%s</a></li>' % (ruta_raiz, f, fecha_larga(dt.date.fromisoformat(f)))
                      for f in anteriores)
    sin = "Sin novedades nuevas en este apartado desde la edición anterior."
    aviso3 = ""
    if ed.get("registro_inicial"):
        aviso3 = ('<p class="aviso">Edición inicial: se han registrado %d organizaciones, webs y cuentas ya existentes '
                  '(ver listas de abajo). A partir de la próxima edición, aquí aparecerán solo las <strong>nuevas</strong>.</p>'
                  % ed["registro_inicial"])
    return """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="color-scheme" content="light">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(titulo)s</title>
<meta name="description" content="%(sub)s">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700&family=Montserrat:wght@600;700;800&display=swap" rel="stylesheet">
<link rel="alternate" type="application/rss+xml" title="%(titulo)s" href="%(raiz)sfeed.xml">
<link rel="icon" href="%(raiz)slogo-22q13.png">
<style>%(css)s</style></head>
<body>
<header class="cabecera"><div class="in">
<a class="logo" href="https://22q13.org.es" target="_blank" rel="noopener"><img src="%(raiz)slogo-22q13.png" alt="Asociación Síndrome Phelan-McDermid"></a>
<div class="kicker">Boletín diario</div>
<h1>%(titulo)s</h1>
<p class="sub">%(sub)s</p>
<div class="fecha">%(fecha)s</div>
</div></header>
<div class="wrap">
<nav class="indice">
<a href="#menciones">1 · Menciones en noticias<span>%(n1)d</span></a>
<a href="#investigacion">2 · Avances e investigación<span>%(n2)d</span></a>
<a href="#organizaciones">3 · Nuevas organizaciones<span>%(n3)d</span></a>
<a href="#archivo">Ediciones anteriores</a>
</nav>

<section class="bloque b1" id="menciones">
<h2><span class="num">1</span>Menciones en noticias</h2>
<p class="desc">Noticias que mencionan «Asociación Síndrome Phelan-McDermid» o «Phelan-McDermid», y novedades publicadas por las asociaciones de todo el mundo. Lo relacionado con investigación está en el bloque 2.</p>
<h3>Asociación Síndrome Phelan-McDermid</h3>
%(asoc)s
<h3>Novedades de las asociaciones del mundo · fuente fiable</h3>
%(asocn)s
<h3>Otras menciones en prensa</h3>
%(menc)s
</section>

<section class="bloque b2" id="investigacion">
<h2><span class="num">2</span>Avances, investigaciones, ensayos y estudios</h2>
<p class="desc">Síndrome de Phelan-McDermid · SHANK3 · 22q13. Fuentes de cualquier idioma, traducidas automáticamente al castellano. Comprueba siempre la fuente original.</p>
<h3>Comunicados de las asociaciones · fuente fiable</h3>
%(asocc)s
<h3>Noticias sobre avances</h3>
%(avan)s
<h3>Publicaciones científicas (PubMed y preprints)</h3>
%(publ)s
<h3>Ensayos clínicos (ClinicalTrials.gov)</h3>
%(ensa)s
</section>

<section class="bloque b3" id="organizaciones">
<h2><span class="num">3</span>Nuevas organizaciones y cuentas Phelan-McDermid</h2>
<p class="desc">Posibles asociaciones, fundaciones o grupos nuevos en el mundo, detectados en prensa, en las webs de las asociaciones y en redes sociales (Bluesky y Mastodon con fecha de alta; Facebook, Instagram, TikTok, X, YouTube y LinkedIn cuando aparecen enlazadas en webs de asociaciones). Son <strong>avisos para verificar</strong>.</p>
%(aviso3)s
%(orgs)s
<details><summary>Asociaciones vigiladas (%(nasoc)d)</summary>%(tasoc)s</details>
<details><summary>Cuentas y webs registradas (%(ncuentas)d)</summary>%(tcuentas)s</details>
</section>

<section class="bloque archivo" id="archivo">
<h2>Ediciones anteriores</h2>
%(archivo)s
</section>

<footer>
<p>Generado automáticamente el %(gen)s a partir de las webs de las asociaciones Phelan-McDermid, Google News, Bing News, PubMed, Europe PMC, ClinicalTrials.gov, Bluesky y Mastodon.
Traducción automática: puede contener errores; el enlace «Fuente original» lleva siempre al texto de origen.
Este boletín es informativo y no sustituye el consejo médico.</p>
<p><a href="https://22q13.org.es" target="_blank" rel="noopener">22q13.org.es</a> · <a href="%(raiz)sindex.html">Última edición</a> · <a href="%(raiz)sfeed.xml">RSS</a></p>
</footer>
</div></body></html>""" % {
        "titulo": e(cfg["titulo"]), "sub": e(cfg["subtitulo"]), "css": CSS, "raiz": ruta_raiz,
        "fecha": fecha_larga(d), "n1": n1, "n2": n2, "n3": n3,
        "asoc": lista(b["asociacion"], "Sin menciones nuevas de la Asociación en esta edición.", True),
        "asocn": lista(b["asoc_noticias"], sin), "menc": lista(b["menciones"], sin),
        "asocc": lista(b["asoc_ciencia"], sin), "avan": lista(b["avances"], sin),
        "publ": lista(b["publicaciones"], sin), "ensa": lista(b["ensayos"], sin),
        "orgs": lista(b["organizaciones"], "No se han detectado organizaciones ni cuentas nuevas desde la edición anterior."),
        "aviso3": aviso3, "nasoc": sum(not a.get("propia") for a in asociaciones), "tasoc": tabla_asociaciones(asociaciones),
        "ncuentas": len(cuentas), "tcuentas": tabla_cuentas(cuentas),
        "archivo": "<ul>%s</ul>" % archivo if archivo else '<p class="vacio">Esta es la primera edición.</p>',
        "gen": e(ed.get("generado", "")),
    }


def feed(ediciones, cfg, base):
    items = []
    for ed in ediciones[:30]:
        n = sum(len(v) for v in ed["bloques"].values())
        titulos = [i["titulo_es"] for v in ed["bloques"].values() for i in v][:8]
        items.append("<item><title>%s</title><link>%s</link><guid>%s</guid><pubDate>%s</pubDate><description>%s</description></item>" % (
            e("%s · %d novedades" % (fecha_larga(dt.date.fromisoformat(ed["fecha"])), n)),
            e(base + "archivo/%s.html" % ed["fecha"]), e(base + "archivo/%s.html" % ed["fecha"]),
            email.utils.format_datetime(dt.datetime.fromisoformat(ed["fecha"] + "T07:00:00+00:00")),
            e(" · ".join(titulos))))
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>%s</title><link>%s</link>'
            "<description>%s</description><language>es</language>%s</channel></rss>") % (
        e(cfg["titulo"]), e(base), e(cfg["subtitulo"]), "".join(items))


# ---------------------------------------------------------------- principal

def cargar(ruta, defecto):
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    return defecto


def guardar(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1, sort_keys=True)


def main():
    import fuentes_extra as fx

    cfg = cargar(os.path.join(RAIZ, "config.json"), {})
    asociaciones = cargar(os.path.join(RAIZ, "asociaciones.json"), [])
    vistos = cargar(VISTOS, {})
    ruta_cuentas = os.path.join(DATOS, "cuentas.json")
    cuentas = cargar(ruta_cuentas, {})
    primera = not vistos
    dias = cfg["dias_busqueda_primera_vez"] if primera else cfg["dias_busqueda"]
    desde = HOY - dt.timedelta(days=dias)
    log("Edición %s · buscando desde %s" % (HOY, desde))
    retraducir_pendientes()

    def nuevo(clave):
        return clave and clave not in vistos

    # --- Noticias de prensa (bloques 1 y 2)
    log("Noticias")
    noticias = buscar_noticias(cfg["bloque1_asociacion"] + cfg["bloque1_menciones"], cfg, desde)
    claves_b1 = {clave_titulo(n["titulo"]) for n in noticias}
    noticias_ciencia = [n for n in buscar_noticias(cfg["bloque2_noticias"], cfg, desde)
                        if clave_titulo(n["titulo"]) not in claves_b1]
    asociacion, menciones, avances = [], [], []
    for n in noticias + [dict(x, _ciencia=True) for x in noticias_ciencia]:
        k = "n:" + clave_titulo(n["titulo"])
        if not nuevo(k):
            continue
        completar_noticia(n)
        n["id"] = k
        if menciona_asociacion(n):
            asociacion.append(n)
        elif n.get("_ciencia") or es_investigacion(n, cfg["palabras_investigacion"]):
            avances.append(n)
        else:
            menciones.append(n)

    # --- Webs de las asociaciones (fuente fiable)
    log("Webs de asociaciones")
    art_asoc, silenciosos = fx.noticias_asociaciones(asociaciones, desde, primera, vistos)
    asoc_noticias, asoc_ciencia = [], []
    for a in art_asoc:
        if not a["resumen"]:
            a["resumen"] = descripcion_pagina(a["link"])
        (asoc_ciencia if es_investigacion(a, cfg["palabras_investigacion"]) else asoc_noticias).append(a)
    # Evita repetir en prensa lo que ya viene de la web de la asociación
    claves_asoc = {clave_titulo(a["titulo"]) for a in art_asoc}
    asociacion = [n for n in asociacion if clave_titulo(n["titulo"]) not in claves_asoc]

    # Fuera lo publicado en webs propias (dominios_excluidos)
    excluidos = tuple(cfg.get("dominios_excluidos", []))
    def ajeno(it):
        return not any(d in urllib.parse.urlparse(it["link"]).netloc for d in excluidos)
    asociacion, menciones, avances = [x for x in asociacion if ajeno(x)], [x for x in menciones if ajeno(x)], [x for x in avances if ajeno(x)]
    asoc_noticias, asoc_ciencia = [x for x in asoc_noticias if ajeno(x)], [x for x in asoc_ciencia if ajeno(x)]

    # --- Ciencia
    log("Publicaciones y ensayos")
    publicaciones = [p for p in pubmed(cfg["bloque2_pubmed"], dias) + preprints(cfg["bloque2_preprints"], desde)
                     if nuevo(p["id"])]
    ensayos_l = [x for x in ensayos(cfg["bloque2_ensayos"], desde) if nuevo(x["id"])]

    # --- Bloque 3
    log("Organizaciones y cuentas nuevas")
    orgs, registrar = fx.buscar_organizaciones_nuevas(
        cfg, asociaciones, lambda q, d: [completar_noticia(n) for n in buscar_noticias(q, cfg, d)],
        desde, vistos, primera, art_asoc)
    vistas_org = set()
    orgs = [o for o in orgs if not (o["id"] in vistas_org or vistas_org.add(o["id"]))]
    cuentas.update({k: v for k, v in registrar.items() if k not in cuentas})

    bloques = {"asociacion": asociacion, "menciones": menciones, "asoc_noticias": asoc_noticias,
               "avances": avances, "asoc_ciencia": asoc_ciencia, "publicaciones": publicaciones,
               "ensayos": ensayos_l, "organizaciones": orgs}
    log("Traduciendo %d elementos" % sum(len(v) for v in bloques.values()))
    for v in bloques.values():
        for it in v:
            traducir_item(it)
            it.pop("_ciencia", None)
        v.sort(key=lambda x: x.get("fecha", ""), reverse=True)

    # Fusiona con la edición de hoy si ya existía (varias ejecuciones el mismo día)
    ruta_ed = os.path.join(EDICIONES, HOY.isoformat() + ".json")
    previa = cargar(ruta_ed, None)
    if previa:
        for k, v in previa["bloques"].items():
            ids = {i["id"] for i in bloques.get(k, [])}
            bloques[k] = bloques.get(k, []) + [i for i in v if i.get("id") not in ids]
    ed = {"fecha": HOY.isoformat(), "generado": dt.datetime.now(MADRID).strftime("%d/%m/%Y %H:%M"), "bloques": bloques}
    if primera or (previa and previa.get("registro_inicial")):
        ed["registro_inicial"] = len(cuentas)
    guardar(ruta_ed, ed)

    for v in list(bloques.values()) + [silenciosos]:
        for it in v:
            vistos[it["id"]] = HOY.isoformat()
    for k in registrar:
        vistos.setdefault(k, HOY.isoformat())
    # Olvida claves de noticias de más de 400 días (las cuentas se conservan siempre en cuentas.json)
    limite = (HOY - dt.timedelta(days=400)).isoformat()
    vistos = {k: f for k, f in vistos.items() if f >= limite or k in cuentas}
    guardar(VISTOS, vistos)
    guardar(ruta_cuentas, cuentas)

    renderizar(cfg, asociaciones, cuentas)
    log("Listo:", {k: len(v) for k, v in bloques.items()})


def renderizar(cfg, asociaciones, cuentas):
    fechas = sorted((n[:-5] for n in os.listdir(EDICIONES) if n.endswith(".json")), reverse=True)
    ediciones = []
    os.makedirs(os.path.join(DOCS, "archivo"), exist_ok=True)
    for fch in fechas:
        x = cargar(os.path.join(EDICIONES, fch + ".json"), None)
        ediciones.append(x)
        with open(os.path.join(DOCS, "archivo", fch + ".html"), "w", encoding="utf-8") as f:
            f.write(pagina(x, cfg, fechas, asociaciones, cuentas, "../"))
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina(ediciones[0], cfg, fechas, asociaciones, cuentas))
    base = os.environ.get("SITE_URL", "./")
    with open(os.path.join(DOCS, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(feed(ediciones, cfg, base))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if "--solo-html" in sys.argv:  # regenera las páginas sin buscar novedades
        renderizar(cargar(os.path.join(RAIZ, "config.json"), {}), cargar(os.path.join(RAIZ, "asociaciones.json"), []),
                   cargar(os.path.join(DATOS, "cuentas.json"), {}))
    else:
        main()
