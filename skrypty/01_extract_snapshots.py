"""Krok 1 preagregacji: strumieniowo czyta stations.rar (48 GB JSON) i zapisuje
kompaktowe wiersze (czas UTC w minutach, uid, availableBikes, bikeRacks, freeRacks).
Uzycie: python 01_extract_snapshots.py <k> <n> <rar> <outdir>  (worker k z n)."""
import sys, subprocess, re, orjson, numpy as np, pickle, os
k, n, rar, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
names=[f'stations/output_{i}.json' for i in range(1,59695) if i % n == k]
lf=os.path.join(out,f'list_{k}.txt'); open(lf,'w').write('\n'.join(names)+'\n')
p=subprocess.Popen(['bsdtar','-xOf',rar,'-T',lf],stdout=subprocess.PIPE,bufsize=1<<24)
pat=re.compile(rb'\{\s*"year"')
recs=[]; meta={}; bad=0
def handle(chunk):
    global bad
    try: d=orjson.loads(chunk)
    except Exception: bad+=1; return
    t=int(np.datetime64(f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}T{d['hour']:02d}:{d['minute']:02d}").astype('datetime64[m]').astype(np.int64))
    for s in d['stations_data']:
        if s.get('placeType')!='STATION': continue
        a=s['availabilityStatus']; u=int(s['uid'])
        recs.append((t,u,a['availableBikes'],a['bikeRacks'],a['freeRacks']))
        if u not in meta:
            meta[u]={'name':s.get('name'),'number':s.get('number'),'lat':s['geoCoords']['lat'],'lon':s['geoCoords']['lng'],
                     'clat':float(s.get('centroid_latitude') or 'nan'),'clon':float(s.get('centroid_longitude') or 'nan')}
buf=b''
while True:
    data=p.stdout.read(1<<24)
    if not data: break
    buf+=data
    st=[m.start() for m in pat.finditer(buf)]
    if len(st)>=2:
        for a,b in zip(st[:-1],st[1:]): handle(buf[a:b])
        buf=buf[st[-1]:]
if buf.strip(): handle(buf)
np.save(os.path.join(out,f'recs_{k}.npy'),np.array(recs,dtype=np.int64))
pickle.dump((meta,bad),open(os.path.join(out,f'meta_{k}.pkl'),'wb'))
print('done',k,len(recs),bad)
