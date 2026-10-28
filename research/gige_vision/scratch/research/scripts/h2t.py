import sys,re,html,io
s=open(sys.argv[1],encoding='utf-8',errors='replace').read()
s=re.sub(r'(?is)<(script|style|noscript|nav|header|footer)[^>]*>.*?</\1>','',s)
s=re.sub(r'(?i)<br\s*/?>|</p>|</li>|</h[1-6]>|</div>|</tr>','\n',s)
s=re.sub(r'(?i)<a [^>]*href="([^"]+)"[^>]*>',r' [\1] ',s)
s=re.sub(r'<[^>]+>','',s)
s=html.unescape(s)
lines=[l.strip() for l in s.splitlines() if l.strip()]
out=open(sys.argv[2],'w',encoding='utf-8')
out.write('\n'.join(lines))
