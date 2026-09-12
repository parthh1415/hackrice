import json,re,time,urllib.request,collections,itertools,math
UA="HackRice16 Firebreak research parth@rice.edu"
def get(u,b=False):
    r=urllib.request.Request(u,headers={"User-Agent":UA,"Accept-Encoding":"gzip, deflate"})
    d=urllib.request.urlopen(r,timeout=60).read()
    if d[:2]==b'\x1f\x8b':
        import gzip; d=gzip.decompress(d)
    return d if b else d.decode('utf-8','replace')

FUNDS={"Citadel":1423053,"Millennium":1273087,"Point72":1603466,
       "TwoSigma":1179392,"Renaissance":1037389}

def latest_13f(cik):
    j=json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    r=j["filings"]["recent"]
    for i in range(len(r["form"])):
        if r["form"][i]=="13F-HR":
            return j.get("name"), r["accessionNumber"][i].replace("-",""), r["filingDate"][i]
    return j.get("name"),None,None

def holdings(cik,acc):
    idx=json.loads(get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"))
    fn=next((i["name"] for i in idx["directory"]["item"]
             if i["name"].lower().endswith(".xml") and "primary_doc" not in i["name"].lower()),None)
    if not fn: return {}
    raw=get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{fn}")
    out=collections.defaultdict(float)
    for m in re.finditer(r"<(?:\w+:)?infoTable>(.*?)</(?:\w+:)?infoTable>",raw,re.S):
        b=m.group(1)
        if re.search(r"<(?:\w+:)?putCall>\s*\w",b): continue      # drop options
        cu=re.search(r"<(?:\w+:)?cusip>\s*([^<\s]+)",b)
        vl=re.search(r"<(?:\w+:)?value>\s*([\d.]+)",b)
        if cu and vl: out[cu.group(1)[:8].upper()]+=float(vl.group(1))
    return dict(out)

CUSIP={"67066G10":"NVDA","03783310":"AAPL","59491810":"MSFT","02313510":"AMZN",
       "02079K30":"GOOGL","30303M10":"META","11135F10":"AVGO","00790310":"AMD",
       "88160R10":"TSLA","46625H10":"JPM"}

books={}
for nm,cik in FUNDS.items():
    name,acc,dt=latest_13f(cik)
    if not acc: print(f"{nm}: no 13F-HR"); continue
    h=holdings(cik,acc)
    sel={CUSIP[c]:v for c,v in h.items() if c in CUSIP}
    tot=sum(sel.values())
    books[nm]=(sel,tot,dt)
    print(f"{nm:<12} filed {dt}  positions={len(h):>5}  top10-tech=${tot/1e9:>7.1f}B  names={len(sel)}")
    time.sleep(0.3)

print("\n=== weights within the 10-asset universe ===")
names=list(CUSIP.values())
print(f"{'':<12}"+"".join(f"{n:>7}" for n in names))
W={}
for nm,(sel,tot,dt) in books.items():
    w={n:(sel.get(n,0)/tot if tot else 0) for n in names}; W[nm]=w
    print(f"{nm:<12}"+"".join(f"{w[n]*100:>6.1f}%" for n in names))

print("\n=== pairwise portfolio overlap (cosine similarity of weights) ===")
def cos(a,b):
    num=sum(a[k]*b[k] for k in names)
    da=math.sqrt(sum(v*v for v in a.values())); db=math.sqrt(sum(v*v for v in b.values()))
    return num/(da*db) if da and db else 0
ks=list(W)
print(f"{'':<12}"+"".join(f"{k[:7]:>9}" for k in ks))
ovs=[]
for a in ks:
    row=f"{a:<12}"
    for b in ks:
        c=cos(W[a],W[b]); row+=f"{c:>9.2f}"
        if a<b: ovs.append(c)
    print(row)
print(f"\nmean pairwise overlap (off-diagonal): {sum(ovs)/len(ovs):.3f}")
print(f"max: {max(ovs):.3f}   min: {min(ovs):.3f}")
