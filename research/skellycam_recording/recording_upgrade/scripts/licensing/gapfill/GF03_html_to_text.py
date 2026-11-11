import sys, html, re
from html.parser import HTMLParser
class P(HTMLParser):
    def __init__(s): super().__init__(); s.out=[]; s.skip=0
    def handle_starttag(s,t,a):
        if t in ("script","style"): s.skip+=1
        if t in ("p","li","tr","td","th","br","div","h1","h2","h3","h4","pre","dt","dd"): s.out.append("\n")
    def handle_endtag(s,t):
        if t in ("script","style"): s.skip-=1
    def handle_data(s,d):
        if not s.skip: s.out.append(d)
src, dst = sys.argv[1:3]
p=P(); p.feed(open(src,encoding="utf-8",errors="replace").read())
t="".join(p.out)
t=re.sub(r"[ \t\r ]+"," ",t)
t=re.sub(r"\n\s*\n+","\n",t)
open(dst,"w",encoding="utf-8").write(t)
