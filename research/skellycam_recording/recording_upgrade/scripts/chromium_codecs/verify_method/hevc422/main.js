const {app,BrowserWindow}=require('electron');const path=require('path');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');app.commandLine.appendSwitch('disable-renderer-backgrounding');app.commandLine.appendSwitch('disable-features','CalculateNativeWinOcclusion');
app.whenReady().then(async()=>{const w=new BrowserWindow({show:true,width:400,height:300,webPreferences:{backgroundThrottling:false}});w.showInactive&&w.showInactive();
w.webContents.on('console-message',(e,l,m)=>console.log('CONSOLE',m));w.on('page-title-updated',(e,t)=>{if(t.startsWith('RESULT:')){console.log(process.versions.electron,t);app.quit();}});
await w.loadFile(path.join(__dirname,'page.html'));setTimeout(()=>{console.log('timeout');app.quit()},40000);});
