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
    
    try:
        logger.info(f"Connexion SFTP à {request.connection.hostname}:{request.connection.port}")
        
        # Créer le client SSH
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Charger la clé privée
        try:
            private_key_file = io.StringIO(request.connection.private_key)
            private_key = paramiko.RSAKey.from_private_key(private_key_file)
        except Exception as e:
            try:
                # Essayer avec Ed25519
                private_key_file = io.StringIO(request.connection.private_key)
                private_key = paramiko.Ed25519Key.from_private_key(private_key_file)
            except Exception:
                # Essayer avec ECDSA
                private_key_file = io.StringIO(request.connection.private_key)
                private_key = paramiko.ECDSAKey.from_private_key(private_key_file)
        
        # Connexion SSH
        ssh_client.connect(
            hostname=request.connection.hostname,
            port=request.connection.port,
            username=request.connection.username,
            pkey=private_key,
            timeout=30,
            auth_timeout=30
        )
        
        # Ouvrir la connexion SFTP
        sftp_client = ssh_client.open_sftp()
        logger.info(f"Connexion SFTP établie. Accès au répertoire: {request.remote_path}")
        
        # Lister les fichiers disponibles
        try:
            available_files = sftp_client.listdir(request.remote_path)
            logger.info(f"Fichiers disponibles: {available_files}")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Impossible d'accéder au répertoire {request.remote_path}: {str(e)}"
            )
        
        # Chercher et télécharger les fichiers attendus
        expected_filenames = [f.filename for f in request.expected_files]
        
        for expected_file in request.expected_files:
            filename = expected_file.filename
            
            # Vérifier si le fichier existe
            if filename not in available_files:
                logger.warning(f"Fichier manquant: {filename}")
                missing_files.append(filename)
                continue
            
            # Télécharger le fichier
            try:
                remote_file_path = f"{request.remote_path}/{filename}"
                file_data = io.BytesIO()
                
                logger.info(f"Téléchargement de {filename}...")
                sftp_client.getfo(remote_file_path, file_data)
                file_data.seek(0)
                
                # Encoder en base64
                file_content = file_data.read()
                content_base64 = base64.b64encode(file_content).decode('utf-8')
                
                downloaded_files.append(DownloadedFile(
                    filename=filename,
                    content_base64=content_base64,
                    size=len(file_content),
                    download_time=datetime.utcnow().isoformat()
                ))
                
                logger.info(f"✓ {filename} téléchargé ({len(file_content)} bytes)")
                
            except Exception as e:
                logger.error(f"Erreur lors du téléchargement de {filename}: {str(e)}")
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
        
        logger.info(f"Téléchargement terminé: {stats}")
        
        return DownloadResponse(
            success=len(missing_files) == 0,
            downloaded_files=downloaded_files,
            missing_files=missing_files,
            stats=stats
        )
        
    except paramiko.AuthenticationException:
        logger.error("Échec d'authentification SFTP")
        raise HTTPException(
            status_code=401,
            detail="Échec d'authentification SFTP. Vérifiez les identifiants et la clé privée."
        )
    except paramiko.SSHException as e:
        logger.error(f"Erreur SSH: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur de connexion SSH: {str(e)}"
        )
    except Exception as e:
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
