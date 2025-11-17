# Microservice SFTP Python/FastAPI

Microservice Python utilisant FastAPI pour gérer les connexions SFTP avec authentification par clé SSH.

## 🚀 Déploiement sur Render.com (Gratuit)

### Étape 1 : Créer un dépôt GitHub

1. Créez un nouveau dépôt sur GitHub nommé `sftp-microservice`
2. Ajoutez les fichiers suivants :
   - `main.py`
   - `requirements.txt`
   - `.gitignore`
   - `README.md`

### Étape 2 : Déployer sur Render

1. Allez sur [render.com](https://render.com)
2. Connectez-vous avec votre compte GitHub
3. Cliquez sur **"New +"** → **"Web Service"**
4. Sélectionnez votre dépôt `sftp-microservice`
5. Configurez le service :
   - **Name** : `sftp-microservice`
   - **Environment** : `Python 3`
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type** : `Free`

6. Cliquez sur **"Create Web Service"**

### Étape 3 : Obtenir l'URL du service

Après le déploiement (2-3 minutes) :
1. L'URL du service apparaîtra en haut : `https://sftp-microservice-xxxx.onrender.com`
2. Testez avec : `https://votre-url.onrender.com/health`
3. Vous devriez voir : `{"status":"healthy",...}`

⚠️ **Important** : Le plan gratuit de Render met le service en veille après 15 minutes d'inactivité. Le premier appel prendra ~30 secondes pour redémarrer le service.

## 📖 API Endpoints

### GET /health

Vérifie que le service fonctionne.

**Réponse** :
```json
{
  "status": "healthy",
  "service": "sftp-microservice",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

### POST /download-files

Télécharge des fichiers depuis un serveur SFTP.

**Corps de la requête** :
```json
{
  "connection": {
    "hostname": "sftp.example.com",
    "port": 22,
    "username": "votre_username",
    "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----"
  },
  "remote_path": "/chemin/vers/dossier",
  "expected_files": [
    {
      "filename": "fichier1.xlsx",
      "description": "Fichier de positions"
    },
    {
      "filename": "fichier2.xlsx",
      "description": "Fichier de transactions"
    }
  ]
}
```

**Réponse réussie** :
```json
{
  "success": true,
  "downloaded_files": [
    {
      "filename": "fichier1.xlsx",
      "content_base64": "UEsDBBQABgAI...",
      "size": 45678,
      "download_time": "2024-01-15T10:30:00.000Z"
    }
  ],
  "missing_files": [],
  "stats": {
    "total_expected": 2,
    "total_downloaded": 1,
    "total_missing": 1,
    "total_size_bytes": 45678,
    "duration_seconds": 2.34
  }
}
```

## 🧪 Tests en local

### 1. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2. Lancer le serveur

```bash
uvicorn main:app --reload --port 8000
```

### 3. Tester

Ouvrez votre navigateur : `http://localhost:8000/health`

Documentation interactive : `http://localhost:8000/docs`

## 💰 Coûts

### Plan Gratuit Render
- ✅ 750 heures/mois gratuites
- ✅ Suffisant pour un projet personnel
- ⚠️ Service en veille après 15 min d'inactivité
- ⚠️ Premier appel : ~30 secondes de redémarrage

### Plan Payant Render (7$/mois)
- ✅ Service toujours actif (pas de mise en veille)
- ✅ Réponses instantanées
- ✅ SSL automatique
- ✅ Logs illimités

## 🔒 Sécurité

- ✅ Clés privées jamais enregistrées
- ✅ Transmission HTTPS uniquement
- ✅ Validation Pydantic sur toutes les entrées
- ✅ Logs détaillés pour débogage
- ⚠️ Utilisez des variables d'environnement pour les secrets en production

## 📊 Monitoring

Sur Render.com :
1. Allez dans votre dashboard
2. Cliquez sur votre service
3. Onglet **"Logs"** : voir les logs en temps réel
4. Onglet **"Metrics"** : CPU, RAM, requêtes

## 🛠️ Dépannage

### Le service ne démarre pas
- Vérifiez les logs dans Render Dashboard
- Assurez-vous que `requirements.txt` contient toutes les dépendances
- Vérifiez que la commande de démarrage est correcte

### Erreur de connexion SFTP
- Vérifiez le hostname et le port
- Testez votre clé privée localement
- Vérifiez les permissions du répertoire distant

### Timeout
- Le service gratuit peut être lent au premier appel (mise en veille)
- Augmentez les timeouts côté client (60 secondes recommandé)
- Considérez le plan payant pour des performances constantes

## 🌟 Avantages FastAPI

- ⚡ **Async natif** : Parfait pour les opérations I/O comme SFTP
- 📝 **Validation automatique** : Pydantic valide toutes les entrées
- 📚 **Documentation auto** : Swagger UI à `/docs`
- 🚀 **Performances** : Plus rapide que Flask
- 🔧 **Moderne** : Type hints Python natifs

## 📞 Support

Pour toute question :
1. Consultez les logs Render
2. Testez l'endpoint `/health`
3. Vérifiez la documentation interactive `/docs`
