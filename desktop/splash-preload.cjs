const { ipcRenderer } = require('electron');
window.addEventListener('DOMContentLoaded', () => {
  ipcRenderer.on('stonic:stage', (_event, stage) => {
    document.getElementById('stage').textContent = stage.message;
    document.getElementById('progress').value = stage.completed;
    document.getElementById('stage-count').textContent = `${stage.completed} / 4 CHECKPOINTS`;
  });
});
