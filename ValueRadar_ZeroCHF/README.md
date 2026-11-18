# ValueRadar ZERO CHF — radar de cotes public

**Déploiement** : GitHub Actions sur le dépôt public `Kopitarnkmk/nhl-point-radar`. Ce dossier n'altère pas l'application NHL. Aucune dépense et aucun abonnement requis.

## Mode actif immédiat, sans clé API

- Source : tableau public OddsLink `GET /v1/public/board/{sport}` : https://oddslink.app/docs/api-reference/operations/publicboard/
- Football, NBA, NHL ; matchs à venir seulement, h2h/spreads/totals.
- Compare une cote Pinnacle à celle d'un autre bookmaker pour le **même marché, même sélection et même ligne**, après retrait multiplicatif de la marge de Pinnacle.
- Ignore les exchanges et marchés prédictifs : uniquement les `sportsbook` avec `kind=sportsbook` ; une seule alerte par match/marché/sélection.
- Exige écart théorique > 7 %, cotes confirmées dans les **15 dernières minutes**, événement encore à venir.
- GitHub Actions analyse toutes les 30 minutes (planificateur best effort, retards possibles) et écrit un commentaire avec une mention du propriétaire dans l'issue dédiée si un signal nouveau apparaît.
- Le lien est public, sans vérification JouezSport ; **les alertes ne sont jamais des ordres de mise**.
- Maximum 3 alertes par exécution, anti-doublons par identifiant stable enregistré dans les commentaires de l'issue. Les 100 derniers commentaires seulement sont vérifiés ; cela peut manquer des anciens signaux si la liste dépasse 100.

Sources : https://oddslink.app/docs/api-reference/operations/publicboard/ ; https://docs.github.com/en/actions/concepts/billing-and-usage

## Vérification

`PYTHONPATH=ValueRadar_ZeroCHF python -m unittest discover -s ValueRadar_ZeroCHF/tests -v`

`python ValueRadar_ZeroCHF/public_board.py --test` (effectue trois requêtes publiques et ne poste rien).

## Étape supplémentaire facultative : Telegram / API étendue

Le fichier `free_radar.py` préparé est fourni séparément pour un futur branchement de PinnFeed, OddsLink et Telegram avec **clés gratuites**. Il n'est pas lancé par le workflow public et ne s'exécute pas sans secrets. Pour obtenir des notifications Telegram privées, il faut créer un bot avec @BotFather et fournir son token + identifiant de chat via des secrets GitHub, puis adapter la cible de notification. Ne jamais publier ces secrets dans le dépôt.
