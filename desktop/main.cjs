const { app, BrowserWindow, ipcMain, dialog, session, desktopCapturer, screen, shell, Notification } = require('electron');
const path = require('node:path');
const net = require('node:net');
const { existsSync } = require('node:fs');
const { startBackend, availablePort, root } = require('../scripts/runtime.cjs');

app.setName('STONIC V2');
app.setAppUserModelId('local.stonic.v2');
const localAppData = process.platform === 'win32' && process.env.LOCALAPPDATA ? process.env.LOCALAPPDATA : app.getPath('appData');
app.setPath('userData', path.join(localAppData, 'STONIC'));
let dataDir;
let main, splash, backend, quitting = false, stageCount = 0, backendRecoveries=0;
const single = app.requestSingleInstanceLock();
if (!single) app.quit();
app.on('second-instance', () => { if (main) { if(main.isMinimized()) main.restore(); main.focus(); } });

function trusted(event) { return main && !main.isDestroyed() && event.sender === main.webContents && event.senderFrame === main.webContents.mainFrame; }
let lastNotice=0;
ipcMain.on('stonic:notification',(event,notice)=>{
  if(!trusted(event)||!notice||notice.quiet||main.isFocused()&&!main.isMinimized()||!Notification.isSupported())return;
  if(typeof notice.title!=='string'||typeof notice.body!=='string'||Date.now()-lastNotice<3000)return;
  lastNotice=Date.now();
  const alert=new Notification({title:notice.title.slice(0,200),body:notice.body.slice(0,1000),silent:true});
  alert.on('click',()=>{if(main&&!main.isDestroyed()){main.restore();main.show();main.focus();}});alert.show();
});
ipcMain.on('stonic:window', (event, action) => {
  if (!trusted(event)) return;
  if (action === 'minimize') main.minimize();
  if (action === 'maximize') main.isMaximized() ? main.unmaximize() : main.maximize();
  if (action === 'close') main.close();
});
ipcMain.handle('stonic:capture', async event => {
  if (!trusted(event)) throw new Error('Untrusted window');
  const sources = await desktopCapturer.getSources({types:['screen'],thumbnailSize:{width:1920,height:1080}});
  const decision = await dialog.showMessageBox(main, {type:'question', title:'Capture a screen',
    message:'Choose a screen to capture into the local Visual Hub.',
    detail:'The image stays in this window. It will not be sent to an AI provider.',
    buttons:[...sources.map((s,i) => `Screen ${i + 1}`), 'Cancel'], defaultId:sources.length, cancelId:sources.length});
  return sources[decision.response]?.thumbnail.toDataURL() || null;
});

function isSafeExternalUrl(raw) {
  try { const target = new URL(raw); if (!['http:','https:'].includes(target.protocol) || target.username || target.password) return false; const host = target.hostname.replace(/^\[|\]$/g,'').replace(/\.$/,'').toLowerCase(); if(['localhost','localhost.localdomain','ip6-localhost','0.0.0.0','::1'].includes(host)) return false; if(net.isIP(host)===4){const [a,b]=host.split('.').map(Number);if(a===10||a===127||(a===169&&b===254)||(a===172&&b>=16&&b<=31)||(a===192&&b===168)||(a===100&&b>=64&&b<=127)||a>=224)return false;} if(net.isIP(host)===6&&(host==='::'||host==='::1'||/^f[cd]/i.test(host)||/^fe[89ab]/i.test(host)||/^ff/i.test(host)))return false; return true; } catch { return false; }
}

async function launch() {
  if (!existsSync(path.join(root,'dist','index.html'))) throw new Error('The interface has not been built. Run npm run build first.');
  splash = new BrowserWindow({width:410,height:230,frame:false,resizable:false,show:false,backgroundColor:'#0d171d',
    webPreferences:{preload:path.join(__dirname,'splash-preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
  await splash.loadFile(path.join(__dirname,'splash.html')); splash.center(); splash.show();
  const port = await availablePort();
  process.env.STONIC_DESKTOP = '1';
  dataDir = path.resolve(process.env.STONIC_DATA_DIR || path.join(app.getPath('userData'), 'data'));
  backend = startBackend(port, message => { stageCount++; if(splash && !splash.isDestroyed()) splash.webContents.send('stonic:stage',{message,completed:Math.min(stageCount,4)}); }, {dataDir});
  await backend.ready();
  watchBackend(port);
  const origin = `http://127.0.0.1:${port}`;
  session.defaultSession.webRequest.onBeforeSendHeaders({urls:[`${origin}/api/*`]}, (details, callback) => {
    callback({requestHeaders:{...details.requestHeaders,'X-Stonic-Token':backend.token}});
  });
  session.defaultSession.setPermissionRequestHandler(async (contents, permission, callback, details) => {
    if (contents !== main?.webContents || !details.requestingUrl.startsWith(origin + '/') || permission !== 'media' || details.mediaTypes?.includes('audio')) { callback(false); return; }
    const answer = await dialog.showMessageBox(main,{type:'question',title:'Local camera preview',message:'Allow STONIC to show a live camera preview?',detail:'Video stays in this workspace. Audio will not be captured.',buttons:['Allow camera','Cancel'],defaultId:1,cancelId:1});
    callback(answer.response === 0);
  });
  const area = screen.getPrimaryDisplay().workArea;
  main = new BrowserWindow({width:Math.min(1600,area.width-40),height:Math.min(1000,area.height-40),
    minWidth:Math.min(800,area.width),minHeight:Math.min(620,area.height),show:false,frame:false,
    backgroundColor:'#080c0f',title:'STONIC V2',webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
  main.webContents.setWindowOpenHandler(({url}) => {
    if (isSafeExternalUrl(url)) void shell.openExternal(url);
    return {action:'deny'};
  });
  main.webContents.on('will-navigate', (event,url) => { if (new URL(url).origin !== origin) event.preventDefault(); });
  main.webContents.on('will-prevent-unload',event=>{
    const answer=dialog.showMessageBoxSync(main,{type:'question',title:'Unsaved changes',message:'Close Stonic and discard unsaved edits?',detail:'Saved records remain on this device.',buttons:['Keep editing','Discard and close'],defaultId:0,cancelId:0});
    if(answer===1)event.preventDefault();
  });
  main.on('closed',()=>{main=null;});
  main.once('ready-to-show', () => { main.show(); if(splash && !splash.isDestroyed()) splash.close(); });
  await main.loadURL(origin);
}

function watchBackend(port){
  const observed=backend;
  observed.child.once('exit',async()=>{
    if(quitting||!main||main.isDestroyed()||backend!==observed)return;
    if(backendRecoveries>=1){main.webContents.send('stonic:backend',{state:'failed',message:'The local service stopped again. Save any open edits, then restart Stonic.'});return;}
    backendRecoveries++;
    main.webContents.send('stonic:backend',{state:'recovering',message:'The local service stopped. Attempting one recovery; interrupted actions will remain paused.'});
    try{
      backend=startBackend(port, undefined, {dataDir});watchBackend(port);await backend.ready();
      if(main&&!main.isDestroyed())main.webContents.send('stonic:backend',{state:'connected',message:'The local service recovered. Inspect Task activity before resuming interrupted work.'});
    }catch{
      if(main&&!main.isDestroyed())main.webContents.send('stonic:backend',{state:'failed',message:'Automatic recovery failed. Save open edits, then restart Stonic.'});
    }
  });
}

app.whenReady().then(async () => {
  if (!single) return;
  try { await launch(); }
  catch (error) {
    const result = await dialog.showMessageBox({type:'error',title:'STONIC could not initialize',message:'The local workspace could not start.',detail:error.message,buttons:['Retry','Exit'],defaultId:0,cancelId:1});
    await backend?.stop();
    if (result.response === 0) app.relaunch();
    app.quit();
  }
});
app.on('window-all-closed', () => app.quit());
app.on('before-quit', event => {
  if (quitting) return;
  event.preventDefault();
  if(main && !main.isDestroyed()){main.close();return;}
  quitting = true;
  Promise.resolve(backend?.stop()).finally(() => app.quit());
});
