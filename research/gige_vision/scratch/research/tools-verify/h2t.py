import sys,re,html
for p in sys.argv[1:]:
    s=open(p,encoding='utf-8',errors='replace').read()
    s=re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>',' ',s)
    s=re.sub(r'(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>|</tr>','\n',s)
    s=re.sub(r'<[^>]+>',' ',s); s=html.unescape(s)
    s=re.sub(r'[ \t\r\f\v]+',' ',s); s=re.sub(r'\n\s*\n+','\n',s)
    open(p.replace('.html','.txt'),'w',encoding='utf-8').write(s)
