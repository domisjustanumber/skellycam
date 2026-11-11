import sys, zipfile
p, member, out = sys.argv[1:4]
open(out, "wb").write(zipfile.ZipFile(p).read(member))
