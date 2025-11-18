from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Optional
import paramiko
import io
import base64
from datetime import datetime
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom log handler to capture logs
class LogCapture:
    def __init__(self):
        self.logs = []
    
    def add(self, message: str):
        self.logs.append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {message}")
        logger.info(message)
    
    def get_logs(self) -> List[str]:
        return self.logs

app = FastAPI(
    title="SFTP Microservice",
    description="Microservice pour connexion SFTP avec authentification par clé SSH",
    version="1.0.0"
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modèles Pydantic pour validation
class ExpectedFile(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

class SFTPConnectionConfig(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=255)
    private_key: str = Field(..., min_length=10)
    
    @validator('private_key')
    def validate_private_key(cls, v):
        if not ('BEGIN' in v and 'PRIVATE KEY' in v):
            raise ValueError('Invalid private key format')
        return v

class DownloadRequest(BaseModel):
    connection: SFTPConnectionConfig
    remote_path: str = Field(..., min_length=1, max_length=1000)
    expected_files: List[ExpectedFile]

class DownloadedFile(BaseModel):
    filename: str
    content_base64: str
    size: int
    download_time: str

class DownloadResponse(BaseModel):
    success: bool
    downloaded_files: List[DownloadedFile]
    missing_files: List[str]
    stats: dict
    logs: List[str] = []

@app.get("/health")
async def health_check():
    """Endpoint de vérification de santé du service"""
    return {
        "status": "healthy",
        "service": "sftp-microservice",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/download-files", response_model=DownloadResponse)
async def download_files(request: DownloadRequest):
    """
    Télécharge des fichiers depuis un serveur SFTP
    
    Args:
        request: Configuration de connexion et liste des fichiers attendus
        
    Returns:
        Informations sur les fichiers téléchargés et manquants
    """
    ssh_client = None
    sftp_client = None
    downloaded_files = []
    missing_files = []
    start_time = datetime.utcnow()
    log_capture = LogCapture()
    
    try:
        log_capture.add(f"🚀 Démarrage de la connexion SFTP vers {request.connection.hostname}:{request.connection.port}")
        
        # Créer le client SSH
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Charger la clé privée avec une meilleure compatibilité
        key_errors = []
        private_key = None
        
        try:
            from cryptography.hazmat.primitives import serialization as crypto_serialization
            from cryptography.hazmat.primitives.asymmetric import ed25519, dsa, rsa, ec
            
            # Charger la clé avec cryptography (supporte mieux les formats modernes)
            file_bytes = request.connection.private_key.encode('utf-8')
            try:
                key = crypto_serialization.load_ssh_private_key(
                    file_bytes,
                    password=None,
                )
            except ValueError:
                key = crypto_serialization.load_pem_private_key(
                    file_bytes,
                    password=None,
                )
            
            # Convertir au format PEM OpenSSH que paramiko peut lire
            pem_key = key.private_bytes(
                crypto_serialization.Encoding.PEM,
                crypto_serialization.PrivateFormat.OpenSSH,
                crypto_serialization.NoEncryption(),
            ).decode('utf-8')
            
            # Charger avec paramiko selon le type de clé
            key_file = io.StringIO(pem_key)
            
            if isinstance(key, rsa.RSAPrivateKey):
                private_key = paramiko.RSAKey.from_private_key(key_file)
                log_capture.add("🔑 Clé RSA chargée avec succès")
            elif isinstance(key, ed25519.Ed25519PrivateKey):
                private_key = paramiko.Ed25519Key.from_private_key(key_file)
                log_capture.add("🔑 Clé Ed25519 chargée avec succès")
            elif isinstance(key, ec.EllipticCurvePrivateKey):
                private_key = paramiko.ECDSAKey.from_private_key(key_file)
                log_capture.add("🔑 Clé ECDSA chargée avec succès")
            elif isinstance(key, dsa.DSAPrivateKey):
                private_key = paramiko.DSSKey.from_private_key(key_file)
                log_capture.add("🔑 Clé DSA chargée avec succès")
            else:
                raise ValueError(f"Type de clé non supporté: {type(key)}")
                
        except Exception as e:
            log_capture.add(f"❌ Erreur lors du chargement de la clé: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Impossible de charger la clé privée: {str(e)}"
            )
        
        # Connexion SSH avec timeouts augmentés
        log_capture.add(f"🔌 Tentative de connexion SSH vers {request.connection.hostname}:{request.connection.port}")
        log_capture.add(f"👤 Utilisateur: {request.connection.username}")
        ssh_client.connect(
            hostname=request.connection.hostname,
            port=request.connection.port,
            username=request.connection.username,
            pkey=private_key,
            timeout=120,  # Augmenté à 2 minutes
            auth_timeout=60,  # Augmenté à 1 minute
            banner_timeout=60
        )
        log_capture.add("✅ Connexion SSH établie avec succès")
        
        # Ouvrir la connexion SFTP avec timeout
        log_capture.add("📂 Ouverture de la session SFTP...")
        sftp_client = ssh_client.open_sftp()
        sftp_client.get_channel().settimeout(180.0)  # Timeout de 3 minutes pour les opérations SFTP
        log_capture.add(f"✅ Session SFTP établie")
        log_capture.add(f"📁 Répertoire cible: {request.remote_path}")
        
        # Lister les fichiers disponibles
        try:
            log_capture.add(f"🔍 Listage des fichiers dans {request.remote_path}...")
            available_files = sftp_client.listdir(request.remote_path)
            log_capture.add(f"📋 Fichiers disponibles: {len(available_files)} fichier(s)")
            if len(available_files) <= 10:
                log_capture.add(f"   Fichiers: {', '.join(available_files)}")
            else:
                log_capture.add(f"   Premiers fichiers: {', '.join(available_files[:10])}...")
        except Exception as e:
            log_capture.add(f"❌ Erreur lors du listage: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Impossible d'accéder au répertoire {request.remote_path}: {str(e)}"
            )
        
        # Chercher et télécharger les fichiers attendus
        expected_filenames = [f.filename for f in request.expected_files]
        log_capture.add(f"📦 Téléchargement de {len(request.expected_files)} fichier(s) attendu(s)...")
        
        for expected_file in request.expected_files:
            filename = expected_file.filename
            
            # Vérifier si le fichier existe
            if filename not in available_files:
                log_capture.add(f"⚠️ Fichier manquant: {filename}")
                missing_files.append(filename)
                continue
            
            # Télécharger le fichier
            try:
                remote_file_path = f"{request.remote_path}/{filename}"
                file_data = io.BytesIO()
                
                download_start = datetime.utcnow()
                log_capture.add(f"⬇️ Téléchargement: {filename}")
                
                # Vérifier la taille du fichier d'abord
                file_attrs = sftp_client.stat(remote_file_path)
                file_size_mb = file_attrs.st_size / (1024 * 1024)
                log_capture.add(f"   Taille: {file_size_mb:.2f} MB")
                
                sftp_client.getfo(remote_file_path, file_data)
                file_data.seek(0)
                
                download_duration = (datetime.utcnow() - download_start).total_seconds()
                log_capture.add(f"   ✅ Terminé en {download_duration:.2f}s")
                
                # Encoder en base64
                file_content = file_data.read()
                content_base64 = base64.b64encode(file_content).decode('utf-8')
                
                downloaded_files.append(DownloadedFile(
                    filename=filename,
                    content_base64=content_base64,
                    size=len(file_content),
                    download_time=datetime.utcnow().isoformat()
                ))
                
                log_capture.add(f"✓ {filename} téléchargé ({len(file_content)} bytes)")
                
            except Exception as e:
                log_capture.add(f"❌ Erreur téléchargement {filename}: {str(e)}")
                missing_files.append(filename)
        
        # Calculer les statistiques
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        total_size = sum(f.size for f in downloaded_files)
        
        stats = {
            "total_expected": len(expected_filenames),
            "total_downloaded": len(downloaded_files),
            "total_missing": len(missing_files),
            "total_size_bytes": total_size,
            "duration_seconds": round(duration, 2)
        }
        
        log_capture.add(f"✅ Téléchargement terminé: {len(downloaded_files)}/{len(expected_filenames)} fichier(s)")
        
        return DownloadResponse(
            success=len(missing_files) == 0,
            downloaded_files=downloaded_files,
            missing_files=missing_files,
            stats=stats,
            logs=log_capture.get_logs()
        )
        
    except paramiko.AuthenticationException:
        log_capture.add("❌ Échec d'authentification SFTP")
        logger.error("Échec d'authentification SFTP")
        raise HTTPException(
            status_code=401,
            detail="Échec d'authentification SFTP. Vérifiez les identifiants et la clé privée."
        )
    except paramiko.SSHException as e:
        log_capture.add(f"❌ Erreur SSH: {str(e)}")
        logger.error(f"Erreur SSH: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur de connexion SSH: {str(e)}"
        )
    except Exception as e:
        log_capture.add(f"❌ Erreur inattendue: {str(e)}")
        logger.error(f"Erreur inattendue: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du téléchargement: {str(e)}"
        )
    finally:
        # Fermer les connexions
        if sftp_client:
            sftp_client.close()
        if ssh_client:
            ssh_client.close()
        logger.info("Connexions fermées")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
