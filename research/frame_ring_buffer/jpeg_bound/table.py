import json, math
E = json.load(open('envelope.json'))
mx = {(e['cam'], e['w'], e['h']): e['max'] for e in E}
page = lambda n: int(math.ceil(n / 4096) * 4096)
modes = [(160,90),(160,120),(320,240),(640,360),(640,480),(960,720),(1280,720),(1920,1080),(2560,1440),(3840,2160)]
cams = ['C922','C930e','generic','Kiyo Pro']
print('| mode | est = 2048+0.5*W*H | slot = page(2*est) | W*H*2 (rejected) | slot/W*H*2 | ' + ' | '.join(f'slot/max {c}' for c in cams) + ' | 3 s @30 (90 slots) | 3 s @60 (180 slots) | W*H*2 3 s @30 / @60 |')
for w,h in modes:
    est = 2048 + 0.5*w*h; slot = page(2*est); rej = page(2*w*h)
    r = []
    for c in cams:
        m = mx.get((c,w,h)); r.append(f'{slot/m:.1f} ({m:,})' if m else '-')
    print(f'| {w}x{h} | {est:,.0f} | {slot:,} | {rej:,} | {slot/rej:.2f} | ' + ' | '.join(r) + f' | {90*slot/2**20:.1f} MiB | {180*slot/2**20:.1f} MiB | {90*rej/2**20:.1f} / {180*rej/2**20:.1f} MiB |')
