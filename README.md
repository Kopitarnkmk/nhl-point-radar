# NHL Point Radar — Coupon Builder

Application web mobile en français : statistiques des joueurs NHL 1+ point, forme 5/10 matchs, calendrier et générateur de coupons.

## Installation Render
Python 3.12, `python app.py`, service web sur `$PORT`. Service gratuit proposé dans `render.yaml`.

## API
- `/api/health`
- `/api/players` (cache de 15 min)
- `/api/games?date=2026-11-04` (cache de 5 min)

Les chiffres proviennent des API NHL. Le service n'accède pas aux bookmakers ; toute cote doit être saisie manuellement. Indices descriptifs, pas de prédictions garanties. Plusieurs joueurs d'un même match nécessitent une cote unique de Pari personnalisé +, fournie par le bookmaker.

Dans Safari sur iPhone : Partager > Sur l'écran d'accueil > Ajouter.
