# Hébergement du site NBA sur Azure

Le site React et FastAPI partagent une origine HTTPS. React ouvre le WebSocket `/api/ws/run` sur cette origine. FastAPI crée l’agent LangChain pour une question et exécute le graphe LangGraph pour un brief. Le client MCP Python découvre les outils des trois serveurs fournis avec le code et leur parle sur les entrées et sorties standard de processus enfants. Le modèle reçoit les descriptions des outils et propose des appels que le code exécute. Cette installation conserve les modèles OpenRouter et accepte aussi les clés fournies par les visiteurs.

## Ressources et configuration

Le groupe `rg-nba-moa` contient le site Linux `nba-moa-sven`, le plan App Service F1 et le serveur PostgreSQL Flexible `pg-nba-moa-sven`, en Sweden Central. Le serveur utilise PostgreSQL 16, une instance B1ms, 32 Gio, une rétention de sauvegarde de sept jours et l’extension `vector`. Le pare-feu autorise les adresses sortantes du site. Vérifier ces adresses après un changement de plan. Le compte applicatif `nba_app` a les droits de créer les tables dans sa base pour les migrations Alembic.

App Service utilise Python 3.11. Les paramètres `SERVE_FRONTEND=true`, `WEBSITE_RUN_FROM_PACKAGE=1` et `SCM_DO_BUILD_DURING_DEPLOYMENT=false` activent le déploiement du paquet précompilé. Les paramètres privés de l’application contiennent `DATABASE_URL` et `BALLDONTLIE_API_KEY`. La connexion PostgreSQL utilise `ssl=verify-full` et `PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt`. La démo utilise le paramètre privé `DEMO_OPENROUTER_KEY`. Le navigateur reçoit uniquement un indicateur de disponibilité. PostgreSQL limite les requêtes financées à `DEMO_DAILY_RUNS` (20 par jour UTC, partagés entre visiteurs). Les installations sans clé serveur demandent une clé visiteur.

## Publier une nouvelle version

Depuis la racine du dépôt, avec Docker, Node, uv et Azure CLI déjà connectée à l’abonnement du site, utiliser les commandes suivantes. Le script compile React et prépare les dépendances Python verrouillées pour Linux x86-64. Les réglages de la machine locale et les fichiers de données sont exclus du paquet.

```bash
npm ci --prefix frontend
./deploy/azure/package.sh /tmp/nba-moa-site.zip
az webapp deploy -g rg-nba-moa -n nba-moa-sven --type zip --src-path /tmp/nba-moa-site.zip
curl --fail https://nba-moa-sven.azurewebsites.net/api/health
```

La commande de démarrage configurée sur le site est la suivante.

```bash
cd /home/site/wwwroot && export PYTHONPATH=/home/site/wwwroot/packages:/home/site/wwwroot/backend && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Dans le portail Azure, ouvrir **rg-nba-moa → nba-moa-sven → Flux de journaux** pour examiner un démarrage. Sur `/api/health`, vérifier `status=ok`, `database_ok=true`, `mcp_initialised=true` et la liste des onze outils. Pour vérifier la génération, ouvrir **NBA Copilot** sur le site et poser une question depuis une nouvelle session sans clé visiteur. Ouvrir **Daily Brief** pour tester le graphe multi-agent et **Evaluation** pour retrouver les traces.

L’offre F1 convient à une démonstration individuelle. Elle impose un quota CPU quotidien, cinq connexions WebSocket simultanées sous Linux et des démarrages à froid. PostgreSQL consomme son allocation même lorsque le site est inactif. Les limites de l’essai et les avantages gratuits de l’abonnement sont consultables dans **Cost Management + Billing**. [Limites d’App Service](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#app-service-limits) · [Offre Azure gratuite](https://azure.microsoft.com/pricing/purchase-options/azure-account)

## Connexion Google et historique

La démo accepte les visiteurs sans compte. Pour activer l’historique, configurer **Google Auth Platform** dans le projet dédié `nba-moa-sven-demo`. Renseigner le nom **NBA Agents Demo** et le contact de support du propriétaire, puis créer un client **Application Web**. Le périmètre demandé par la démo se limite à `openid`. Choisir une audience externe et publier le client quand la connexion doit être accessible à tous. Le mode test est adapté à une vérification préalable avec les comptes de test du propriétaire.

- URI de redirection de production : `https://nba-moa-sven.azurewebsites.net/api/account/google/callback`.
- Origine publique : `https://nba-moa-sven.azurewebsites.net`.
- URI de redirection locale si un client séparé sert au développement : `http://localhost:5173/api/account/google/callback`. Utiliser l’origine `http://localhost:5173` pour ce client. Le flux est côté serveur et ne requiert aucune origine JavaScript autorisée.

Saisir `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `SESSION_SECRET` (au moins 32 caractères aléatoires) et `PUBLIC_ORIGIN` dans les paramètres privés d’App Service. Le secret de session peut être généré directement dans le terminal avec `openssl rand -hex 32` pour être saisi dans Azure. Garder ces valeurs dans le gestionnaire de secrets. L’application utilise un cookie temporaire pour l’état OAuth et un cookie de session signé, HTTPOnly et Secure en production, valable sept jours. Avant l’activation, configurer le démarrage d’Uvicorn avec `--no-access-log` et désactiver la journalisation HTTP de la plateforme si elle enregistre la chaîne de requête du callback OAuth. [Création d’un client Google](https://developers.google.com/workspace/guides/create-credentials)

Vérifier `/api/account/session`, se connecter depuis deux profils, lancer une question dans chaque profil et confirmer que chacun n’affiche que son exécution. Vérifier que **Se déconnecter** rétablit le mode invité et que **Effacer mon historique** supprime les exécutions et les briefs du compte actif. Les exécutions privées restent en base jusqu’à effacement. Les sauvegardes Azure peuvent contenir une copie pendant leur durée de rétention. Les traces antérieures à la migration n’ont aucun propriétaire et sont inaccessibles aux visiteurs et aux comptes. La migration les conserve dans PostgreSQL pour permettre au propriétaire de décider de leur suppression.

## Coût et disponibilité

Le plafond PostgreSQL porte sur les requêtes sponsorisées, en incluant les générations interrompues après réservation. Il protège le nombre de départs et les appels d’agents, les jetons et les tarifs déterminent la dépense. Le parcours d’exemples sert des fichiers statiques, sans appel de modèle. Le tableau de bord calcule un coût théorique en USD à partir des jetons et des tarifs catalogue. La facturation Azure, les embeddings, les remises et l’usage facturé par OpenRouter se vérifient dans les consoles respectives.

Contrôler dans OpenRouter le plafond en USD de la clé de cette démo et la remise à zéro choisie. Pour Azure, contrôler la période écoulée et le coût de PostgreSQL dans **Cost Management**, y compris après la fin des crédits gratuits. S’appuyer sur les données de facturation pour toute projection. [Plafond OpenRouter par clé](https://openrouter.ai/docs/api/api-reference/api-keys/update-keys) · [API Azure Cost Management](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage)
