import json,sys,re
for fn in sys.argv[1:]:
  d=json.load(open(fn))
  print('#####',fn)
  for k,v in d.items():
    if not isinstance(v,dict): print(k,str(v)[:300]); continue
    print('==',re.split(r'[\/]',k)[-2:])
    for f in v.get('frames',[]):
      print('  ',f['file'],f['n'],f.get('n_valid_jpeg'),f.get('fps_frames5on'),f.get('arrival_interval_hist_4ms'),'ph',f.get('phase16_modal_bin_fraction'),'a-os med',f.get('arrival_minus_os_ms_median'),'drift',f.get('arrival_minus_os_drift_ms_per_s'),'sd',f.get('arrival_minus_os_resid_sd_ms'),'top',f.get('os_ts_delta_top3_100ns'))
    for s in v.get('samples',[]): print('   luma',s['file'],s['mean_luma'])
