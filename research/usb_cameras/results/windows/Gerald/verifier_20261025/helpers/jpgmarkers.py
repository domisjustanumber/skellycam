import sys
for p in sys.argv[1:]:
    b=open(p,'rb').read()
    i=2; ms=[]
    while i<len(b)-4:
        if b[i]!=0xFF: break
        m=b[i+1]; L=int.from_bytes(b[i+2:i+4],'big')
        extra=''
        if m==0xE0 or m==0xFE or (0xE1<=m<=0xEF): extra=repr(b[i+4:i+4+min(L-2,12)])
        if m==0xC0: extra=f'{int.from_bytes(b[i+7:i+9],"big")}x{int.from_bytes(b[i+5:i+7],"big")} comps={b[i+9]} samp={[hex(b[i+11+3*k]) for k in range(b[i+9])]}'
        ms.append(f'{m:02X}{extra}')
        if m==0xDA: break
        i+=2+L
    print(p, len(b), ms, 'tail', b[-2:].hex())
