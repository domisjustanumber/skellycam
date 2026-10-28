import sys,re,collections
c=collections.Counter()
for l in open(sys.argv[1],encoding='utf-8',errors='replace'):
    if not re.search(r'warning C\d+',l): continue
    m=re.search(r'([A-Za-z_]+\.[ch])\(\d+,\d+\): warning (C\d+)',l); p=re.search(r'([A-Za-z_]+)\.vcxproj',l)
    c[(m.groups() if m else l[:60], p.group(1) if p else None)]+=1
for k,v in c.items(): print(v,k)
