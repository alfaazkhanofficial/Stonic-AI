import { _electron as electron, expect } from '@playwright/test';
import { createRequire } from 'node:module';
import path from 'node:path';
import fs from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const require = createRequire(import.meta.url);
const root = path.resolve(import.meta.dirname,'..');
const executablePath=process.env.STONIC_ELECTRON_PATH || require('electron');
const appRoot=process.env.STONIC_APP_ROOT ? path.resolve(process.env.STONIC_APP_ROOT) : root;
const app = await electron.launch({executablePath,args:[appRoot],
  env:{...process.env,STONIC_DATA_DIR:path.join(root,'.runtime','desktop-test')},timeout:35000});
let tearingDown=false;
try {
  let page;
  const deadline = Date.now()+30000;
  while(Date.now()<deadline) {
    page = app.windows().find(window => window.url().startsWith('http://127.0.0.1:'));
    if(page) break;
    await new Promise(resolve=>setTimeout(resolve,150));
  }
  if(!page) throw new Error('Native main window did not open after startup.');
  page.on('dialog',dialog=>{void (dialog.type()==='beforeunload'&&!tearingDown?dialog.dismiss():dialog.accept()).catch(()=>{});});
  await expect(page.getByText('LOCAL WORKSPACE',{exact:true})).toBeVisible();
  const welcome=page.getByRole('dialog',{name:'Welcome to Stonic'});
  if(await welcome.count())await welcome.getByRole('button',{name:'Start workspace'}).click();
  await expect(page.getByRole('button',{name:'Minimize window'})).toBeAttached();
  await expect(page.getByRole('button',{name:'CONNECT AI',exact:true})).toBeVisible();
  const viewport = await page.evaluate(()=>({width:innerWidth,height:innerHeight}));
  if(viewport.width>1050) {
    const composer = await page.locator('.composer-footnote').boundingBox();
    if(composer.y + composer.height > viewport.height) throw new Error('Native composer exceeds the viewport at current DPI');
  }
  await page.getByRole('textbox',{name:'Message STONIC'}).fill('/status');
  await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.locator('.message-assistant').last()).toContainText('CPU:');
  await page.getByRole('button',{name:'New conversation'}).click();
  await fs.mkdir(path.join(root,'.runtime','screenshots'),{recursive:true});
  await page.screenshot({path:path.join(root,'.runtime','screenshots','stonic-desktop.png')});
  const windows = await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().length);
  if(windows!==1) throw new Error(`Expected one main window after splash handoff; got ${windows}`);
  const security = await app.evaluate(({BrowserWindow})=>{
    const preferences = BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences();
    return {sandbox:preferences.sandbox,contextIsolation:preferences.contextIsolation,nodeIntegration:preferences.nodeIntegration};
  });
  if(!security.sandbox || !security.contextIsolation || security.nodeIntegration) throw new Error('Desktop renderer security configuration failed');
  await page.evaluate(()=>{window.__backendChecks=[];window.stonicDesktop.onBackendStatus(data=>window.__backendChecks.push(data.state));});
  const nativePid=await app.evaluate(()=>process.pid);
  await promisify(execFile)(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/verify-owned-recovery.py'),String(nativePid)]);
  await expect.poll(()=>page.evaluate(()=>window.__backendChecks),{timeout:35000}).toContain('connected');
  await expect(page.getByText('LOCAL WORKSPACE',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'NOTES',exact:true}).click();
  await page.getByRole('button',{name:'Add note',exact:true}).click();
  await page.getByLabel('note title').fill('Unsaved native acceptance fixture');
  await app.evaluate(({dialog})=>{globalThis.__originalDialog=dialog.showMessageBoxSync;dialog.showMessageBoxSync=()=>0;});
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].close());
  await expect(page.getByLabel('note title')).toHaveValue('Unsaved native acceptance fixture');
  await app.evaluate(({dialog})=>{dialog.showMessageBoxSync=globalThis.__originalDialog;});
  await page.getByRole('button',{name:'Back to notes',exact:true}).click();
  console.log(JSON.stringify({nativeStartup:'passed',splashHandoff:'passed',localChat:'passed',textOnlyWorkspace:'passed',backendCrashRecovery:'passed',unsavedCloseGuard:'passed',viewport,security},null,2));
} finally {
  tearingDown=true;
  // A failing assertion must not leave an unsaved-test dialog blocking teardown.
  try{await app.evaluate(({dialog})=>{dialog.showMessageBoxSync=()=>1;});}catch{/* Process may already have exited. */}
  await app.close();
}
