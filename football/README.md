# Football Point Radar

Web app mobile en français : 19 compétitions d'Europe, tri championnat/coupe/Europe, calendrier des matchs, historiques de la saison courante **uniquement dans la compétition étudiée**, générateur de coupons et calculateur de gains avec cotes saisies par l'utilisateur.

## Render

Déployer un service Python distinct du service NHL, basé sur ce même dépôt GitHub, avec la commande de démarrage `python football/app.py`. Aucune dépendance pip. Variable `PORT` fournie par Render. Plan Free possible.

## Données

API JSON non officielle d'ESPN (sans clé). Le calendrier est mis en cache 5 min et l'historique par compétition 60 min. Certaines compétitions peuvent être incomplètes, ne pas répondre ou proposer des résultats en prolongations sans séparation des 90 min. Les données ESPN ne remplacent pas les cotes, les compositions ou les blessures vérifiées.

## Endpoints
- `/api/health`
- `/api/competitions`
- `/api/fixtures?date=2026-11-04`
- `/api/history?competition=eng.1`

Les indices de convergence descriptifs ne sont **pas** des probabilités de résultat ni des garanties. Le code NHL reste dans la racine du dépôt et est servi par un service Render indépendant.
