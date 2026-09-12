// Meet Companion desktop shell.
//
// The app is the same web UI and Python server as the self-hosted version.
// This shell starts the bundled server on a free localhost port, waits for
// it to answer, and opens it in a window. All data lives in the user's app
// data directory; the installed files are never written to.

const { app, BrowserWindow, dialog, shell } = require('electron')
const { spawn } = require('node:child_process')
const http = require('node:http')
const path = require('node:path')
const fs = require('node:fs')

let serverProcess = null
let serverPort = null
let mainWindow = null

function serverExecutable() {
  const name = process.platform === 'win32' ? 'meet-companion-server.exe' : 'meet-companion-server'
  return app.isPackaged
    ? path.join(process.resourcesPath, 'server', name)
    : path.join(__dirname, 'build', 'meet-companion-server', name)
}

function dataDir() {
  return path.join(app.getPath('userData'), 'workspace')
}

function waitForHealth(port, timeoutMs) {
  const started = Date.now()
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const request = http.get({ host: '127.0.0.1', port, path: '/health', timeout: 1500 }, (response) => {
        response.resume()
        if (response.statusCode === 200) return resolve()
        retry()
      })
      request.on('error', retry)
      request.on('timeout', () => {
        request.destroy()
        retry()
      })
    }
    const retry = () => {
      if (serverProcess && serverProcess.exitCode !== null) {
        return reject(new Error(`The server exited with code ${serverProcess.exitCode}.`))
      }
      if (Date.now() - started > timeoutMs) return reject(new Error('The server did not start in time.'))
      setTimeout(attempt, 300)
    }
    attempt()
  })
}

function startServer() {
  const executable = serverExecutable()
  if (!fs.existsSync(executable)) {
    throw new Error(`Server binary not found at ${executable}. Build it with "pyinstaller desktop/server.spec" first.`)
  }
  const dir = dataDir()
  fs.mkdirSync(dir, { recursive: true })

  const logPath = path.join(app.getPath('userData'), 'server.log')
  const log = fs.createWriteStream(logPath, { flags: 'a' })

  return new Promise((resolve, reject) => {
    serverProcess = spawn(executable, ['--data-dir', dir], {
      cwd: path.dirname(executable),
      env: { ...process.env, PYTHONUNBUFFERED: '1', HF_HUB_DISABLE_SYMLINKS_WARNING: '1' },
      windowsHide: true,
    })

    let port = null
    const onData = (chunk) => {
      const text = chunk.toString()
      log.write(text)
      // The server prints its chosen port before it starts listening.
      const match = text.match(/MEET_COMPANION_PORT=(\d+)/)
      if (match && port === null) {
        port = Number(match[1])
        waitForHealth(port, 60_000).then(() => resolve(port), reject)
      }
    }
    serverProcess.stdout.on('data', onData)
    serverProcess.stderr.on('data', onData)
    serverProcess.on('error', reject)
    serverProcess.on('exit', (code) => {
      log.end()
      if (port === null) reject(new Error(`The server exited early with code ${code}. See ${logPath}.`))
    })
  })
}

function stopServer() {
  if (!serverProcess || serverProcess.exitCode !== null) return
  serverProcess.kill()
  serverProcess = null
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    title: 'Meet Companion',
    backgroundColor: '#f5f6fa',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // Links to other sites open in the system browser, never inside the app.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(`http://127.0.0.1:${port}`)) {
      shell.openExternal(url)
      return { action: 'deny' }
    }
    return { action: 'allow' }
  })

  mainWindow.loadURL(`http://127.0.0.1:${port}/`)
  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

app.whenReady().then(async () => {
  try {
    serverPort = await startServer()
    createWindow(serverPort)
  } catch (error) {
    dialog.showErrorBox('Meet Companion could not start', String(error.message || error))
    app.quit()
  }
})

app.on('window-all-closed', () => {
  // On macOS apps stay alive without windows; the server stays with them.
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  // Reuse the running server rather than starting a second one.
  if (BrowserWindow.getAllWindows().length === 0 && serverPort) createWindow(serverPort)
})

app.on('before-quit', stopServer)
app.on('will-quit', stopServer)
process.on('exit', stopServer)
