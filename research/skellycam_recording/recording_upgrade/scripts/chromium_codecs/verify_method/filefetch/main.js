const {app,BrowserWindow}=require('electron');const path=require('path');
app.whenReady().then(async()=>{const w=new BrowserWindow({show:false});
w.on('page-title-updated',(e,t)=>{if(t.startsWith('RESULT:')){console.log(process.versions.electron,t);app.quit();}});
await w.loadFile(path.join(__dirname,'page.html'));setTimeout(()=>{console.log('timeout');app.quit()},15000);});
