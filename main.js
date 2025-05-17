const { app, BrowserWindow } = require('electron');
const path = require('path');
const { PythonShell } = require('python-shell');
const fs = require('fs');
const os = require('os');

let mainWindow;
let pythonProcess;
const flaskPort = 5051;
const logPath = path.join(os.homedir(), 'Desktop', 'python-error.log');

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    icon: path.join(__dirname, 'static', 'fish-hook.png')
  });

  // Start the Python backend
  startPythonBackend(() => {
    // Wait a moment for Flask to start, then load the app
    setTimeout(() => {
      mainWindow.loadURL(`http://localhost:${flaskPort}`);
    }, 2000); // 2 seconds, adjust if needed
  });
}

function startPythonBackend(callback) {
  const pythonPath = app.isPackaged
    ? '/usr/bin/python3'
    : path.join(__dirname, 'venv', 'bin', 'python');

  const scriptName = 'app.py';
  const scriptPath = app.isPackaged ? process.resourcesPath : __dirname;

  const options = {
    mode: 'text',
    pythonPath: pythonPath,
    pythonOptions: ['-u'],
    scriptPath: scriptPath
  };

  pythonProcess = new PythonShell(scriptName, options);

  pythonProcess.on('message', function (message) {
    console.log('Python message:', message);
  });

  pythonProcess.on('error', function (err) {
    console.error('Python error:', err);
    fs.appendFileSync(logPath, String(err) + '\n');
  });

  pythonProcess.on('stderr', function (stderr) {
    console.error('Python stderr:', stderr);
    fs.appendFileSync(logPath, String(stderr) + '\n');
  });

  if (callback) callback();
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
}); 