const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('stonicDesktop', {
  windowAction: action => { if (['minimize','maximize','close'].includes(action)) ipcRenderer.send('stonic:window', action); },
  captureScreen: () => ipcRenderer.invoke('stonic:capture'),
  notify: notice => { if(notice&&typeof notice.title==='string'&&typeof notice.body==='string')ipcRenderer.send('stonic:notification',{title:notice.title.slice(0,200),body:notice.body.slice(0,1000),quiet:notice.quiet===true}); },
  onBackendStatus: callback=>{const receive=(_event,data)=>callback(data);ipcRenderer.on('stonic:backend',receive);return()=>ipcRenderer.removeListener('stonic:backend',receive);},
});
