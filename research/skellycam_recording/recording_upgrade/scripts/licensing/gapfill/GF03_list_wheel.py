import sys, zipfile
for p in sys.argv[1:]:
    z = zipfile.ZipFile(p)
    print("==", p.rsplit("/",1)[-1])
    for i in z.infolist():
        print(f"  {i.file_size:>10}  {i.filename}")
