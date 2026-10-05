# results/

Scored forecasts (`*.jsonl`, one row per model, issue time and lead; git-ignored because of their size), with each run's event list and settings (`*.meta.json`), and cached bootstrap summary (`*.summary.json`).

These are the basis of `docs/REPORT.md`.

| Files | What |
|---|---|
| `benchmark-10min.*` | Main benchmark: full-range scans every 10 minutes, 157 rain episodes, hourly issue times, leads 30 to 180 min, all models; `gwNf` is the whole-map vector averaged from the smoothed and filled block field (report, Appendix B.4). |
| `benchmark-10min-window.*` | History from the last pair up to 2 hours, leads to 6 hours; global vector and pysteps Lucas-Kanade. |
| `check-cadence-10min.*`, `check-cadence-5min.*` | Cadence check: every scan (5 min) against full-range scans only (10 min), on the fixed area both scan types cover, at the same issue times. |
| `cities.*` | Rain in the first and second hour at five Danish cities (3 x 3 cells around each centre), radar against persistence, block matching, the global vector (30 min) and pysteps Lucas-Kanade, at the main benchmark's issue times (`scripts/run_cities.py`). |
| `grid-3.2km.*`, `grid-2km.*`, `grid-1km.*` | The cell-size study (report, Appendix B.2): the benchmark on each grid at the main benchmark's issue times, with FSS also by distance from the nearest radar (`scripts/run_grid_study.sh`, run on a separate machine; the 3.2 km run is identical to `benchmark-10min`). |
| `cities-grid-*.jsonl` | Rain at the five cities on each grid, for the same study. |
| `blocksize-3.2km.*`, `blocksize-2km.*` | The block-size study (report, Appendix B.3): block matching with 13 to 102 km blocks, plain and blended, on the 3.2 and 2 km grids. |
| `motion-coherence.json`, `motion-tracks.jsonl` | How much the rain's motion differs by distance, from pysteps Lucas-Kanade feature tracks (`scripts/motion_coherence.py`). |
| `station-wind.json`, `station-vs-rain.json` | Wind at 68 DMI stations at the issue times (`scripts/fetch_station_wind.py`), and its comparison with the rain's motion (`scripts/station_vs_rain.py`). |
| `climatology.npz`, `climatology.json` | Per-cell wet frequency, mean rain rate, and how often a cell is wet on an almost dry map (fixed echoes), over all full-range scans of the benchmark period (`scripts/climatology.py`). |
| `motion-vectors.jsonl` | The whole-map vector at every issue time, as the model computes it and without its confidence scaling (`scripts/motion_stats.py`). |
| `speed-scaling.*` | The 30-minute whole-map vector sped up by 5, 10 and 15% (report, Appendix B.4). |
| `steps-defaults.*` | STEPS at pysteps' defaults on the main benchmark's issue times (report, section 5.5): `pysteps-steps-bps` (8 members, motion perturbed) and `pysteps-steps-default` (24 members, motion perturbed); the main tables' STEPS has 8 members and no motion perturbation. |
| `robustness.json` | Intervals from resampling rain episodes, calendar days and rainy spells, and every setting chosen on one half of the season and scored on the other (report, sections 6.3 and 6.4; `scripts/robustness.py`, from existing results). |
| `probs.*`, `probs.json` | The main benchmark's methods scored with neighbourhood probabilities (windows of 3 to 25 cells, about 10 to 80 km) and reliability counts (`run_eval.py --neighbourhood`; `scripts/compare_probs.py` writes `probs.json`; report, section 5.5). |
| `era5-vs-rain.json` | The ERA5 wind at 850, 700, 500 and 300 hPa against the rain's tracked motion, per level, and its change with distance (report, Appendix B.3; `scripts/fetch_era5.py` downloads to `data/era5/`, `scripts/era5_vs_rain.py`). |
| `gauges.json`, `radar-vs-gauges.json` | Hourly rain at DMI's rain gauges (`scripts/fetch_gauges.py`), and the radar against them: season ratio, correlation, rainy hours caught, by gauge and by nearest radar (`scripts/radar_vs_gauges.py`; report, Appendix A.4). |
| `explain-checks.json` | Numbers for the three follow-up checks: the Copenhagen fixed echo, the vector's speed, the distance bands (`scripts/explain_checks.py`). |
| `fixed-echo-mask.npy`, `fixed-echo-mask.json` | The fixed-echo mask: cells wet in more than 1% of almost-dry scans, with their neighbours (`scripts/fixed_echo_mask.py`). |
| `vector-speed.json`, `vector-speed.jsonl` | The whole-map vector measured in several ways (the model's, and averaged from the smoothed and filled block field, with each of its steps switched off), on real scans and on a known shift, against the tracked motion (`scripts/vector_speed.py`). |
| `subcell*.jsonl` | Sub-cell block matching (report, Appendices B.4 and A.2): `block-sub`/`gwNsub` refine the blocks that register a whole-cell shift, `block-sub-all`/`gwNsuba` also those whose best whole-cell match is no shift; on the main benchmark's and the cadence check's issue times. |
| `benchmark-clean.jsonl`, `cities-5x5*.jsonl`, `cities-clean.jsonl`, `motion-*-clean.*`, `fixed-echo-check.json` | The benchmark, cities (5 x 5 cells) and whole-map vector with and without the mask (`run_eval.py --region clean`, `run_cities.py --half 2 [--region clean]`, `motion_stats.py N clean`, `scripts/compare_mask.py`). |
| `motion-stats.json` | Speed, direction and steadiness of the whole-map motion vector at every issue time (report, Appendices B.1 and B.4; `scripts/motion_stats.py`). |
| `turning-flow.json` | Issue times rated by how fast the flow changed (ERA5 700 hPa wind, the radar's whole-map vector, 700 hPa vorticity), and the history run re-scored in steady and turning thirds with episode-resampled intervals (report, Appendix B.1; `scripts/turning_flow.py`). |
| `subcell-cities.json` | Sub-cell block matching against whole-cell block matching at the five cities, next hour and the hour after: rainy hours caught, false alarms, CSI with an episode-resampled interval for the difference, rain total (report, Appendix B.4; `scripts/subcell_cities.py`, after `run_cities.py --update block-sub-all`). |
| `local-probs.npz`, `local-probs.json` | A chance of rain at one spot: every cell, every 10-minute step to +2 hours, 0.1 and 0.5 mm/h; persistence, the whole-map vector (alone, over windows growing with lead time, stretched along the motion, with lagged members) and STEPS at its defaults; Brier sums and reliability tables per rain episode, and the summary with every setting chosen on the other half of the season (report, section 5.5 and Appendix C; `scripts/local_probs.py`, `scripts/local_probs_summary.py`). |
| `local-timing.npz`, `local-timing.json` | Timing at one spot as a chance: "rain starts within", "dry for good within", "rain within" 30, 60 and 120 minutes, every cell, 0.1 and 0.5 mm/h; persistence, the whole-map vector (rain or no rain, the largest per-step window chance, a 40-member coherent shift ensemble) and STEPS at its defaults, each also calibrated on the other half of the season (report, section 5.5 and Appendix C; `scripts/local_timing.py`, `scripts/local_timing_summary.py`). |
| `cases.json` | Numbers for the three real cases in the report (`scripts/make_case_figures.py`). |
