import express from 'express';
import cors from 'cors';
import SftpClient from 'ssh2-sftp-client';

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// Endpoint de santé
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Endpoint principal pour télécharger les fichiers SFTP
app.post('/download-files', async (req, res) => {
  const sftp = new SftpClient();
  
  try {
    const {
      hostname,
      port = 22,
      username,
      privateKey,
      remotePath,
      expectedDate,
      expectedFiles
    } = req.body;

    // Validation des paramètres requis
    if (!hostname || !username || !privateKey || !remotePath || !expectedDate) {
      return res.status(400).json({
        error: 'Missing required parameters',
        required: ['hostname', 'username', 'privateKey', 'remotePath', 'expectedDate']
      });
    }

    console.log(`[${new Date().toISOString()}] Connecting to SFTP ${hostname}:${port}`);

    // Connexion SFTP avec clé privée
    await sftp.connect({
      host: hostname,
      port: parseInt(port),
      username,
      privateKey: privateKey.replace(/\\n/g, '\n'), // Support des clés avec \n échappés
      readyTimeout: 20000,
      retries: 2
    });

    console.log(`[${new Date().toISOString()}] Connected successfully`);

    // Liste tous les fichiers dans le répertoire
    const fileList = await sftp.list(remotePath);
    console.log(`[${new Date().toISOString()}] Found ${fileList.length} files in ${remotePath}`);

    const downloadedFiles = [];
    const missingFiles = [];

    // Cherche les fichiers attendus
    for (const expectedFile of expectedFiles || []) {
      const foundFile = fileList.find(f => {
        const fileName = f.name.toLowerCase();
        const searchTerm = expectedFile.toLowerCase();
        return fileName.includes(searchTerm);
      });

      if (foundFile) {
        console.log(`[${new Date().toISOString()}] Downloading: ${foundFile.name}`);
        
        // Télécharge le fichier en buffer
        const fileBuffer = await sftp.get(`${remotePath}/${foundFile.name}`);
        
        downloadedFiles.push({
          name: foundFile.name,
          size: foundFile.size,
          data: fileBuffer.toString('base64'), // Encode en base64 pour transport JSON
          modifyTime: foundFile.modifyTime
        });
      } else {
        console.log(`[${new Date().toISOString()}] Missing: ${expectedFile}`);
        missingFiles.push(expectedFile);
      }
    }

    await sftp.end();
    console.log(`[${new Date().toISOString()}] SFTP connection closed`);

    res.json({
      success: true,
      expectedDate,
      downloadedFiles,
      missingFiles,
      stats: {
        expected: expectedFiles?.length || 0,
        downloaded: downloadedFiles.length,
        missing: missingFiles.length
      }
    });

  } catch (error) {
    console.error(`[${new Date().toISOString()}] SFTP Error:`, error.message);
    
    try {
      await sftp.end();
    } catch (e) {
      // Ignore cleanup errors
    }

    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

app.listen(PORT, () => {
  console.log(`SFTP Microservice listening on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
});
