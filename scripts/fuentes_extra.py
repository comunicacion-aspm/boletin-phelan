"""Fuentes adicionales: webs de las asociaciones Phelan-McDermid y vigilancia de
organizaciones y cuentas nuevas (bloque 3)."""
import datetime as dt
import hashlib
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

from build import (HOY, clave_titulo, fecha_rss, http, http_json, limpiar, log, recortar)

# --------------------------------------------------------------- webs de asociaciones

RUTAS_NO_ARTICULO = re.compile(
    r"/(category|categoria|tag|etiqueta|page|pagina|author|autor|feed|wp-|cart|carrito|shop|tienda|"
    r"donate|donar|dona|contact|contacto|privacy|privacidad|cookies|legal|login|account|cuenta|search)\b", re.I)


def _texto(el, *nombres):
    for n in nombres:
        for hijo in el:
            if hijo.tag.split("}")[-1] == n:
                if n == "link" and hijo.get("href"):
                    return hijo.get("href")
                return "".join(hijo.itertext())
    return ""


def leer_feed(url):
    xml = http(url)
    if not xml:
        return []
    try:
        raiz = ET.fromstring(xml.strip().encode("utf-8"))
    except ET.ParseError:
        return []
    items = []
    for el in raiz.iter():
        if el.tag.split("}")[-1] not in ("item", "entry"):
            continue
        fecha_txt = _texto(el, "pubDate", "published", "updated", "date")
        f = fecha_rss(fecha_txt)
        if not f and fecha_txt[:10]:
            try:
                f = dt.date.fromisoformat(fecha_txt[:10])
            except ValueError:
                f = None
        items.append({"titulo": limpiar(_texto(el, "title")), "link": _texto(el, "link").strip(),
                      "fecha": f.isoformat() if f else "",
                      "resumen": recortar(_texto(el, "description", "summary", "content"), 450)})
    return items


def leer_wp_json(url):
    datos = http_json(url)
    items = []
    for p in datos or []:
        if not isinstance(p, dict):
            continue
        items.append({"titulo": limpiar((p.get("title") or {}).get("rendered")), "link": p.get("link", ""),
                      "fecha": (p.get("date") or "")[:10],
                      "resumen": recortar((p.get("excerpt") or {}).get("rendered", ""), 450)})
    return items


def leer_html(url):
    """Extrae enlaces a artículos de una página de noticias sin feed."""
    pagina = http(url)
    if not pagina:
        return []
    base = urllib.parse.urlparse(url)
    items, vistos = [], set()
    for href, texto in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', pagina, re.S | re.I):
        enlace = urllib.parse.urljoin(url, href.strip())
        p = urllib.parse.urlparse(enlace)
        titulo = limpiar(texto)
        if p.netloc.replace("www.", "") != base.netloc.replace("www.", ""):
            continue
        if len(titulo) < 25 or len(titulo) > 220 or enlace in vistos:
            continue
        if RUTAS_NO_ARTICULO.search(p.path) or p.path.rstrip("/") in ("", base.path.rstrip("/")):
            continue
        if p.path.count("/") < 2 and "-" not in p.path:
            continue
        vistos.add(enlace)
        items.append({"titulo": titulo, "link": enlace, "fecha": "", "resumen": ""})
    return items[:25]


def noticias_asociaciones(asociaciones, desde, primera_vez, vistos):
    """Devuelve (nuevos, silenciosos). Los 'silenciosos' se marcan como vistos sin publicarse
    (páginas HTML sin fecha en la primera ejecución, para no inundar el boletín)."""
    nuevos, silenciosos = [], []
    for a in asociaciones:
        tipo, fuente = a.get("tipo_feed"), a.get("feed") or a.get("noticias")
        if not fuente or tipo == "none":
            continue
        log("  asociación:", a["nombre"])
        if tipo == "cambios":
            # Página sin artículos: avisa cuando cambia su texto
            texto = limpiar(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", http(fuente) or "", flags=re.S | re.I))
            if texto:
                huella = hashlib.sha1(texto.encode()).hexdigest()[:16]
                it = {"titulo": "%s ha actualizado su página de novedades" % a["nombre"], "link": fuente,
                      "fecha": HOY.isoformat(), "resumen": recortar(texto[:600], 300),
                      "id": "cambio:%s:%s" % (fuente, huella), "medio": "%s · %s" % (a["nombre"], a.get("pais", "")),
                      "fuente_fiable": True, "tipo": "Fuente fiable · página actualizada"}
                previas = [k for k in vistos if k.startswith("cambio:%s:" % fuente)]
                if it["id"] not in vistos:
                    (nuevos if previas and not primera_vez else silenciosos).append(it)
            continue
        if tipo == "rss":
            items = leer_feed(fuente)
        elif tipo == "wp-json":
            items = leer_wp_json(fuente)
        else:
            items = leer_html(fuente)
        for it in items[:20]:
            if not it["titulo"] or not it["link"]:
                continue
            if a.get("solo_si_menciona") and not RE_SINDROME.search(it["titulo"] + " " + it["resumen"]):
                continue
            if re.search(r"\b(store|shop|tienda|boutique|negozio|loja|donate|dona ahora)\b", it["titulo"], re.I):
                continue
            it["id"] = "asoc:" + it["link"].split("?")[0].rstrip("/")
            if it["id"] in vistos:
                continue
            it.update({"medio": "%s · %s" % (a["nombre"], a.get("pais", "")), "fuente_fiable": True,
                       "tipo": "Fuente fiable · asociación"})
            if it["fecha"]:
                if it["fecha"] < desde.isoformat():
                    continue
                nuevos.append(it)
            elif primera_vez:
                silenciosos.append(it)
            else:
                it["fecha"] = HOY.isoformat()
                nuevos.append(it)
    return nuevos, silenciosos


# --------------------------------------------------------------- bloque 3: organizaciones nuevas

RE_SINDROME = re.compile(r"phelan[\s_.-]*mc[\s_.-]*dermid|22q13|shank[\s_-]?3|\bpms\s*(uk|foundation|syndrome)|pmsf", re.I)
RE_ORGANIZACION = re.compile(
    r"asociaci|associa|foundation|fundaci|fondation|fondazione|stichting|vereniging|verein|\be\.\s?v\b|charity|"
    r"\borg\b|\.org|federa|communit|comunidad|comunit|famil|group|grupo|gruppo|network|alliance|alianza|"
    r"society|sociedad|onlus|\baps\b|\bong\b|\bngo\b|non-?profit|sin [aá]nimo|association|parents|padres", re.I)
RE_FUNDACION = re.compile(
    r"nueva asociaci|nace (la|una) (asociaci|fundaci)|se (crea|constituye|funda)|constitu(ida|ye)|fundad[ao]|"
    r"new (association|foundation|charity|organi[sz]ation|group|chapter)|launch(es|ed)?|founded|established|"
    r"nouvelle association|association (créée|fondée)|nuova associazione|nasce|fondata|"
    r"nova associa|fundada|criada|neuer? verein|gegründet|opgericht|nieuwe stichting", re.I)


def es_organizacion(texto):
    return bool(RE_SINDROME.search(texto) and RE_ORGANIZACION.search(texto))


def cuentas_bluesky(consultas):
    cuentas = {}
    for q in consultas:
        r = http_json("https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors?" +
                      urllib.parse.urlencode({"q": q, "limit": 50}))
        for a in (r or {}).get("actors", []):
            texto = " ".join([a.get("handle", ""), a.get("displayName", ""), a.get("description", "")])
            if es_organizacion(texto):
                cuentas["bluesky:" + a["handle"]] = {
                    "red": "Bluesky", "nombre": a.get("displayName") or a["handle"], "usuario": "@" + a["handle"],
                    "link": "https://bsky.app/profile/" + a["handle"],
                    "descripcion": recortar(a.get("description", ""), 300),
                    "creada": (a.get("createdAt") or "")[:10]}
    return cuentas


def cuentas_mastodon(consultas):
    cuentas = {}
    for q in consultas:
        r = http_json("https://mastodon.social/api/v2/search?" +
                      urllib.parse.urlencode({"q": q, "type": "accounts", "limit": 40}))
        for a in (r or {}).get("accounts", []):
            nota = limpiar(a.get("note", ""))
            texto = " ".join([a.get("acct", ""), a.get("display_name", ""), nota])
            if es_organizacion(texto):
                cuentas["mastodon:" + a["acct"]] = {
                    "red": "Mastodon", "nombre": a.get("display_name") or a["acct"], "usuario": "@" + a["acct"],
                    "link": a.get("url", ""), "descripcion": recortar(nota, 300),
                    "creada": (a.get("created_at") or "")[:10]}
    return cuentas


RE_RED = re.compile(
    r"https?://(?:www\.|m\.|es-es\.)?(facebook\.com|instagram\.com|tiktok\.com|x\.com|twitter\.com|"
    r"youtube\.com|linkedin\.com|threads\.net|bsky\.app)/(?!sharer|share|intent|dialog|plugins|tr\?|watch|embed|"
    r"hashtag|explore|p/|reel|home|login|privacy|policy|legal)([A-Za-z0-9_.@/%-]{2,120})", re.I)
NOMBRE_RED = {"facebook.com": "Facebook", "instagram.com": "Instagram", "tiktok.com": "TikTok", "x.com": "X",
              "twitter.com": "X", "youtube.com": "YouTube", "linkedin.com": "LinkedIn", "threads.net": "Threads",
              "bsky.app": "Bluesky"}


def perfiles_en_pagina(url):
    """Perfiles de redes sociales enlazados desde una página (web de asociación o noticia)."""
    pagina = http(url, timeout=15, reintentos=0) or ""
    perfiles = {}
    for dominio, ruta in RE_RED.findall(pagina):
        partes = urllib.parse.unquote(ruta).strip("/").split("?")[0].split("/")
        # linkedin.com/company/x, youtube.com/channel/x… conservan dos segmentos; el resto, uno
        n = 2 if partes[0].lower() in ("company", "in", "school", "channel", "c", "user", "groups", "pages", "people") else 1
        ruta = "/".join(partes[:n])
        if not ruta or len(partes) < n or re.match(r"^(\d{4}|profile\.php|status|i|home|search)$", partes[0], re.I):
            continue
        red = NOMBRE_RED[dominio.lower()]
        clave = "%s:%s" % (red.lower(), ruta.lower())
        perfiles[clave] = {"red": red, "usuario": ruta, "link": "https://%s/%s" % (dominio.lower(), ruta),
                           "encontrado_en": url}
    return perfiles


def buscar_organizaciones_nuevas(cfg, asociaciones, noticias_fn, desde, vistos, primera_vez, articulos_asoc):
    """Bloque 3. Devuelve (candidatas, claves_para_registrar)."""
    candidatas, registrar = [], {}

    # 1) Noticias sobre creación de asociaciones/fundaciones (cualquier idioma)
    for n in noticias_fn(cfg["bloque3_noticias"], desde):
        texto = n["titulo"] + " " + n.get("resumen", "")
        if RE_SINDROME.search(texto) and RE_FUNDACION.search(texto):
            clave = "org-noticia:" + clave_titulo(n["titulo"])
            if clave not in vistos:
                n.update({"id": clave, "tipo": "Posible nueva organización · prensa"})
                candidatas.append(n)

    # 2) Comunicados de las propias asociaciones que anuncian nuevas organizaciones
    for a in articulos_asoc:
        if RE_FUNDACION.search(a["titulo"] + " " + a.get("resumen", "")):
            candidatas.append(dict(a, id="org-" + a["id"], tipo="Posible nueva organización · fuente fiable"))

    # 3) Cuentas en redes con API pública (Bluesky, Mastodon), con fecha de creación
    cuentas = {}
    cuentas.update(cuentas_bluesky(cfg["bloque3_redes"]))
    cuentas.update(cuentas_mastodon(cfg["bloque3_redes"]))
    # 4) Perfiles enlazados desde las webs de las asociaciones y páginas de directorio
    paginas = [a["web"] for a in asociaciones if a.get("web")] + cfg.get("bloque3_directorios", [])
    for url in paginas:
        for clave, p in perfiles_en_pagina(url).items():
            cuentas.setdefault(clave, dict(p, nombre=p["usuario"], descripcion="", creada=""))
    conocidas = {c.lower() for a in asociaciones for c in (a.get("redes") or {}).values() if c}

    for clave, c in cuentas.items():
        registrar[clave] = c
        if clave in vistos or primera_vez:
            continue
        if any(c["link"].lower().rstrip("/") == k.rstrip("/") for k in conocidas):
            continue
        reciente = c.get("creada") and c["creada"] >= (HOY - dt.timedelta(days=60)).isoformat()
        candidatas.append({
            "id": clave, "titulo": "%s: %s (%s)" % (c["red"], c["nombre"], c["usuario"]), "link": c["link"],
            "medio": c["red"], "fecha": c.get("creada") or HOY.isoformat(),
            "resumen": c.get("descripcion") or ("Enlazada desde " + c["encontrado_en"] if c.get("encontrado_en") else ""),
            "tipo": ("Cuenta creada el %s" % c["creada"]) if reciente else "Cuenta detectada por primera vez",
            "extra": ""})

    # 5) Webs de directorio: organizaciones enlazadas que no conocíamos
    dominios_conocidos = {urllib.parse.urlparse(a["web"]).netloc.replace("www.", "") for a in asociaciones if a.get("web")}
    for url in cfg.get("bloque3_directorios", []):
        pagina = http(url) or ""
        for href, texto in re.findall(r'<a[^>]+href=["\'](https?://[^"\']+)["\'][^>]*>(.*?)</a>', pagina, re.S | re.I):
            dom = urllib.parse.urlparse(href).netloc.replace("www.", "")
            titulo = limpiar(texto)
            if dom in dominios_conocidos or dom in urllib.parse.urlparse(url).netloc or any(r in dom for r in NOMBRE_RED):
                continue
            if not es_organizacion(titulo + " " + href):
                continue
            clave = "org-web:" + dom
            registrar[clave] = {"link": href}
            if clave not in vistos and not primera_vez:
                candidatas.append({"id": clave, "titulo": titulo or dom, "link": href, "medio": dom,
                                   "fecha": HOY.isoformat(), "tipo": "Nueva web en directorio",
                                   "resumen": "Aparece enlazada en " + url})
    return candidatas, registrar
