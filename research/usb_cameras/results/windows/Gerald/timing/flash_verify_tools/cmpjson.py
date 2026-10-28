import json,sys
a=json.load(open(sys.argv[1]));b=json.load(open(sys.argv[2]))
skip={'utc_started','command','inputs','file','dir'}
n=[0];diffs=[]
def walk(x,y,p):
    if isinstance(x,dict):
        for k in set(x)|set(y):
            if k in skip: continue
            if k not in x or k not in y: diffs.append((p+'/'+k,'missing')); continue
            walk(x[k],y[k],p+'/'+k)
    elif isinstance(x,list):
        if len(x)!=len(y): diffs.append((p,'len')); return
        for i,(u,v) in enumerate(zip(x,y)): walk(u,v,f'{p}[{i}]')
    else:
        n[0]+=1
        if x!=y: diffs.append((p,x,y))
walk(a,b,'')
print('leaves compared',n[0],'differences',len(diffs))
for d in diffs[:30]: print(d)
