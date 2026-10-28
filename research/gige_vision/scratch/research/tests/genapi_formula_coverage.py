"""Offline: how much of a real camera's GenApi XML would a toy evaluator cover?
Counts node types and tries to parse every SwissKnife/IntSwissKnife/Converter/IntConverter
formula with the toy translator from gev_scratch_probe.py.
usage: python -I genapi_formula_coverage.py <tests_dir> file1.xml [file2.xml ...]"""
import sys, ast, re, collections, importlib.util
import xml.etree.ElementTree as ET
spec = importlib.util.spec_from_file_location("probe", sys.argv[1] + "/gev_scratch_probe.py")
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)

def nodes(e):
    for ch in e:
        t = ch.tag.split('}')[-1]
        if t == 'Group': yield from nodes(ch)
        elif ch.get('Name'): yield t, ch

for path in sys.argv[2:]:
    root = ET.parse(path).getroot()
    L = list(nodes(root))
    kinds = collections.Counter(t for t, _ in L)
    ok, fail, reasons = 0, 0, collections.Counter()
    funcs = collections.Counter()
    for t, e in L:
        if t not in ("SwissKnife", "IntSwissKnife", "Converter", "IntConverter"):
            continue
        formulas = [x.text for x in e if x.tag.split('}')[-1] in ("Formula", "FormulaTo", "FormulaFrom") and x.text]
        for f in formulas:
            for fn in re.findall(r"\b([A-Z]{2,})\s*\(", f):
                funcs[fn] += 1
            try:
                ast.parse(P.translate_formula(f), mode="eval"); ok += 1
            except Exception as ex:
                fail += 1; reasons[type(ex).__name__ + ": " + str(ex)[:40]] += 1
    sel = sum(1 for t, e in L if any(x.tag.split('}')[-1] == 'pSelected' for x in e))
    avail = sum(1 for t, e in L if any(x.tag.split('}')[-1] in ('pIsAvailable', 'pIsImplemented', 'pIsLocked') for x in e))
    inval = sum(1 for t, e in L if any(x.tag.split('}')[-1] == 'pInvalidator' for x in e))
    paddr = sum(1 for t, e in L if any(x.tag.split('}')[-1] in ('pAddress', 'pIndex', 'IntSwissKnife') for x in e))
    print(f"== {path.split('/')[-1]}: {len(L)} named nodes; schema {root.get('SchemaMajorVersion')}.{root.get('SchemaMinorVersion')}")
    print("   node kinds:", dict(kinds.most_common()))
    print(f"   formulas parsed by toy translator: {ok}/{ok+fail}; failures: {dict(reasons.most_common(5))}")
    print(f"   formula functions used: {dict(funcs.most_common())}")
    print(f"   nodes with pSelected (selectors): {sel}; with pIsAvailable/pIsImplemented/pIsLocked: {avail}; "
          f"with pInvalidator (cache invalidation): {inval}; with pAddress/pIndex (computed addresses): {paddr}")
