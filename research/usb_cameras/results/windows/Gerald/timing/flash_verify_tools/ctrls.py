import json,glob,sys,os
for f in sorted(glob.glob(sys.argv[1]+'/capture/*.session.json')):
  d=json.load(open(f)); c=d['controls']
  if not c.get('exposure_log2',{}).get('supported',True): continue
  print(os.path.basename(f)[:17],'exp',c['exposure_log2']['value'],'flags',c['exposure_log2']['flags'],'gain',c['gain']['value'],c['gain']['flags'],'wb',c['white_balance_k']['value'],'errors',d.get('errors'))
