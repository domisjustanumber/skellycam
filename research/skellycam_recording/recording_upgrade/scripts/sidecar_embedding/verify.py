import subprocess, sys, json, hashlib
orig, new = sys.argv[1], sys.argv[2]
def pkts(p):
    out = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","packet=pos,size,pts","-of","json",p],capture_output=True,text=True,check=True).stdout
    return [(int(x["pos"]),int(x["size"]),int(x["pts"])) for x in json.loads(out)["packets"]]
a, b = pkts(orig), pkts(new)
ob, nb = open(orig,"rb").read(), open(new,"rb").read()
same = sum(1 for x,y in zip(a,b) if x==y)
# ffprobe pos = SimpleBlock body start; a 4-byte block header (track vint, int16 timecode, flags) precedes the JPEG
bytes_ok = sum(1 for pos,sz,_ in b if nb[pos+4:pos+4+sz]==ob[pos+4:pos+4+sz] and nb[pos+4:pos+6]==b"\xff\xd8" and nb[pos+2+sz:pos+4+sz]==b"\xff\xd9")
diff = [i for i in range(len(ob)) if ob[i]!=nb[i]]
print(f"packets orig={len(a)} new={len(b)} identical(pos,size,pts)={same} jpeg_bytes_identical_with_SOI_EOI={bytes_ok}")
print(f"first JPEG pos orig={a[0][0]} new={b[0][0]}")
print(f"bytes changed inside original length: {len(diff)} in range [{min(diff)},{max(diff)}]; appended={len(nb)-len(ob)}")
