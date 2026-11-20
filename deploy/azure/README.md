# Hébergement du site NBA sur Azure

Le site React et FastAPI partagent une origine HTTPS. React ouvre le WebSocket `/api/ws/run` sur cette origine. FastAPI crée l’agent LangChain pour une question et exécute le graphe LangGraph pour un brief. Le client MCP Python découvre les outils des trois serveurs fournis avec le code et leur parle sur les entrées et sorties standard de processus enfants. Le modèle reçoit les descriptions des outils et propose des appels que le code exécute. Cette installation conserve les modèles OpenRouter et les clés par utilisateur du projet.

## Ressources et configuration

Le groupe `rg-nba-moa` contient le site Linux `nba-moa-sven`, le plan App Service F1 et le serveur PostgreSQL Flexible `pg-nba-moa-sven`, en Sweden Central. Le serveur utilise PostgreSQL 16, une instance B1ms, 32 Gio, une rétention de sauvegarde de sept jours et l’extension `vector`. Le pare-feu autorise les adresses sortantes du site. Vérifier ces adresses après un changement de plan. Le compte applicatif `nba_app` a les droits de créer les tables dans sa base pour les migrations Alembic.

App Service utilise Python 3.11. Les paramètres `SERVE_FRONTEND=true`, `WEBSITE_RUN_FROM_PACKAGE=1` et `SCM_DO_BUILD_DURING_DEPLOYMENT=false` activent le déploiement du paquet précompilé. Les paramètres privés de l’application contiennent `DATABASE_URL` et `BALLDONTLIE_API_KEY`. La connexion PostgreSQL utilise `ssl=verify-full` et `PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt`. Une clé OpenRouter est saisie dans l’interface, conservée pour la session du navigateur et transmise au backend par HTTPS ou WSS pour les appels au fournisseur.

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

Dans le portail Azure, ouvrir **rg-nba-moa → nba-moa-sven → Flux de journaux** pour examiner un démarrage. Sur `/api/health`, vérifier `status=ok`, `database_ok=true`, `mcp_initialised=true` et la liste des onze outils. Pour vérifier la génération, ouvrir **NBA Copilot** sur le site et poser une question après avoir renseigné une clé OpenRouter. Ouvrir **Daily Brief** pour tester le graphe multi-agent et **Evaluation** pour retrouver les traces.

L’offre F1 convient à une démonstration individuelle. Elle impose un quota CPU quotidien, cinq connexions WebSocket simultanées sous Linux et des démarrages à froid. PostgreSQL consomme son allocation même lorsque le site est inactif. Les limites de l’essai et les avantages gratuits de l’abonnement sont consultables dans **Cost Management + Billing**. [Limites d’App Service](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#app-service-limits) · [Offre Azure gratuite](https://azure.microsoft.com/pricing/purchase-options/azure-account)
