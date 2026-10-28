# /// script
# requires-python = ">=3.10"
# dependencies = ["simplejpeg==1.8.2", "numpy<2.3"]
# ///
import sys,glob,re,simplejpeg,collections
c=collections.Counter()
for f in sorted(glob.glob(sys.argv[1]+'/*.jpg')):
    try: simplejpeg.decode_jpeg(open(f,'rb').read(),strict=True); c['ok']+=1
    except Exception as e:
        m=re.search(r'(\d+) extraneous',str(e)); c[int(m.group(1)) if m else str(e)[:50]]+=1
k=[x for x in c if isinstance(x,int)]
print('n',sum(c.values()),'ok',c['ok'],'min',min(k),'max',max(k),'n_gt_500',sum(c[x] for x in k if x>500))
