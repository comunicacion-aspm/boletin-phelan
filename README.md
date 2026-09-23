# Boletín diario Phelan-McDermid

Página web pública y gratuita (GitHub Pages) que se actualiza sola cada mañana con tres bloques:

1. **Menciones en noticias**: «Asociación Síndrome Phelan-McDermid» y «Phelan-McDermid» en prensa, más las novedades publicadas por las asociaciones de todo el mundo.
2. **Avances, investigaciones, ensayos y estudios** sobre síndrome de Phelan-McDermid, SHANK3 y 22q13: comunicados de asociaciones, noticias, PubMed, preprints (Europe PMC) y ensayos clínicos (ClinicalTrials.gov).
3. **Nuevas organizaciones y cuentas**: posibles asociaciones o fundaciones nuevas detectadas en prensa, en las webs de las asociaciones y en redes sociales.

Todo se traduce automáticamente al castellano y cada elemento lleva el enlace a su fuente original.

## Puesta en marcha (una sola vez)

1. Crea una cuenta gratuita en https://github.com si no tienes.
2. Crea un repositorio **público** nuevo, por ejemplo `boletin-phelan`, vacío (sin README).
3. Sube esta carpeta desde el Terminal (te pedirá tu usuario y un *token* de GitHub como contraseña):
   ```bash
   cd ~/Documents/newsletter-phelan-mcdermid
   git init -b main
   git add .
   git commit -m "Boletín Phelan-McDermid"
   git remote add origin https://github.com/TU_USUARIO/boletin-phelan.git
   git push -u origin main
   ```
4. En GitHub, en el repositorio: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
5. En **Actions → Boletín diario → Run workflow** lánzalo la primera vez.
6. Tu boletín queda en: `https://TU_USUARIO.github.io/boletin-phelan/`

A partir de ahí se regenera todos los días a las 05:30 UTC (07:30 hora peninsular en verano).

## Cómo ajustarlo

- `config.json`: palabras clave, idiomas, días de búsqueda y consultas del bloque 3.
- `asociaciones.json`: asociaciones vigiladas (web, página de noticias, feed y redes). Para añadir una, copia una entrada y cambia los datos. `tipo_feed` puede ser `rss`, `wp-json`, `html` (se leen los enlaces de la página de noticias), `cambios` (avisa cuando la página cambia) o `none` (solo se vigilan sus redes). `solo_si_menciona: true` filtra organizaciones generalistas para que solo entren noticias sobre Phelan-McDermid/SHANK3/22q13.
- Para probar en local: `python3 scripts/build.py` y abre `docs/index.html`.

## Límites a tener en cuenta

- **Redes sociales**: Facebook, Instagram, TikTok, X, YouTube y LinkedIn no permiten buscar cuentas nuevas gratis ni sin iniciar sesión. El bloque 3 detecta cuentas nuevas en **Bluesky y Mastodon** (con fecha de alta) y en el resto **cuando aparecen enlazadas** en webs de asociaciones o en directorios, además de noticias sobre creación de asociaciones.
- La traducción es automática (servicio web gratuito de Google); ante cualquier duda, abre la fuente original.
- Si Google News limita las peticiones, algunas noticias llevan su enlace de redirección de Google News en lugar del enlace directo al medio; al abrirlo te lleva igualmente a la noticia original.
- Algunas webs (Portugal, C22C, Mount Sinai, phelan-mcdermid.eu) bloquean las lecturas automáticas; sus redes siguen en la lista de vigilancia.
