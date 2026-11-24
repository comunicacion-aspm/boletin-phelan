#!/bin/zsh
# Lanza el Boletín diario a las 08:30 desde el Mac (LaunchAgent es.22q13.boletin-diario).
# El cron de GitHub llega con horas de retraso; un push en disparador/ lo arranca al momento.
cd "$HOME/Documents/newsletter-phelan-mcdermid" || exit 1
dia=$(date +%u); [ "$dia" -gt 5 ] && exit 0          # solo de lunes a viernes
hoy=$(TZ=Europe/Madrid date +%F)
git pull --rebase --autostash -q || exit 1
[ -f "data/ediciones/$hoy.json" ] && exit 0          # ya está hecho
date "+%F %T" > disparador/ultimo.txt
git add disparador/ultimo.txt
git commit -q -m "Disparar boletín $hoy" -- disparador/ultimo.txt
git push -q || { sleep 30; git pull --rebase --autostash -q && git push -q; }
