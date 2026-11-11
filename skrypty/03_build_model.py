"""Krok 2 preagregacji: buduje tabele modelu gwiazdy dla Power BI (parquet).
Wszystkie czasy w Europe/Warsaw. Wejscie: recs_*.npy/meta_*.pkl (01), trips_local.parquet (02),
geojsony, weather_data.csv, Mass_Events.csv, Locations.csv."""
import numpy as np, pandas as pd, pickle, json, glob, sys, os
W, D, O = sys.argv[1], sys.argv[2], sys.argv[3]   # workdir, datadir, outdir
os.makedirs(O, exist_ok=True)
EXCL=[20257383,56365818,47264647]          # 2 stacje testowe + "willowa" spoza Warszawy
HOL=pd.to_datetime(['2023-06-08','2023-08-15','2023-11-01'])
ARTEFAKT=pd.to_datetime(['2023-10-10','2023-10-11'])
LOG={}
def save(df,name):
    df.to_parquet(os.path.join(O,name+'.parquet'),index=False); LOG[name]=len(df); print(name,len(df))

# ---------- snapshoty -> slot 5 min, czas lokalny ----------
a=np.concatenate([np.load(f) for f in sorted(glob.glob(f'{W}/recs_*.npy'))])
s=pd.DataFrame(a,columns=['t','uid','avail','racks','free']); del a
s=s[~s.uid.isin(EXCL)]
for c in ['avail','racks','free']: s[c]=s[c].astype('int16')
ts=pd.to_datetime(s.t.values,unit='m').tz_localize('UTC').tz_convert('Europe/Warsaw').tz_localize(None)
s['slot']=ts.round('5min'); s=s.drop(columns='t')
s=s.sort_values(['uid','slot']).drop_duplicates(['uid','slot'],keep='last')
s['date']=s.slot.dt.normalize(); s['hour']=s.slot.dt.hour.astype('int8')
s['empty']=s.avail==0; s['over']=s.avail>s.racks
s['outlier']=s.avail>2*s.racks+10
s['avail_ok']=s.avail.where(~s.outlier)
LOG['rows_5min']=len(s)
meta={}
for f in sorted(glob.glob(f'{W}/meta_*.pkl')):
    m,_=pickle.load(open(f,'rb'))
    for u,v in m.items(): meta.setdefault(u,v)

# F_StanStacji: stacja x dzien x godzina
g=s.groupby(['uid','date','hour'],sort=True)
f=g.agg(slots=('avail','size'),empty_slots=('empty','sum'),over_slots=('over','sum'),
        avg_bikes=('avail_ok','mean'),min_bikes=('avail','min'),max_bikes=('avail','max'),
        bikes_first=('avail','first'),racks=('racks','median')).reset_index()
for c in ['slots','empty_slots','over_slots','min_bikes','max_bikes','bikes_first']: f[c]=f[c].astype('int16')
f['avg_bikes']=f.avg_bikes.round(2).astype('float32'); f['racks']=f.racks.astype('int16')
f['date']=f.date.dt.date
save(f,'F_StanStacji')

# ---------- ranking poranny i top 20 ----------
wd=(s.slot.dt.dayofweek<5)&(~s.date.isin(HOL))
morn=s[wd&s.hour.between(6,9)]
ps=morn.groupby('uid').agg(n=('empty','size'),empty_slots=('empty','sum'))
ps['empty_share_6_10']=ps.empty_slots/ps.n
ps=ps[ps.n>=0.5*ps.n.max()].sort_values('empty_share_6_10',ascending=False)
ps['rank_6_10']=np.arange(1,len(ps)+1)
top=ps.index[:20].tolist(); LOG['top20']=top

# ---------- przejazdy ----------
t=pd.read_parquet(f'{W}/trips_local.parquet')
LOG['trips_raw']=len(t)
t=t[~t.dep.dt.normalize().isin(ARTEFAKT)]
st_uids=set(s.uid.unique())
dep=t[t.from_uid.isin(st_uids)&(t.dur_min<=1440)]
arr=t[t.to_uid.isin(st_uids)]   # zwroty licza sie zawsze (rower wraca do systemu)
d1=dep.groupby([dep.from_uid.astype('int64').rename('uid'),dep.dep.dt.normalize().rename('date'),dep.dep.dt.hour.rename('hour')]).size().rename('departures')
a1=arr.groupby([arr.to_uid.astype('int64').rename('uid'),arr.arr.dt.normalize().rename('date'),arr.arr.dt.hour.rename('hour')]).size().rename('arrivals')
fp=pd.concat([d1,a1],axis=1).fillna(0).astype('int32').reset_index()
fp=fp[~fp.uid.isin(EXCL)]; fp['hour']=fp.hour.astype('int8'); fp['date']=fp.date.dt.date
save(fp,'F_Przejazdy')

# ---------- komorki siatki i pogoda ----------
cen=json.load(open(f'{D}/centroidy.geojson'))['features']
dk=pd.DataFrame([{'CellID':int(c['properties']['id']),'lon':c['geometry']['coordinates'][0],'lat':c['geometry']['coordinates'][1]} for c in cen])
def nearest_cell(lat,lon):
    d=(dk.lat.values[None,:]-np.asarray(lat)[:,None])**2+((dk.lon.values[None,:]-np.asarray(lon)[:,None])*0.61)**2
    return dk.CellID.values[d.argmin(1)]
save(dk,'D_Komorka')
w=pd.read_csv(f'{D}/weather_data.csv',header=None,names=['dt','lat','lon','temp','cond','precip','wind'])
w['CellID']=nearest_cell(w.lat.values,w.lon.values)
w['dt']=pd.to_datetime(w.dt); w['date']=w.dt.dt.date; w['hour']=w.dt.dt.hour.astype('int8')
LOG['weather_cells']=int(w.CellID.nunique()); LOG['weather_dup']=int(w.duplicated(['CellID','dt']).sum())
w=w.drop_duplicates(['CellID','dt'])
save(w[['CellID','date','hour','temp','precip','wind','cond']],'F_Pogoda')

# ---------- D_Stacja ----------
geo=pd.DataFrame([x['properties'] for x in json.load(open(f'{D}/stations_attr.geojson'))['features']]).drop(columns=['lat','lon']).set_index('uid')
racks=s.groupby('uid').racks.median()
ds=pd.DataFrame([{'uid':u,'name':v['name'],'number':v['number'],'lat':v['lat'],'lon':v['lon'],
                  'clat':v['clat'],'clon':v['clon']} for u,v in meta.items() if u not in EXCL])
ds['CellID']=nearest_cell(ds.clat.fillna(ds.lat).values,ds.clon.fillna(ds.lon).values)
ds['racks']=ds.uid.map(racks).round().astype('Int16')
ds=ds.drop(columns=['clat','clon']).join(geo[['d_metro_st','d_city_cen','d_bus_tram','d_railway','pop_2023']],on='uid')
ds['has_attributes']=ds.d_metro_st.notna()
ds=ds.join(ps[['empty_share_6_10','rank_6_10']],on='uid')
ds['is_top20']=ds.uid.isin(top)
ds['rank_6_10']=ds.rank_6_10.astype('Int16')
save(ds,'D_Stacja')

# ---------- symulacja nocnego stanu dla top 20 ----------
# Model popytu: odjazdy w slocie 5 min z danych; gdy stacja byla pusta (popyt ucenzurowany)
# imputujemy odjazdy ~ Poisson(lambda), lambda = srednia odjazdow w tym slocie dnia w dni, gdy stacja nie byla pusta.
rng=np.random.default_rng(42); REPS=30; EXTRA=np.arange(0,21)
tw=t.copy(); tw['ds']=tw.dep.dt.floor('5min'); tw['as_']=tw.arr.dt.floor('5min')
sim_rows=[]
for u in top:
    x=s[(s.uid==u)&wd&(s.hour>=5)&(s.hour<10)].copy()
    x['sod']=(x.slot.dt.hour*60+x.slot.dt.minute-300)//5      # 0..59
    days=sorted(x.date.unique())
    av=x.pivot_table(index='date',columns='sod',values='avail',aggfunc='last').reindex(columns=range(60))
    dd=tw[(tw.from_uid==u)&(tw.dur_min<=1440)]; dd=dd[dd.ds.dt.normalize().isin(days)&(dd.ds.dt.hour>=5)&(dd.ds.dt.hour<10)]
    aa=tw[tw.to_uid==u]; aa=aa[aa.as_.dt.normalize().isin(days)&(aa.as_.dt.hour>=5)&(aa.as_.dt.hour<10)]
    def mat(df,col):
        k=df[col]; m=pd.crosstab(k.dt.normalize(),(k.dt.hour*60+k.dt.minute-300)//5)
        return m.reindex(index=av.index,columns=range(60)).fillna(0).values
    Dm, Am = mat(dd,'ds'), mat(aa,'as_')
    A=av.values; nonempty=(A>0)
    lam=np.nanmean(np.where(nonempty,Dm,np.nan),axis=0); lam=np.nan_to_num(lam)
    s0=A[:,0]; ok=~np.isnan(s0)
    Dm,Am,A,s0=Dm[ok],Am[ok],A[ok],s0[ok]
    cens=(A==0)
    act=np.nansum(A[:,12:]==0)*5/60                    # faktyczne godziny pustej 6-10
    for e in EXTRA:
        tot=0.0
        for r in range(REPS):
            dem=np.where(cens,rng.poisson(lam,size=Dm.shape),Dm)
            st=s0+e; emp=0
            for j in range(60):
                st=np.maximum(st+Am[:,j]-dem[:,j],0)
                if j>=12: emp+=(st==0).sum()
            tot+=emp*5/60
        sim_rows.append({'uid':u,'extra_bikes':int(e),'empty_h_sim':tot/REPS,'empty_h_actual':act,'days':int(ok.sum()),
                         'stock5_median':float(np.median(s0))})
sim=pd.DataFrame(sim_rows)
save(sim,'F_Symulacja')
# alokacja zachlanna budzetu rowerow (0..150) miedzy top 20
curve={u:g.set_index('extra_bikes').empty_h_sim for u,g in sim.groupby('uid')}
alloc={u:0 for u in top}; bud=[]; arows=[]
base=sum(c.loc[0] for c in curve.values())
for B in range(0,151):
    if B>0:
        best=max(top,key=lambda u:(curve[u].loc[alloc[u]]-curve[u].loc[alloc[u]+1]) if alloc[u]+1 in curve[u].index else -1)
        alloc[best]+=1
    tot=sum(curve[u].loc[alloc[u]] for u in top)
    bud.append({'budget':B,'empty_h_sim':tot,'reduction_vs_sim0':1-tot/base})
    arows+= [{'budget':B,'uid':u,'extra_bikes':alloc[u]} for u in top]
save(pd.DataFrame(bud),'F_Budzet'); save(pd.DataFrame(arows),'F_Alokacja')
LOG['sim_base_h']=base; LOG['actual_h']=float(sim.groupby('uid').empty_h_actual.first().sum())

# ---------- imprezy ----------
loc=pd.read_csv(f'{D}/Locations.csv'); loc.columns=['Location_ID','name','address','lat','lon']
loc['coord_rounded']=((loc.lat*200).round(6)%1==0)&((loc.lon*200).round(6)%1==0)
save(loc,'D_Lokalizacja')
ev=pd.read_csv(f'{D}/Mass_Events.csv'); ev.columns=['date','time','participants','type','info','Location_ID']
ev['EventID']=np.arange(1,len(ev)+1)
ev['bad_time']=ev.time.str.strip().eq('00:00-01:00')
tt=ev.time.str.extract(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})')
ev['start']=pd.to_datetime(ev.date+' '+tt[0]); ev['end']=pd.to_datetime(ev.date+' '+tt[1])
ev.loc[ev.end<=ev.start,'end']+=pd.Timedelta(days=1)
ev['Location_ID']=ev.Location_ID.astype('Int64'); ev['date']=pd.to_datetime(ev.date).dt.date
ev['in_data_window']=(ev.start>='2023-05-06')&(ev.start<'2023-11-30')
save(ev[['EventID','date','time','start','end','participants','type','info','Location_ID','bad_time','in_data_window']],'F_Imprezy')
R=6371000
la1,lo1=np.radians(loc.lat.values)[:,None],np.radians(loc.lon.values)[:,None]
la2,lo2=np.radians(ds.lat.values)[None,:],np.radians(ds.lon.values)[None,:]
dist=2*R*np.arcsin(np.sqrt(np.sin((la2-la1)/2)**2+np.cos(la1)*np.cos(la2)*np.sin((lo2-lo1)/2)**2))
i,j=np.where(dist<=1000)
br=pd.DataFrame({'Location_ID':loc.Location_ID.values[i],'uid':ds.uid.values[j],'distance_m':dist[i,j].round(0)})
save(br,'B_LokalizacjaStacja')
# efekt imprezy: sredni stan stacji <=1 km, od -2 h do +3 h wzgledem konca, vs dzien kontrolny (ten sam dzien tyg. +-7 dni bez imprezy w tej lokalizacji)
hs=f.set_index(['uid','date','hour']).avg_bikes
evd=ev[~ev.bad_time&ev.in_data_window&ev.Location_ID.notna()]
busy=set(zip(ev.Location_ID,ev.date))
rows=[]
for _,e in evd.iterrows():
    us=br[br.Location_ID==e.Location_ID].uid.values
    if len(us)==0: continue
    ctrl=None
    for k in (-7,7,-14,14):
        cd=(pd.Timestamp(e.date)+pd.Timedelta(days=k)).date()
        if (e.Location_ID,cd) not in busy and pd.Timestamp('2023-05-06')<=pd.Timestamp(cd)<pd.Timestamp('2023-11-30'): ctrl=k; break
    if ctrl is None: continue
    for rh in range(-2,4):
        tm=e.end.floor('h')+pd.Timedelta(hours=rh); tc=tm+pd.Timedelta(days=ctrl)
        ve=[hs.get((u,tm.date(),tm.hour),np.nan) for u in us]; vc=[hs.get((u,tc.date(),tc.hour),np.nan) for u in us]
        rows.append({'EventID':e.EventID,'rel_hour':rh,'avg_bikes_event':np.nanmean(ve) if np.isfinite(ve).any() else np.nan,
                     'avg_bikes_control':np.nanmean(vc) if np.isfinite(vc).any() else np.nan,'stations':len(us),'control_shift_days':ctrl})
save(pd.DataFrame(rows),'F_ImprezaEfekt')
json.dump(LOG,open(os.path.join(O,'_log.json'),'w'),indent=1,default=str)
print(json.dumps(LOG,indent=1,default=str))
