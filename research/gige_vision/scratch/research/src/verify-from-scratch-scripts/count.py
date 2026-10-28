import sys, xml.etree.ElementTree as ET
for p in sys.argv[1:]:
    r=ET.parse(p).getroot()
    def ln(e): return e.tag.split('}')[-1]
    els=list(r.iter())
    named=[e for e in els if e.get('Name') and ln(e) not in ('EnumEntry','StructEntry')]
    named_all=[e for e in els if e.get('Name')]
    sk=[e for e in els if ln(e) in ('SwissKnife','IntSwissKnife')]
    conv=[e for e in els if ln(e) in ('Converter','IntConverter')]
    sel=[e for e in named if any(ln(c)=='pSelected' for c in e)]
    pred=[e for e in named_all if any(ln(c) in ('pIsAvailable','pIsImplemented','pIsLocked') for c in e)]
    inv=[e for e in named_all if any(ln(c)=='pInvalidator' for c in e)]
    inv2=[e for e in els if any(ln(c)=='pInvalidator' for c in e)]
    addr=[e for e in els if any(ln(c) in ('pAddress','pIndex') for c in e)]
    form=[c for e in els for c in e if ln(c) in ('Formula','FormulaTo','FormulaFrom')]
    print(p, 'named(non-entry)',len(named),'named_all',len(named_all),'sk',len(sk),'conv',len(conv),'sel',len(sel),'pred',len(pred),'inv(named)',len(inv),'inv(any)',len(inv2),'addr',len(addr),'formulas',len(form))
