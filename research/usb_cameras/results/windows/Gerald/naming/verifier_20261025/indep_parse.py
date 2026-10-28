# Independent raw-config-descriptor parser (does not use usbdesc.py) to cross-check descriptors.json
import json, sys, struct
d = json.load(open(sys.argv[1]))
for c in d['cameras']:
    cam = c['camera']; raw = bytes.fromhex(c['raw_hex']['configuration'].replace(' ',''))
    dev = bytes.fromhex(c['raw_hex']['device'].replace(' ',''))
    wTotal = struct.unpack_from('<H', raw, 2)[0]
    print('=====', cam['vid'], cam['pid'], cam.get('friendly_name'), 'speed', c['speed'], 'len', len(raw), 'wTotal', wTotal, 'iSerial', dev[16], 'bcdUSB %04x'%struct.unpack_from('<H',dev,2)[0])
    i=0; cur_if=None; cur_alt=None; cur_cls=None; cur_sub=None
    fmts=[]; alts=[]; last_ep=None
    while i < len(raw):
        bl, bt = raw[i], raw[i+1]
        if bl == 0: print('zero len'); break
        b = raw[i:i+bl]
        if bt == 4:
            cur_if, cur_alt, cur_cls, cur_sub = b[2], b[3], b[5], b[6]
        elif bt == 0x24 and cur_cls == 14 and cur_sub == 1 and b[2] == 1:
            print(' VC header bcdUVC %x.%02x clk %d' % (b[4], b[3], struct.unpack_from('<I', b, 7)[0]))
        elif bt == 0x24 and cur_cls == 14 and cur_sub == 2:
            st = b[2]
            if st in (4, 6, 0x10, 0x0c):  # uncompressed, mjpeg, frame-based, (stream-based)
                name = {4:'UNCOMP',6:'MJPEG',0x10:'FRAMEBASED',0x0c:'STREAM'}[st]
                extra = ''
                if st in (4,0x10): extra = b[5:9].decode('latin1')
                fmts.append([cur_if, name, extra, b[4], 0])
            elif st in (5, 7, 0x11):
                fmts[-1][4] += 1
        elif bt == 5:
            mps = struct.unpack_from('<H', b, 4)[0]
            last_ep = (cur_if, cur_alt, b[2], b[3] & 3, mps)
            if cur_cls == 14 and cur_sub == 2 and (b[3]&3) == 1:
                alts.append([cur_if, cur_alt, mps, None])
        elif bt == 0x30:  # SS companion
            if alts and alts[-1][0]==cur_if and alts[-1][1]==cur_alt:
                alts[-1][3] = (b[2], b[3], struct.unpack_from('<H', b, 4)[0])
        i += bl
    for f in fmts: print('  fmt if%d %s %s declared_frames=%d counted=%d' % tuple(f))
    best=0;bestalt=None
    for a in alts:
        mps=a[2]
        if c['speed']=='super' and a[3]:
            bpi = a[3][2]; bps = bpi*8000
        else:
            base = mps & 0x7ff; mult = ((mps>>11)&3)+1
            bps = base*mult*(8000 if c['speed']=='high' else 1000)
        if bps>best: best=bps; bestalt=a
    print('  iso alts', len(alts), 'best', best, bestalt)
