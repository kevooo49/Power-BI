# Tabele modelu (dane/model, parquet)

Wszystkie czasy w **Europe/Warsaw** (surowe dane były w UTC). Ziarno faktów: stacja × dzień × godzina.
Wykluczone: 3 stacje (2 testowe + „willowa”), przejazdy z 10–11.10.2023 (artefakt), odjazdy >24 h.

| Tabela | Wiersze | Klucz / kolumny |
|---|---|---|
| D_Stacja | 330 | uid (PK), name, lat, lon, CellID, racks (mediana, NIE pojemność), d_metro_st, d_city_cen, pop_2023, empty_share_6_10, rank_6_10, is_top20 |
| D_Komorka | 31 | CellID (PK), lat, lon (centroid siatki 5 km) |
| D_Lokalizacja | 46 | Location_ID (PK), name, address, lat, lon, coord_rounded |
| F_StanStacji | 1,6 mln | uid, date, hour, slots, empty_slots, over_slots, avg_bikes, min/max_bikes, bikes_first, racks |
| F_Przejazdy | 1,1 mln | uid, date, hour, departures, arrivals |
| F_Pogoda | 130 tys. | CellID, date, hour, temp, precip, wind, cond |
| F_Imprezy | 203 | EventID, date, start, end, participants, type, Location_ID, bad_time, in_data_window |
| B_LokalizacjaStacja | 216 | Location_ID, uid, distance_m (≤1 km) – most M:N |
| F_ImprezaEfekt | 1 110 | EventID, rel_hour (−2..+3 wzgl. końca), avg_bikes_event, avg_bikes_control |
| F_Symulacja | 420 | uid (top 20), extra_bikes 0–20, empty_h_sim, empty_h_actual, stock5_median |
| F_Budzet | 151 | budget 0–150 rowerów, empty_h_sim, reduction_vs_sim0 |
| F_Alokacja | 3 020 | budget, uid, extra_bikes (alokacja zachłanna) |

KPI 1 = SUM(empty_slots)/SUM(slots). Kontrola z raportu etapu 2: rano 6–10 dni rob. 3,86%, top 20: 17,6% (2 035,6 h), 16–20: 11,6%.

Symulacja: odjazdy z danych; gdy stacja była pusta, popyt imputowany Poisson(λ slotu, liczonego z dni, gdy stacja nie była pusta), 30 powtórzeń.
Model zawyża bazę o 17% (2 373 h vs 2 036 h faktycznie), więc wyniki są ostrożne. −30% osiąga budżet 25 rowerów dla top 20.
Skrypty: skrypty/01_extract_snapshots.py → 02_trips.py → 03_build_model.py.
