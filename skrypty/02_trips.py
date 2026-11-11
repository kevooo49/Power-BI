"""Przejazdy: bike_paths.json -> tabela przejazdow w czasie lokalnym (Europe/Warsaw)."""
import orjson, pandas as pd, numpy as np, sys
src, out = sys.argv[1], sys.argv[2]
d = orjson.loads(open(src,'rb').read())
bike=[];fr=[];to=[];dep=[];arr=[]
for b, lst in d.items():
    for t in lst:
        bike.append(int(b)); fr.append(t['from']); to.append(t['to']); dep.append(t['departure_time']); arr.append(t['arrival_time'])
del d
df=pd.DataFrame({'bike':bike,'from':fr,'to':to,'dep':dep,'arr':arr}); del bike,fr,to,dep,arr
for c in ['dep','arr']:
    df[c]=pd.to_datetime(df[c]).dt.tz_localize('UTC').dt.tz_convert('Europe/Warsaw').dt.tz_localize(None)
df['dur_min']=(df.arr-df.dep).dt.total_seconds()/60
df['from_uid']=pd.to_numeric(df['from'],errors='coerce'); df['to_uid']=pd.to_numeric(df['to'],errors='coerce')
df=df.drop(columns=['from','to'])
df.to_parquet(out); print(len(df), df.dep.min(), df.dep.max())
