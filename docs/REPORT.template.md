# Rain nowcasting in Denmark: simple motion models against the state of the art

*Phone apps say "rain in 20 minutes". This report looks at how such short-range forecasts are made from weather radar, and how simple they can be. Tested on six months of Danish radar, 2026-04-01 to 2026-09-23, a simple method gets within a few percent of the state of the art.*

## Summary

**The question.** A rain *nowcast* predicts where it will rain over the next minutes to hours, usually by taking the latest radar images and moving the rain along. This project asks four questions: does moving the rain help, how close do simple methods come to a state-of-the-art system (the open-source library [pysteps](https://pysteps.github.io)), why is a simple method enough over Denmark, and can a single forecast also give an honest chance of rain at one spot?

**How it was tested.** Every method was run as a *hindcast*: pretend it is a moment in the past, give the method only the radar scans up to that moment, forecast, then compare with the scans that followed. This was repeated at {{n:issues}} moments in {{n:units}} rainy periods, with identical inputs for every method, and each forecast was scored from 30 minutes to 3 hours ahead.

**The methods.** Two *simple motion models* were built for this project. Both measure how the rain moved between the latest radar scans and carry it on along that motion: *block matching* gives each square of the map, about 26 km across, its own motion, and the *whole-map vector* moves all the rain with one shared motion. They are compared with three pysteps methods: Lucas-Kanade optical flow, which measures the motion at every point of the map, S-PROG, and the STEPS ensemble, which also gives the chance of rain. The reference is *persistence*: the latest radar picture, unchanged ("nothing moves").

**What was found.**

1. **Moving the rain pays off.** One hour ahead, the simple motion models place rain {{pc:gw4:persistence:60}} to {{pc:bw7:persistence:60}} more accurately than "nothing moves", and pysteps' Lucas-Kanade {{pc:pysteps-lk:persistence:60}}.
2. **The state of the art is ahead, but only a little.** One hour ahead, Lucas-Kanade places rain {{pc:pysteps-lk:bw7:60}} more accurately than the better simple model, block matching, and does better in {{pw:pysteps-lk:bw7:60}} of the rainy periods. Three hours ahead all the methods are level.
3. **Over Denmark, one motion for the whole map is nearly enough.** The two simple models differ by at most about 2% at any lead time: over flat Denmark the rain moves nearly the same way within about 50 km.
4. **Accuracy fades with time.** For every method it roughly halves between 30 minutes and three hours ahead (bottom of the chart): rain that forms or dies, which none of them can forecast, takes over.
5. **One forecast can also give an honest chance of rain.** STEPS gives the best chances, but one ordinary forecast, read with an uncertainty that grows with lead time, comes within a few percent, both for rain at a given moment and for when rain starts or stops at one spot (section 5.5).
6. **The conclusions hold up** in every month, without the radar's known flaws, and with settings chosen on held-out months (section 6).

![Headline comparison](figures/12-headline.svg)

*Reading the chart:* warm colours are the simple motion models built for this project, cool colours the state of the art (pysteps). Top: one hour ahead, how much more accurately each method places rain than "nothing moves". Bottom: spatial accuracy from 30 minutes to 3 hours ahead (1 is perfect), with "nothing moves" dashed.

## 1. What a rain nowcast is

Weather radar scans the sky every few minutes and, after conversion, gives a map of rain rate in millimetres per hour. Over the next hour or two, the best predictor of that map is usually *the same map with the rain moved along*, not a full physics-based weather model, which is too slow and too coarse to track individual showers. Methods that do this are called *extrapolation nowcasts*. They all have two parts:

1. **Measure the motion** of the rain from recent scans.
2. **Move the rain forward** along that motion, one time step at a time.

They cannot predict rain starting, growing, or dying; only movement. The methods compared here differ almost entirely in the first part: how the motion is measured.

**Tested:** "nothing moves" as the reference; the two simple motion models built for this project; and three methods from **pysteps**, a widely used research library. Section 4 describes them.

**Words used.** A few terms recur; all are also in the glossary (Appendix F).

- *Lead time*: how far ahead a forecast looks, "+60 minutes" meaning one hour ahead.
- *Hindcast*: a forecast made for a moment in the past, using only the radar scans up to that moment.
- *Cell*: the radar map is divided into cells of about 3.2 km on each side. A *block* is a square of 8 x 8 cells, about 26 km across.
- *Rain episode*: a rainy period of at most 12 hours; the unit of evidence (section 3.1).
- *Spatial accuracy* (FSS): how well a forecast puts rain in the right place, judged over about 30 km (section 3.2).

## 2. Data

- **Radar.** The composite of DMI's five weather radars covering Denmark, from DMI's open data API: one full-range scan every 10 minutes (Appendix A.1).
- **Period.** 2026-04-01 to 2026-09-23, {{n:days}} days, {{n:fullrange}} scans.
- **Map.** Rain rate in mm/h on cells of about 3.2 km (224 x 160 cells). The map is wider than Denmark so that rain can be tracked in from the sea; scores are computed only over Denmark and its waters, the *scoring area*. Appendix A gives the details.
- **Known flaws.** The radar is an estimate of the rain, not a measurement of it. At a few spots, most clearly at Copenhagen, it shows light rain that never moves, an echo from structures, and its five radars disagree on amounts (Appendices A.3 and A.4). Every method is scored against the same radar, so this favours none of them.

## 3. How the methods are tested

### 3.1 Hindcasts and rain episodes

At each *issue time* a method receives the last few scans (never later ones) and forecasts every 10 minutes ahead; the forecast for +60 minutes is compared with the scan 60 minutes later. Every method sees exactly the same issue times and scans.

Hindcasts are run only while it rains. The rainy hours (rain on at least 2% of the scoring area) are grouped into *rain episodes*: a dry break of less than an hour does not end an episode, an episode shorter than an hour or never covering 5% of the area is left out, and an episode longer than 12 hours is cut into pieces of at most 12 hours. Inside each episode a hindcast is issued every hour: {{n:issues}} hindcasts in {{n:units}} episodes.

![From rainy moments to rain episodes](figures/07-episodes.svg)

Hindcasts from one episode share its weather, so the episode, not the single hindcast, counts as one independent piece of evidence. And because only rainy moments are scored, the results say how well each method moves rain that is already on the map; when the whole map is dry there is nothing to move.

### 3.2 Scores

| Score | What it measures | Better is |
|---|---|---|
| **FSS**, fractions skill score | **Spatial accuracy.**<br>Does the forecast put rain (at least 0.5 mm/h) in the right neighbourhood? For every cell, the share of wet cells within 9 x 9 cells (about 30 km) is compared between forecast and radar, so a shower forecast a few cells off still scores. The report mostly gives it as *how much more accurately* a method places rain than "nothing moves": +35% means an FSS 35% higher. | higher; 1 is perfect |
| **Rain ratio** | **Amount.**<br>Total forecast rain divided by total observed rain. | closest to 1 |
| **Brier score** | **Chance of rain.**<br>Each cell gets a forecast chance of rain, checked against what happened: a 90% chance scores well where it rained and badly where it stayed dry. Given as the improvement over "nothing moves". | higher |

![Why neighbourhood scoring](figures/07-fss.svg)

### 3.3 Uncertainty

Every score comes from a limited sample of rain, {{n:units}} rain episodes, so each is given with a *95% interval*: the range it would very likely fall in with another six months of similar rain. For example, one hour ahead pysteps Lucas-Kanade places rain {{pc:pysteps-lk:persistence:60}} more accurately than "nothing moves", with an interval of {{pci:pysteps-lk:persistence:60}}. When two methods are compared, the interval is for their difference: if it does not include 0, the difference is statistically significant. Appendix D.1 explains how the intervals are made.

## 4. The methods

**What the methods rely on.** Rain is carried by the wind at the height of its clouds. Over Denmark it moves with the wind about 3 km up, typically at {{ms:speed}} km/h toward the east or north-east. That wind changes slowly, typically by {{ms:change1}} km/h in an hour, and over flat Denmark it is nearly the same everywhere within about 50 km (Appendices B.1, B.3 and B.4). So a motion measured on the last few scans can move the rain forward for an hour or more. What no method can foresee is rain forming, growing or dying out on the way.

![Pipeline shared by all extrapolation methods](figures/01-pipeline.svg)

### 4.1 Persistence

The reference: the latest scan, unchanged. A method has skill only if it beats this.

![Persistence](figures/02-persistence.svg)

### 4.2 Block matching, one vector per block

Each 8 x 8-cell block of the older scan (about 26 x 26 km) is searched for in the newer one, up to 6 cells (about 19 km) away in every direction. With scans 10 minutes apart, that covers rain moving at up to about 115 km/h, well above the typical {{ms:speed}} km/h. The shift that fits best is that block's motion, and its confidence is how much better it fits than no shift. Blocks with low confidence borrow from confident neighbours, and empty blocks over dry ground are filled from their neighbours, so rain keeps moving where the measurement ends. Each block's motion is averaged over the scan pairs of the last hour, which calms the noise of single matches (Appendix B.1).

![Block matching](figures/03-block-matching.svg)

**Why 8 x 8 cells.** A block must hold enough rain pattern to be found again in the next scan, and blocks of 4 x 4 cells (13 km) already match unreliably. It must also be small enough that the rain inside it moves the same way. Blocks from 26 to about 100 km score about the same (Appendix B.3); 26 km keeps the most local detail.

### 4.3 The whole-map vector

The whole-map vector starts from the same block matches, but combines them into one motion for the whole map: the average of the blocks' matches, weighted by their confidence, and over the scan pairs of the last 30 minutes. One vector cannot follow rain moving in different directions in different places, as it can around a low-pressure system; but it never pulls neighbouring parts of the rain apart, as differing block vectors sometimes do (Appendix B.5).

In the figure, each arrow on the upper map is one block's vector, drawn inside that block's outline (every other block is shown, over rain only); the lower map shows the single whole-map vector. Arrow lengths are to scale with each other.

![Motion between the two scans ending 4 September 2026, 10:40 UTC: one vector per block, and one for the whole map](figures/10-vectors.svg)

### 4.4 State of the art: pysteps

[pysteps](https://pysteps.github.io) (Pulkkinen et al., 2019) is an open-source library for probabilistic nowcasting, used as a reference in the research literature. Three of its methods were run on the last 4 scans:

- **Lucas-Kanade extrapolation**: a dense motion field, a vector at every point varying smoothly across the map, estimated by tracking small features; the latest scan is moved along it.
- **S-PROG**: the same, plus a model per spatial scale so that fine detail fades faster than broad rain areas: small showers, which change within minutes, fade within the first hour.
- **STEPS**: S-PROG plus random small-scale detail, run as an ensemble of equally likely futures, 8 here (pysteps' default is 24; Appendix C compares the two). It is scored as the ensemble mean, one blurred forecast, and as the share of members with rain, a chance of rain.

![The pysteps methods](figures/09-state-of-the-art.svg)

### 4.5 Moving the rain forward

All the methods move the rain the same way: each forecast cell looks back along the motion, upstream, and copies what the latest scan shows there. The rain keeps its strength; no method here makes rain grow, decay, appear or vanish, and S-PROG and STEPS only smooth small showers away over time. Appendix B.5 shows the procedure, and how differing block vectors can drop rain or copy it twice.

## 5. Results

All the methods use the same issue times, scans, 3.2 km cells and scoring, each at the amount of history that scored best (Appendix B.1). These settings were chosen on the same data they are scored on; chosen on held-out months instead, they change almost nothing (section 6). Finer cells or other block sizes from 26 to about 100 km change the scores below by less than 1% (Appendices B.2 and B.3).

### 5.1 What it looks like: three real cases

Three real cases, one per season, show what the methods do to rain. Each is the hour with the most rain moving fastest on the radar, picked by that rule alone, not by how any method did. Each animation runs through the next two hours in 10-minute steps: top left is the radar, what really happened; the other panels are the forecasts of block matching (latest pair only), the whole-map vector and pysteps Lucas-Kanade. The white outline marks where it *actually* rained 0.5 mm/h or more at that moment: forecast rain inside it is in the right place.

**Spring, {{case:spring:time}}.** The rain moved {{case:spring:obs}}. All three methods move it at nearly the right speed and direction (off by {{case:spring:err:block}}, {{case:spring:err:gw4}} and {{case:spring:err:pysteps-lk}} km/h) and stay close to the outline through the first hour, scoring far above persistence (FSS about {{case:spring:fss:gw4:60}} at +60 minutes, against {{case:spring:fss:persistence:60}}). By the second hour the forecasts hold more rain than the radar shows: this rain was dying, which no method here can represent.

![Spring case: the next two hours](figures/22-case-spring.gif)

**Early summer, {{case:early-summer:time}}.** The rain moved {{case:early-summer:obs}}. The whole-map vector is closest ({{case:early-summer:err:gw4}} km/h off), pysteps {{case:early-summer:err:pysteps-lk}} and block matching {{case:early-summer:err:block}} km/h. Block matching's rain breaks up where neighbouring blocks disagree and thins out (its rain total is {{case:early-summer:ratio:block:60}} of the observed at +60 minutes), although its FSS ({{case:early-summer:fss:block:60}}) stays close to the others'.

![Early-summer case: the next two hours](figures/22-case-early-summer.gif)

**Late summer, {{case:late-summer:time}}.** The rain moved {{case:late-summer:obs}}. All three methods keep pace with it (off by {{case:late-summer:err:block}}, {{case:late-summer:err:gw4}} and {{case:late-summer:err:pysteps-lk}} km/h), and pysteps places it best (FSS {{case:late-summer:fss:pysteps-lk:60}} at +60 minutes, against {{case:late-summer:fss:block:60}} for block matching and {{case:late-summer:fss:gw4:60}} for the whole-map vector). In the second hour the rain faded fast: at +120 minutes every forecast holds three to five times the rain the radar shows, and even persistence {{case:late-summer:ratio:persistence:120}} times. Moving the rain correctly does not help when the rain itself is going away.

![Late-summer case: the next two hours](figures/22-case-late-summer.gif)

### 5.2 Does moving the rain help, and how close are simple methods?

One hour ahead, over all {{n:units}} rain episodes:

{{table:headline}}

- **Moving the rain pays off** for every method, by {{pc:gw4:persistence:60}} to {{pc:pysteps-lk:persistence:60}} one hour ahead.
- **pysteps Lucas-Kanade leads up to two hours,** by {{pc:pysteps-lk:bw7:60}} over block matching and {{pc:pysteps-lk:gw4:60}} over the whole-map vector one hour ahead, both statistically significant. By three hours ahead the difference is gone. Its lead does not come from measuring motion more finely than a cell (Appendix B.4); its dense, smoothly varying motion field is the likely reason.
- **S-PROG and the STEPS ensemble mean** place rain a little less well than plain Lucas-Kanade: they deliberately blur small detail as the forecast ages.
- **Beyond three hours little skill is left,** for any method (Appendix B.1).

The scores at every lead time, and the methods compared pair by pair, are in Appendix D.5.

### 5.3 Block matching or one vector for the whole map?

The two simple methods are close at every lead time. Block matching is slightly ahead from one hour on, by {{pc:bw7:gw4:60}} at +60 minutes, but it also forecasts more rain ({{r:bw7:60}} of the observed one hour ahead, against {{r:gw4:60}}): where neighbouring block vectors disagree, rain is dropped or copied twice, and the copies win (Appendix B.5). That one vector does nearly as well follows from the rain moving nearly the same way within about 50 km (section 4).

Two design details mattered about as much as the choice between the two methods: averaging each block's motion over the last hour instead of the latest pair of scans gains block matching {{pc:bw7:block:60}} (Appendix B.1), and building the whole-map vector from the blocks' own matches, before the borrowing and filling, gains it {{pc:gw4:gw4f:60}} (Appendix B.4).

### 5.4 Is the amount of rain right?

Forecast rain divided by observed rain, one value per rain episode. Each box holds the middle half of the episodes, the white line is the median, and the whiskers reach from the 10th to the 90th percentile.

![Rain amount](figures/13-rain-total.svg)

- **Most methods forecast slightly too much rain** ({{r:gw4:60}} to {{r:bw7:60}} of the observed at +60 minutes), and more so further ahead: moving the rain along keeps dying rain at full strength.
- **The STEPS ensemble mean forecasts too little** ({{r:pysteps-steps-mean:60}} at +60 minutes, {{r:pysteps-steps-mean:180}} at +3 hours): averaging members that disagree about where the rain is spreads it into weak drizzle that no longer counts as rain.

### 5.5 The chance of rain

A forecast that only says "rain" or "no rain" in each cell can be turned into a chance. Here this is done with a simple probability model: the forecast is copied 40 times, each copy shifted by a random offset that grows by about one kilometre for every three minutes ahead and keeps its direction, so that each copy is one consistent alternative future; the chance of rain is the share of copies with rain (Appendix C). The STEPS ensemble gives chances directly. Scored in every cell and at every 10-minute step, as for a person at one place, and with STEPS calibrated on the other half of the season:

![The chance of rain at one spot](figures/28-local-chance.svg)

- **One forecast comes close to STEPS.** The model's improvement over "nothing moves" is {{lp:0.5:gw_grow:60:imp}} at +60 minutes against {{lp:0.5:steps_grow_cal:60:imp}} for STEPS, and level at +2 hours ({{lp:0.5:gw_grow:120:imp}} against {{lp:0.5:steps_grow_cal:120:imp}}). Read as plain rain or no rain, the same forecast reaches only {{lp:0.5:gw:60:imp}}.
- **The same holds for timing.** For statements like "rain starts here within an hour", the model reaches {{lt:0.5:start:60:gw_shift:pct}} of STEPS' improvement, and {{lt:0.5:start:120:gw_shift:pct}} within two hours; plain rain or no rain reaches about half.
- **STEPS' chances are a little more honest at the top:** when STEPS says 85%, it rains about {{pb:reliability.pysteps-steps-default-mean_rel_n5_at_60.o.8:pct}} of the time; for chances read from single forecasts, about {{pb:reliability.gw4_rel_n15_at_60.o.8:pct}} to {{pb:reliability.pysteps-lk_rel_n15_at_60.o.8:pct}}.

### 5.6 Rain at Danish cities

The scores so far are for the whole map. A reader more often wants to know: *will it rain here in the next hour?* Each forecast was read out at five cities (Copenhagen, Aarhus, Odense, Aalborg and Esbjerg), averaged over about 10 x 10 km around the centre and added up over the next hour, and compared with the radar's own amount: {{city:hours}} city-hours per method, of which {{city:wet}} had at least 0.5 mm of rain.

![The five cities](figures/20-cities.svg)

*Rainy hours caught* is the share of the rainy hours that the forecast also called rainy; *false alarms* the share of forecast rainy hours that stayed drier; the *CSI* (critical success index) combines the two, 1 being perfect.

{{table:cities}}

- **Moving the rain clearly helps at a single place.** The three motion methods catch {{cpod:gw4:1}} to {{cpod:pysteps-lk:1}} of rainy hours, against {{cpod:persistence:1}} for "nothing moves", with fewer false alarms ({{cfar:pysteps-lk:1}} to {{cfar:bw7:1}} against {{cfar:persistence:1}}).
- **The three motion methods are close:** pysteps has the best CSI, but within the intervals of the other two, and the order changes from city to city. The second hour is much harder: about half of the rainy hours are caught (Appendix D.5).
- **The motion methods seem to forecast too little rain** (rain total ratio {{cratio:gw4:1}} to {{cratio:bw7:1}}, against {{cratio:persistence:1}} for persistence). This is almost entirely Copenhagen, where the radar shows a fixed echo, rain that stays put, which persistence keeps and the moving methods carry away (Appendix A.3).

## 6. Robustness checks

- **Season.** Every method gains in every month, least in April and May, when "nothing moves" already scores high; pysteps leads in every month (Appendix D.2).
- **Radar flaws.** Leaving out the cells with fixed echoes changes every map-wide score by less than 0.005 and leaves the order of the methods unchanged (Appendix A.3).
- **Related rain episodes.** Resampling whole days or rainy spells instead of episodes widens the intervals by a median of {{rb:summary.median_wider_spell:pct}} and changes no conclusion (Appendix D.3).
- **Settings chosen on the same data.** Chosen on April to June and scored on July to September, and the other way round, the settings hardly change, and pysteps stays significantly ahead of both simple methods on either half (Appendix D.4).

![FSS gain over persistence by month, +60 minutes](figures/14-by-month.svg)

## 7. Conclusions

### 7.1 What was learned

- **Moving the rain is clearly worth it for the first two hours.** One hour ahead, every motion method places rain {{pc:gw4:persistence:60}} to {{pc:pysteps-lk:persistence:60}} more accurately than "nothing moves", and at a single place it catches {{cpod:gw4:1}} to {{cpod:pysteps-lk:1}} of the rainy hours instead of {{cpod:persistence:1}}.
- **The state of the art leads, but by little and not for long:** {{pc:pysteps-lk:bw7:60}} one hour ahead, nothing significant three hours ahead. Its smooth, dense motion field is the likely reason.
- **Over Denmark, one motion for the whole map is nearly enough,** because the wind that carries the rain is nearly the same within about 50 km. For a simple method, the details of how the motion is measured matter about as much as the choice of method.
- **The limit is rain that forms or dies, not motion.** Accuracy roughly halves within three hours for every method, and moving rain keeps dying rain at full strength.
- **One forecast can give an honest chance of rain.** Read with an uncertainty that grows by about a kilometre every three minutes, it comes within a few percent of the STEPS ensemble, also for when rain starts or stops at one spot.

**In practice:** for a nowcast at one place in Denmark over the next hour or two, a simple motion model with 30 to 60 minutes of history, plus a growing uncertainty, delivers most of what the state of the art does, with far simpler code. pysteps is worth its extra machinery for the best placement in the first two hours.

### 7.2 What cannot be concluded

- **Denmark only.** The numbers, and the sizes that worked best, depend on Denmark: flat land, sea on almost every side, and a mostly westerly flow. In mountains the terrain can hold rain in place: over Switzerland, tracked radar patterns moved more slowly than the rain's motion measured by Doppler radar, possibly because rain keeps forming on windward slopes, and possibly because ground echoes and the mountains' shadow on the radar beam disturb the tracking ([Li, Schmid and Joss, 1995](https://doi.org/10.1175/1520-0450%281995%29034%3C1286:NOMAGO%3E2.0.CO;2)). There, a single motion vector could do much worse than here.
- **One season.** The archive is April to September; nothing here speaks for winter, snow or autumn storms. DMI's open API keeps only about the last 180 days.
- **No weather types.** Rain was not classified by weather type; rapidly changing flow was tested only for the amount of history (Appendix B.1).
- **One rain threshold,** 0.5 mm/h. Heavier rain (5 mm/h and above) is too rare here to score. FSS at a fixed threshold also slightly rewards forecasting too much rain; read it together with the rain ratio.
- **pysteps at its defaults, not tuned.** Tuned, pysteps might do better; so might the simple methods.
- **The radar is not perfect truth:** one conversion from radar echo to rain, no gauge calibration, some fixed echoes, and regional errors of up to a factor of two against rain gauges (Appendix A.4).
- **Not tested:** numerical weather prediction (DMI's HARMONIE model gives hourly steps a few times a day, too coarse for nowcasting, and its open API rarely answered) and deep-learning nowcasters, which have no pretrained weights for Danish radar and need far more than six months of data to train.

## 8. Open questions

- **Growth and decay.** The main limit after the first hour: none of the methods can predict a shower forming, growing or dying.
- **What sets pysteps apart?** Its dense, smoothly varying motion field is the main candidate; blending block vectors between block centres (Appendix B.3) tests only part of that.
- **A 2 km grid.** It helps pysteps and block matching when rain placement is judged over about 10 km, at about five times the cost (Appendix B.2).
- **Fronts, lows and weather types.** Where the flow turns quickly a long history lags a little (Appendix B.1); whether smaller blocks help there is open. Classifying rain by weather type would also explain the spring behaviour (section 6).
- **Scoring at single places** against DMI's rain gauges instead of the radar, which is closer to what one person experiences.
- **Winter and heavy rain.** The archive grows every night: winter from about March 2027, and with it enough heavy rain to score on its own.

## Appendix A. The radar data

**Details of the data.**

- **Source.** The composite radar product from the DMI Open Data API (`opendataapi.dmi.dk`, no key required; see DMI's terms of use for reuse): ODIM HDF5 files on a 500 m grid.
- **The radars.** Five C-band weather radars (Rømø, Sindal, Samsø, Stevns and Bornholm) with a 1° beam and 500 m range resolution, each scanning from 0.5° to 15° elevation out to 240 km. The composite combines them into one picture; where radars overlap, the highest value is kept ([DMI radar documentation](https://www.dmi.dk/friedata/dokumentation/radar-data); beam and range figures from [Schleiss et al., 2020, *Hydrology and Earth System Sciences* 24, 3157-3188](https://doi.org/10.5194/hess-24-3157-2020)).
- **Period.** 2026-04-01 to 2026-09-23, {{n:days}} days, {{n:scans}} scans of both types (A.1); {{n:fullrange}} full-range scans are used.
- **Conversion.** Radar reflectivity is converted to rain rate in mm/h with the Marshall-Palmer relation stored in each file (Z = 200 R^1.6), values under 0.05 mm/h are set to zero, and the scan is averaged onto a 224 x 160 grid (cells of about 3.2 km on each side near 56 N) covering 5.0 to 16.5 E and 53.9 to 58.5 N. Pixels flagged as *no data* stay missing; a grid cell is missing if less than half of it has data.
- **Scoring area.** Denmark and its waters (8.0 to 15.3 E, 54.3 to 58.0 N), and only the cells the radar actually covered (96% of that box).

### A.1 Full-range and doppler scans

DMI's composite alternates two products, which the API labels with `scanType`:

- **full range**, at minutes divisible by 10 (:00, :10, ...): {{n:fullrange}} scans in the archive. Each radar sees out to 240 km; no data over 46% of the raster, the far corners beyond that range.
- **doppler**, in between (:05, :15, ...): {{n:doppler}} scans. Scans made for measuring wind (radial velocity), reaching only 120 km; no data over 79% of the raster.

The label matches the minute for every one of the 50,619 scans the API listed for the period. Beyond the doppler scans' reach, only the full-range scans see anything:

![The two kinds of DMI scan, five minutes apart on 4 September 2026; grey: no radar data](figures/16-scan-types.svg)

Reading the doppler scans' missing area as "no rain" makes every other frame lose the rain far from the radars. A motion estimate between a full and a doppler scan then mostly measures that change in coverage. **This benchmark uses the full-range scans only**, which gives one scan every 10 minutes. A.2 tests whether the 5-minute spacing would help if the coverage problem is set aside.

### A.2 Scans 5 or 10 minutes apart?

Using only the full-range scans also doubles the gap between the scans a method compares, which could help or hurt on its own. To separate the two, both kinds of scan were restricted to the area *both* cover (37% of the grid, 56% of the scoring box), set to "no radar" everywhere else in every frame, and the methods were run on all scans (5 minutes apart) and on the full-range scans only (10 minutes apart), at the same {{n:cadence_issues}} issue times. Rain moving out of this smaller area is lost and none comes in, so the rain ratios are below 1 and the gains are lower than elsewhere in this report: compare the two scan spacings with each other, not these numbers with the rest of the report.

![Scan spacing](figures/17-cadence.svg)

- **The simple methods are much worse with scans 5 minutes apart** when they use only the latest pair. Block matching falls from {{d@c10:block:60}} to {{d@c5:block:60}} and over-forecasts rain ({{r@c5:block:60}} of the observed total); a whole-map vector from one pair falls from {{d@c10:gw2:60}} to {{d@c5:gw2:60}}. Averaging an hour of 5-minute pairs recovers most of the loss, for block matching ({{d@c5:bw13:60}}, rain ratio {{r@c5:bw13:60}}) and for the whole-map vector ({{d@c5:gw13:60}}), but not all.
- **pysteps is almost unaffected** ({{d@c10:pysteps-lk:60}} against {{d@c5:pysteps-lk7:60}}).
- **Why.** Rain moves about one grid cell in 5 minutes, so a whole-cell match between two scans that close rounds a large share of the motion away. But rounding is not the main cause: refining each block's match to a fraction of a cell (Appendix B.4) recovers only {{pr:subcell-all-cadence-5min+check-cadence-5min:block-sub-all:block:60}} for block matching, while averaging each block over an hour of pairs recovers {{pd@c5:bw13:block:60}}. Single matches between scans 5 minutes apart are noisy, because the rain moves little compared with how much it changes shape, and neighbouring blocks that disagree copy rain twice.

So for block matching the gap between the matched scans matters, and so does averaging several pairs when the gap is short. With 10-minute scans, more history gains only a little (Appendix B.1).

### A.3 Fixed echoes

Some places show rain on the radar far more often than rain allows: *fixed echoes*, from tall structures or wind turbines, or from the beam catching the ground. They were found by how often each cell is wet (0.5 mm/h or more) in the scans in which almost the whole map is dry. Over the scoring area the median is {{fe:copenhagen_ring.box_median:pct2}} of such scans, and 99% of cells stay below {{ex:copenhagen.box_wet_on_dry_map_p99:pct2}}. One cell at Copenhagen is wet in {{ex:copenhagen.wet_on_dry_map_max:pct1}} of them, and over the whole archive the Copenhagen area averages {{ex:copenhagen.mean_rate:2f}} mm/h against {{ex:copenhagen.mean_rate_around:2f}} mm/h around it. Offshore wind farms in the southern Baltic show the same signature. The source of the Copenhagen echo was not identified.

A fixed echo stays put: persistence keeps it, and a method that moves the rain carries it away, so near an echo the moving methods seem to forecast too little rain (section 5.6).

**Masking them.** Cells wet in more than 1% of the almost-dry scans, and the ring of cells around each, were treated as having no radar data, in the inputs and in the scoring: {{fe:mask.masked_in_box:0f}} cells, {{fe:mask.masked_in_box_share:pct2}} of the scoring area. Every map-wide score (section 5.2) changes by less than 0.005, and the order of the methods does not change.

**At Copenhagen.** The usual 3 x 3 city area lies entirely inside the mask, so the check uses 5 x 5 cells (about 16 km) with and without it. The rain ratio of block matching goes from {{fe:cities_before.Copenhagen.block.ratio:2f}} to {{fe:cities_after.Copenhagen.block.ratio:2f}}, but that of the whole-map vector only from {{fe:cities_before.Copenhagen.gw4.ratio:2f}} to {{fe:cities_after.Copenhagen.gw4.ratio:2f}}, and of pysteps Lucas-Kanade from {{fe:cities_before.Copenhagen.pysteps-lk.ratio:2f}} to {{fe:cities_after.Copenhagen.pysteps-lk.ratio:2f}}. The cells left around the core still carry a weaker echo, wet in {{fe:copenhagen_ring.median:pct2}} of the almost-dry scans (median). A threshold low enough to catch it (0.5%) masks {{fe:sweep.t5.copenhagen_5x5_masked:0f}} of the 25 cells, so Copenhagen cannot be verified cleanly from this radar product. The rest of the report uses the unmasked data.

### A.4 Radar against rain gauges

DMI's weather stations also measure rain, in mm per hour. For every gauge and hour of the archive, the gauge's rain was set against the radar's in the gauge's 3.2 km grid cell, averaged over the six full-range scans of that hour (`scripts/fetch_gauges.py`, `scripts/radar_vs_gauges.py`). Two of the {{rg:gauges_total:0f}} gauges were left out as faulty, by a check that does not use the radar: their season total was less than half that of their three nearest neighbours. That leaves {{rg:all.cell.hours:,}} gauge-hours. A rainy hour is one with at least 0.5 mm.

{{table:gauges}}

![Radar against rain gauges; triangles are the radars](figures/23-gauges.svg)

- **Over the season the radar reads {{rg:all.cell.ratio:2f}} times the gauge rain.** Part of that is the gauges: in wind they typically catch 2 to 10% too little rain (Sevruk, 1982; for Danish gauges, Allerup, Madsen and Vejen, 1997).
- **The radars disagree with each other.** Near Rømø and Bornholm radar and gauges agree; around Sindal, in the north, the radar sees little more than half the gauge rain, and around Stevns, on Zealand, about half as much again. Calibration differences between the radars are the likely cause, possibly helped by the composite keeping the highest value where radars overlap; neither was tested.
- **Hour by hour the agreement is moderate** (correlation {{rg:all.cell.corr:2f}}): a gauge catches rain on a few hundred square centimetres, the radar averages over about 10 square kilometres, and a shower can fall on one and not the other.
- **The gauges cannot confirm the fixed echo at Copenhagen:** no gauge sits in it. The nearest, at Kastrup airport about 6 km away, reads like its neighbours.

For this benchmark the errors are the same for every method, so the comparisons of section 5 stand. They do mean that the 0.5 mm/h threshold catches less real rain in the north than on Zealand.

## Appendix B. Method studies

Four parts of the simple methods are tested here: how much history they use (B.1), the size of the grid cells the radar is averaged onto (B.2), the size of the blocks that are matched between scans (B.3), and how the motion is measured from the matches (B.4). Outside B.1, block matching uses the latest pair of scans.

### B.1 How much history

**How several scans are used.** How far back a method looks is its *history*, counted in scans 10 minutes apart: the latest pair covers 10 minutes, 4 scans 30 minutes, 7 scans an hour. The last *n* scans form *n* − 1 pairs (scans 1 and 2, scans 2 and 3, and so on), each matched on its own. The whole-map vector is first made for each pair, across the whole map; these pair vectors are then averaged with equal weight. Block matching averages each block's vector over the pairs, weighted by how well each pair matched, and only then applies the neighbour borrowing and filling. Either way, averaging several pairs averages out their separate measurement errors:

![Averaging several scan pairs](figures/08-motion-window.svg)

**Why more history can help.** The flow that carries rain changes slowly. Over North America, [Germann, Zawadzki and Turner (2006)](https://doi.org/10.1175/JAS3735.1) found that most of the loss of predictability of radar rain patterns comes from rain growing and decaying; changes in the motion itself played a small, though not negligible, part. The data here agree: one hour later the whole-map vector has typically changed by {{ms:change1}} km/h, and three hours later by {{ms:change3}} km/h, against a typical speed of {{ms:speed}} km/h, and part of that change is measurement noise (`results/motion-stats.json`). So the scan pairs of the last half hour or hour mostly measure the same motion, each with its own error, and one motion measured now can be used for hours ahead.

Both simple methods were run with every window from the latest pair up to 13 scans (two hours), the whole-map vector also with recent pairs weighted more, and pysteps Lucas-Kanade on 4, 7 and 13 scans, out to 6 hours ahead (the pairs are combined as described above). This is a separate run that needs two hours of history, so its persistence row differs slightly from section 5.2. FSS gain over persistence:

{{table:windows}}

![Window length](figures/15-windows.svg)

- **Block matching gains a little from more history.** An hour of scan pairs over the latest pair alone gains {{pd:bw7:block:30}} at +30 minutes and {{pd:bw7:block:60}} at +60, and nothing clear by +2 hours ({{pd:bw7:block:120}}). Each block's vector comes from a single 26 km patch, so it is noisy, and averaging several pairs calms it. Its excess rain hardly changes ({{r:bw7:60}} against {{r:block:60}} at +60 minutes). Two hours adds a little more at +60 minutes ({{pd@window:bw13:bw7:60}}) but loses at 6 hours ({{pd@window:bw13:bw7:360}}).
- **For the whole-map vector, about 30 minutes is best, and the differences are small.** 30 minutes over the latest pair gains {{pd:gw4:gw2:60}} at +60 minutes: one pair is already an average over hundreds of blocks. Longer windows lose a little, more at longer leads: an hour instead of 30 minutes changes the gain by {{pd:gw7:gw4:180}} at +180 minutes, two hours instead of one by {{pd@window:gw13:gw7:180}}.
- **Weighting recent pairs more helps only over long windows:** over two hours of history, a weighting that halves the influence of a pair every 30 minutes beats the plain average by {{pd@window:gwx3:gw13:180}} at +180 minutes, but it does not beat a plain 30-minute average.
- **pysteps Lucas-Kanade does not depend on history** ({{d:pysteps-lk:60}} with 30 minutes, {{d:pysteps-lk7:60}} with an hour).
- **With scans 5 minutes apart, history matters far more** (Appendix A.2).

**Does history lag where the flow turns?** An average over past scans should lag behind when the flow changes quickly, at a front or around a low. To test this, every issue time was rated by how much the wind about 3 km up (the 700 hPa pressure level), which is the wind that carries the rain over Denmark (Appendix B.3), changed over the next hour. The wind comes from the ERA5 reanalysis, averaged over the scoring area, so the rating does not depend on the radar. The history run was then scored again in the third of issue times where that wind changed least (median {{tf:ratings.era5.median.steady:0f}} km/h) and the third where it changed most (median {{tf:ratings.era5.median.turning:0f}} km/h), with no new forecasts (`scripts/turning_flow.py`). The figure shows, for each amount of history, how much better (above 0) or worse (below 0) it scores than the history section 5 uses (dashed line), in steady and in turning flow:

![History in steady and turning flow](figures/27-turning-flow.svg)

- **When the flow turns, older scans mislead.** They measured a motion that has since changed. So for the whole-map vector, two hours of history instead of 30 minutes scores {{tfa:era5:gw13:gw4:turning:180}} lower at +3 hours in turning flow, but only {{tfa:era5:gw13:gw4:steady:180}} lower in steady flow. And for block matching, an hour of history instead of the latest pair alone scores {{tfa:era5:bw7:bw2:steady:60}} higher at +60 minutes in steady flow, but only {{tfa:era5:bw7:bw2:turning:60}} higher in turning flow.
- **The best history moves a little shorter, but the effects are small.** In turning flow at +3 hours, block matching does best with 30 minutes instead of an hour ({{tfg:era5:bw4:bw7:turning:180}}), and the whole-map vector with 20 minutes instead of 30 ({{tfg:era5:gw3:gw4:turning:180}}); at +60 minutes the histories of section 5 stay at or close to the best, and the latest pair alone is never the best. All these differences are about 0.01 or less, smaller than the gaps between the methods, so the settings of section 5 hold.
- **Two other ways of finding turning flow mostly agree:** the change of the rain's own motion on the radar over the next hour, and how strongly that wind changes direction from place to place across the map, as it does around lows and across fronts. Both show the same pattern for the whole-map vector and Lucas-Kanade; for block matching only the curvature does.

**In short:** the best history is about an hour for block matching and about 30 minutes for the whole-map vector and pysteps Lucas-Kanade. Section 5 uses these. They were chosen on the same data they are reported on (section 5), but choices made on one half of the season hold up on the other (Appendix D.4).

### B.2 Cell size

**Set-up.** DMI's composite has 500 m pixels; the rest of this report averages them onto 3.2 km cells. For this study the archive was rebuilt from the same raw files on two finer grids, 2 km (358 x 256 cells) and 1 km (717 x 512), keeping only the full-range scans. Everything else that is counted in cells was kept fixed in kilometres, so only the resolution changes: blocks of about 26 km (8, 13 and 26 cells), a search radius of about 19 km (6, 10 and 19 cells; rain up to about 115 km/h with scans 10 minutes apart), and the FSS neighbourhoods of about 30 km (9, 15 and 29 cells) and 10 km (3, 5 and 9 cells). All three grids were scored at the same {{n:issues}} issue times as section 5, for persistence, block matching, the whole-map vector and pysteps Lucas-Kanade, each against persistence on its own grid, so a finer grid is not credited merely for resolving the radar more finely. Rerun on the 3.2 km grid, every score is identical to section 5.

FSS gain over persistence at +60 minutes, judged over about 30 km, as in section 5:

{{table:grid30}}

The same, judged over about 10 km:

{{table:grid10}}

![FSS gain against cell size](figures/18-grid.svg)

The 1 km grid minus the 3.2 km grid at other lead times, judged over about 10 km:

{{table:gridleads}}

By distance from the nearest radar (judged over about 30 km, +60 minutes):

{{table:gridbands}}

Rain at the five cities of section 5.5, CSI for the next hour (the city area is about 10 x 10 km on every grid):

{{table:gridcities}}

- **Over 30 km, cell size hardly matters.** The changes are below 0.01 for every method, which is why the choice of grid does not affect the conclusions of section 5.
- **Judged over 10 km, a finer grid helps the methods that track local detail.** At +60 minutes, 1 km improves pysteps Lucas-Kanade by {{gd:pysteps-lk:60:10:1km}} (better in {{gw:pysteps-lk:60:10:1km}} of rain episodes) and block matching by {{gd:block:60:10:1km}}. Most of it comes with the first step: 2 km already gives pysteps {{gd:pysteps-lk:60:10:2km}}.
- **The whole-map vector gains nothing, and even loses a little** ({{gd:gw4:60:10:1km}}): a single vector has no local detail to benefit from finer cells.
- **At the cities the gain goes to pysteps.** Its CSI for rain in the next hour rises from {{gc:pysteps-lk:3.2km}} on the 3.2 km grid to {{gc:pysteps-lk:1km}} on 1 km; block matching ({{gc:block:3.2km}} to {{gc:block:1km}}) and the whole-map vector ({{gc:gw4:3.2km}} to {{gc:gw4:1km}}) change little.
- **The gain is not where the radar beam predicts.** The beam is narrow near the radars (section 2), so finer cells were expected to add most there. Instead pysteps gains most far from them ({{gd:pysteps-lk:60:far:1km}} beyond 120 km, against {{gd:pysteps-lk:60:near:1km}} within 60 km). The far band is different ground. It is mostly land ({{ex:bands.far.sea:pct}} sea, against {{ex:bands.near.sea:pct}} near the radars), at the edges of the scoring area in Sweden and Germany. The radar sees rain there less often (wet in {{ex:bands.far.wet_freq:3f}} of scans against {{ex:bands.near.wet_freq:3f}}), and the detected rain is patchier ({{ex:bands.far.tracks_per_1000_cells:1f}} trackable features per 1,000 cells against {{ex:bands.near.tracks_per_1000_cells:1f}}), as expected where the beam passes over shallow rain. A plausible explanation, not tested, is that with sparse, patchy rain small placement errors weigh more, so the finer placement a 1 km grid gives pysteps pays off most there.
- **Cost.** On a 14-core machine the benchmark took about 3 minutes on the 3.2 km grid, 15 minutes on 2 km and 3 hours 40 minutes on 1 km, where each block-matching step searches ten times as many cells over a ten times larger window. The archive of full-range scans is about 9 GB at 2 km and 35 GB at 1 km.

**In short:** for forecasts judged at the scale of a town, a 2 km grid is worth having for pysteps and block matching; 1 km adds a little more at a large cost; for the headline comparisons of this report the grid does not matter.

### B.3 Block size

Block matching measures one vector per 8 x 8-cell block (about 26 km). A block should be about as large as the area over which the rain moves the same way: smaller, and each vector is noisier and neighbours disagree; larger, and real differences in motion are averaged away. Denmark favours large areas: its highest point is 170.86 m (Møllehøj, measured by the Danish Geodata Agency in 2005, as reported by [Wikipedia](https://en.wikipedia.org/wiki/M%C3%B8lleh%C3%B8j)), and no place in the country is more than about 52 km from the sea ([VisitDenmark](https://www.visitdenmark.com/faq/geography)). With no mountains to block, lift or channel the flow, the wind that carries rain should change only gradually across the country. This study measures that area first, then tests block sizes against it.

**How far does the rain move the same way?** At every issue time, individual rain features were tracked over the last 30 minutes with pysteps' Lucas-Kanade method, using its raw tracks before any interpolation, about 250 per issue time inside the scoring area. For every pair of tracks, the difference in their motion was recorded against the distance between them. (Small matched blocks cannot be used for this: at this resolution their whole-cell matches scatter by tens of km/h.) Tracks a few kilometres apart differ by about {{coh:5}} km/h, which is measurement noise; the difference grows to {{coh:45}} km/h at 45 km, {{coh:85}} km/h at 85 km, {{coh:145}} km/h at 145 km and {{coh:245}} km/h at 245 km, against a typical speed of {{ms:speed}} km/h. There is no distance at which the motion suddenly stops agreeing: it changes gradually across the map. Within about 50 km it is uniform to within the noise; across the country it differs by more than half the typical speed. The three seasons of the archive give nearly the same curve.

**Do ground stations show the same?** DMI's open observation data give 10-minute mean winds at 68 Danish stations. At the issue times their wind has a median speed of only {{sv:speed}} km/h, {{sv:ratio}} of the rain's own speed measured within 25 km of each station, and its direction is turned anticlockwise from the rain's by a median of {{sv:turn}} degrees (half of the cases between {{sv:turnq}} degrees; only {{sv:within30}} within 30 degrees), over {{sv:pairs}} station-hours. This is the effect of friction near the ground, which slows the wind and turns it with height ([Lindvall and Svensson, 2019](https://doi.org/10.1002/qj.3605)). The station winds also disagree strongly over short distances: stations about 10 km apart already differ by {{stc:10}} km/h, near their typical speed, because local surroundings dominate the wind at the ground. So ground stations cannot measure the scale that matters for moving rain.

**And the wind at cloud height?** Rain is carried by the wind at the height of the clouds that produce it. For convective storms the drift of existing cells is usually taken to be the mean wind of the *cloud layer*, between the 850 and 300 hPa pressure levels, roughly 1.5 to 9 km up ([Corfidi, 2003](https://doi.org/10.1175/1520-0434%282003%29018%3C0997:CPAMPF%3E2.0.CO;2)). The rain pattern as a whole can still move somewhat differently, because storms also *propagate*: new cells form on one side as old ones decay on the other ([Corfidi, 2003](https://doi.org/10.1175/1520-0434%282003%29018%3C0997:CPAMPF%3E2.0.CO;2)). The ERA5 reanalysis (Copernicus Climate Data Store; hourly, on a 0.25° grid) gives the wind at 850, 700, 500 and 300 hPa, from about 1.5 to 9 km up. Interpolated to each tracked rain feature's place and time (`scripts/era5_vs_rain.py`), it agrees with the rain's motion far better than the ground stations do, and best at 700 hPa, about 3 km up:

{{table:era5}}

At 700 hPa the wind moves at {{e5:track.700.speed_ratio.median:2f}} of the rain's speed, in the same direction to within a few degrees. It also changes with distance much as the rain's motion does (figure below): two places about 50 km apart differ by about {{e5:structure.700.rms_kmh.2:0f}} km/h, and about 250 km apart by {{e5:structure.700.rms_kmh.12:0f}} km/h, against {{coh:45}} and {{coh:245}} km/h for the rain tracks. So the wind aloft confirms, independently of the radar, that the motion is nearly uniform over about 50 km. ERA5 is smoother than the real wind and cannot show differences over less than about 30 km. It is also built after the fact, so it shows what carries the rain, not a forecast a nowcast could use in real time.

![Motion difference by distance, and skill by block size](figures/19-blocksize.svg)

**Which block size forecasts best?** Block matching was run with blocks of about 13, 26, 51 and 102 km, each as a plain per-block field and as a field blended smoothly between block centres, at the same issue times as section 5. On the 3.2 km grid (FSS gain over persistence, about 30 km, +60 minutes; differences paired against the 26 km blocks used in the rest of the report):

{{table:blocksize32}}

- **13 km blocks are clearly worse** ({{bsd:block-13km:60:3.2km}}): they hold too little rain pattern for a reliable match (the 2 km results below show that it is the small area, not the few cells).
- **From 26 to 102 km, and up to one vector for the whole map, the differences are small** (within about 0.01). Larger blocks forecast less excess rain at long lead times.
- **Blending between block centres hurts small blocks**, where it spreads the noise of each vector across its neighbours, and makes no clear difference for large ones ({{bsd:block-smooth-102km:60:3.2km}} at 102 km).

This matches the tracked motion: the rain moves nearly uniformly within about 50 km, so blocks of 26 to 100 km all capture it, and smaller blocks only add noise.

**On the 2 km grid**, where a 13 km block has 6 cells instead of 4, the picture is the same:

{{table:blocksize2}}

The 13 km blocks are still clearly worse ({{bsd:block-13km:60:2km}}), so the problem is the small area rather than the few cells: a 13 km patch of rain holds too little structure, and changes too much between two scans, to be matched reliably. From 26 to 102 km the results are again level.

**In short:** the 26 km blocks sit at the start of a broad optimum that reaches to about 100 km, consistent with the rain moving nearly uniformly over about 50 km. Changing the block size within that range makes no clear difference; larger blocks, with blending, would slightly reduce the excess rain at long lead times. Blocks smaller than about 26 km should be avoided. Chosen on one half of the season, the block size does not carry over exactly to the other (Appendix D.4), another sign that it matters little.

### B.4 Measuring motion: speed and sub-cell matching

**How fast, and which way?** In this archive (`results/motion-stats.json`) the whole-map vector has a median speed of {{ms:speed}} km/h (half of the cases from {{ms:speedq}} km/h). At {{ms:eastward}} of the issue times the rain moved toward the east or north-east, against {{ms:westward}} toward any westerly direction: rain over Denmark mostly arrives from the west and south-west. Individual rain features tracked with pysteps' Lucas-Kanade method, which has no search limit, move slower than {{ms:trackp99}} km/h in 99% of cases, and only {{ms:trackabove}} faster than the 115 km/h block matching can follow (section 4.2).

**Is the whole-map vector's speed right?** It runs a little slower than the rain features pysteps' Lucas-Kanade method tracks (B.3): a median {{vs:real.raw.median:2f}} of their speed ({{ex:speed.vector_median:0f}} against {{ex:speed.tracked_median:0f}} km/h). The method itself is not biased: on a scan moved by a known amount it measures a median {{vs:shifted.raw.median:2f}} of that amount. And speeding the vector up hardly helps: by 5% it gains {{sc:gw4s105:60}} at +60 minutes, by 10% {{sc:gw4s110:60}}, by 15% {{sc:gw4s115:60}}. A possible reason for the gap, not tested here, is that the trackable parts of the rain, its sharp edges and cores, move a little faster than the rain as a whole.

![Two ways to build the whole-map vector](figures/24-vector-paths.svg)

**Which block vectors to average?** The whole-map vector is the confidence-weighted average of each block's own match (section 4.3). Block matching, before it moves the rain, repairs those matches (section 4.2): weakly matched blocks borrow the average of their confident neighbours, and empty blocks are filled from the nearest measured ones. Averaging these repaired vectors instead gives a slower whole-map vector, a median {{vs:real.smoothed.median:2f}} of the tracked speed against {{vs:real.raw.median:2f}}, and it places rain worse: the raw version beats it by {{pd:gw4:gw4f:30}} at +30 minutes, {{pd:gw4:gw4f:60}} at +60 and {{pd:gw4:gw4f:120}} at +120 (`scripts/vector_speed.py`). The reason is that the repairs put averages of neighbours into the field, and where neighbours move differently, their average is shorter than either vector. Undoing the fill alone gives {{vs:real.no-fill.median:2f}}; undoing both gives the raw {{vs:real.raw.median:2f}}. Other suspects change the speed by 0.01 or less:

- the scaling down of weakly matched blocks' vectors ({{vs:real.no-shrink.median:2f}} without it);
- whole-cell matching ({{vs:real.raw-sub.median:2f}} refined to a fraction of a cell);
- the edges of radar coverage ({{vs:real.raw-inner.median:2f}} with them left out);
- the averaging of three scan pairs ({{vs:real.last-pair.median:2f}} with the last pair alone);
- fixed echoes (masking them, Appendix A.3, moves the whole-map vector by a median {{fe:speed.vector_change_median:2f}} km/h).

**Does matching to a fraction of a cell help?** Each block's whole-cell match was refined to a fraction of a cell, with a parabola through the mismatch at the best shift and its two neighbours in each direction. Blocks whose best whole-cell match is no shift were refined the same way, so rain moving less than half a cell between scans is no longer read as standing still. On a known shift this halves the error of single block vectors, and narrows the whole-map vector's scatter from {{vs:shifted.raw.p25:2f}}–{{vs:shifted.raw.p75:2f}} to {{vs:shifted.raw-sub.p25:2f}}–{{vs:shifted.raw-sub.p75:2f}} of the true speed.

In the forecasts the gain is small. Block matching improves by {{pr:subcell-all+benchmark-10min:block-sub-all:block:60}} at +60 minutes (better in {{pw2:subcell-all+benchmark-10min:block-sub-all:block:60}} of rain episodes), while its rain total rises from {{rr:benchmark-10min:block:60}} to {{rr:subcell-all:block-sub-all:60}} of the observed. Refining only the blocks that already register a whole-cell shift gains less ({{pr:subcell+benchmark-10min:block-sub:block:60}}). The whole-map vector gains {{pr:subcell-all+benchmark-10min:gw4suba:gw4:60}}: averaging many blocks and pairs already resolves fractions of a cell. pysteps Lucas-Kanade stays ahead of the refined block matching by {{pr:subcell-all+benchmark-10min:pysteps-lk:block-sub-all:60}} at +60 minutes. So whole-cell rounding is not what mainly holds the simple methods back. At a single place it makes no difference either: at the five cities of section 5.6, refined block matching catches {{sb:hour1.block-sub-all.caught:pct}} of rainy hours in the next hour, against {{sb:hour1.block.caught:pct}} with whole-cell matching, with {{sb:hour1.block-sub-all.false_alarms:pct}} against {{sb:hour1.block.false_alarms:pct}} false alarms (CSI {{sb:hour1.block-sub-all.csi:2f}} against {{sb:hour1.block.csi:2f}}; difference {{sb:hour1.csi_diff.d:3f}}, 95% interval {{sb:hour1.csi_diff.lo:3f}} to {{sb:hour1.csi_diff.hi:3f}}), and its rain total is {{sb:hour1.block-sub-all.rain_ratio:2f}} of the observed against {{sb:hour1.block.rain_ratio:2f}} (`scripts/subcell_cities.py`). The refinement is not used elsewhere in this report.

### B.5 Moving the rain forward

All the methods move the rain the same way once the motion is measured.

**Looking upstream.** The forecast map is filled one cell at a time. For each cell the method asks: *where is the rain now that will be here in 30 minutes?* It finds the answer by starting at that cell and stepping *against* the motion, upstream, one 10-minute step at a time, three steps for 30 minutes. Whatever the latest radar scan shows at the point it reaches is copied into the forecast cell; if that point falls between cells, which it usually does, the value is a weighted average of the nearest ones. This "pull" (semi-Lagrangian advection) gives every forecast cell exactly one value and reads the radar only once, so showers do not blur away step after step. Pushing each rainy cell forward instead would leave gaps and pile-ups wherever the motion is a fraction of a cell or differs between blocks.

![Filling the forecast map by looking upstream](figures/04-backward-tracing.svg)

**The rain's strength** does not change: the simple methods and Lucas-Kanade keep the latest scan's intensities at every lead time, apart from a slight smoothing where a look-up lands between cells. S-PROG and STEPS keep the overall amount of rain about the same but let small showers fade and spread out.

**Where it goes wrong.** Looking upstream works well when the motion changes smoothly across the map. Where two neighbouring blocks have different vectors, forecast cells on either side of the block edge look upstream in different directions. Some rain in the radar scan is then never picked up by any cell (it is dropped), and some is picked up by two cells (it is copied twice, adding rain that was not there). This is why block matching forecasts more rain than the whole-map vector (section 5.3):

![Dropping and copying rain](figures/05-failure-mode.svg)

**At the map edge**, where rain would enter from beyond the map, the simple methods repeat the edge value and pysteps lets no rain in. This shows as vertical streaks along the edges of some forecasts in section 5.1, and may explain part of why pysteps' rain totals fall below the simple methods' at long lead times (Lucas-Kanade {{r:pysteps-lk:180}}, whole-map vector {{r:gw4:180}} at +3 hours); this has not been checked.

## Appendix C. The chance of rain in depth

Section 5.5 gives the conclusions of this comparison; this appendix gives the details.

**Why a neighbourhood?** How long rain stays predictable grows with its size. Rain patterns of 0.2 to 200 km remain recognisable, once their motion is taken into account, for about 20 minutes ([Ruzanski and Chandrasekar, 2012](https://doi.org/10.1175/JAMC-D-11-069.1)); the growth and decay of rain is predictable for up to about 2 hours only for features larger than about 250 km ([Radhakrishna, Zawadzki and Fabry, 2012](https://doi.org/10.1175/JAS-D-12-029.1)). After an hour, a shower in the right area but not the right spot is about as much as extrapolation can deliver, so a single forecast is best read over a neighbourhood, and the best neighbourhood widens with lead time. The same holds for the spatial accuracy score, which is why it is computed over about 30 km (section 3.2).

**STEPS at its full defaults.** The STEPS run of section 5 has 8 members and no random perturbation of the motion field. With pysteps' defaults, 24 members and the motion perturbed, the probabilities improve a little: a Brier improvement of {{b@steps:pysteps-steps-default-mean:60}} at +60 minutes and {{b@steps:pysteps-steps-default-mean:180}} at +3 hours, against {{b:pysteps-steps-mean:60}} and {{b:pysteps-steps-mean:180}}. Both changes contribute: the perturbation mostly at long leads ({{b@steps:pysteps-steps-bps-mean:180}} at +3 hours with 8 members), more members at every lead. The ensemble mean, on the other hand, places rain worse, with an FSS gain of {{d@steps:pysteps-steps-default-mean:60}} at +60 minutes against {{d:pysteps-steps-mean:60}}: perturbed members disagree more about where the rain goes, so their mean spreads it out. For the chance of rain STEPS' lead only grows at its defaults; for a single forecast, plain Lucas-Kanade stays the better choice.

**A fair comparison.** A single forecast can give a probability too: the share of its cells with rain within a window around each cell, a *neighbourhood probability*:

![How a single forecast gives a chance of rain](figures/25-neighbourhood-probability.svg)

The figure uses a window of 5 x 5 cells, about 16 km; windows of about 10 to 80 km were tried, and a wider window gives smoother, more cautious chances.

STEPS' own probabilities were averaged over the same windows, and every forecast is still scored against the one cell. Brier improvement over persistence's own rain-or-no-rain forecast, with each method's best window in bold (`scripts/compare_probs.py`):

{{table:probs}}

- **STEPS' lead grows with lead time.** At +3 hours the single forecasts need ever wider windows: their gain is still rising at 80 km (Lucas-Kanade {{pb:improvement.pysteps-lk_n25_at_180.d:4f}}, block matching {{pb:improvement.bw7_n25_at_180.d:4f}}), and STEPS stays ahead ({{pb:improvement.pysteps-steps-default-mean_n25_at_180.d:4f}}). With the windows that were best at +60 minutes, its lead over Lucas-Kanade grows from {{pb:summary.steps_vs_lk_60.d:4f}} to {{pb:summary.steps_vs_lk_180.d:4f}}. An ensemble whose members spread apart as the forecast ages adapts to the growing uncertainty by itself; a single forecast needs the window widened by hand.
- **At +60 minutes the gap nearly closes.** With a window of about {{pb:summary.best_km.pysteps-lk:0f}} km, Lucas-Kanade reaches {{pb:summary.best.pysteps-lk_60:4f}} and block matching {{pb:summary.best.bw7_60:4f}}, against {{pb:summary.best.pysteps-steps-default-mean_60:4f}} for STEPS at its defaults: its lead over Lucas-Kanade almost disappears.
- **The best window was picked on the same data.** At +60 minutes the gain of the single forecasts peaks at about 48 km and falls again at 80, and the peak is flat, so the exact choice matters little.

The same comparison as curves, with the reliability of the chances: how often it rained when a method gave a certain chance (on the diagonal = honest):

![The chance of rain, map-wide](figures/21-probabilities.svg)

**How honest are the chances?** With each method at its best window, when the single forecasts give an 85% chance of rain it rains about {{pb:reliability.gw4_rel_n15_at_60.o.8:pct}} to {{pb:reliability.pysteps-lk_rel_n15_at_60.o.8:pct}} of the time, and with STEPS {{pb:reliability.pysteps-steps-default-mean_rel_n5_at_60.o.8:pct}}: all of them overstate high chances somewhat, the single forecasts a little more. Read over a window too small for them, about 30 km, the single forecasts overstate far more ({{pb:reliability.bw7_rel_n9_at_60.o.8:pct}} for block matching).

**A chance of rain at one spot, from one forecast.** The comparisons above score the map at a few lead times. A person at one place asks something narrower: will it rain here in ten minutes, in an hour, and when will it start or stop? To answer that, the whole-map vector's single forecast was turned into a simple probability model.

*The model.* At one place the main error of a moving-rain forecast is *where* the rain will be: the measured motion is slightly off, and the error grows with lead time. So the forecast is copied 40 times, and each copy is displaced by a random offset whose standard deviation grows in proportion to the lead time, by about one kilometre for every three minutes ahead: some 3 km at +10 minutes, 20 km at +1 hour and 40 km at +2 hours. Each copy keeps the direction of its offset at every lead time, so it is one consistent alternative future, in which the rain arrives a little earlier or later, or a little to one side. The chance of any statement, such as "rain here at +30 minutes" or "rain starts here within an hour", is the share of copies for which it comes true. The rate is read off the window widths that scored best at each lead time, chosen on one half of the season and scored on the other; both halves chose the same widths (`scripts/local_probs.py`, `scripts/local_timing.py` and their summaries).

*Scored* in every cell of the scoring area, from every issue time, against STEPS at its defaults (24 members) calibrated on the other half of the season, at 0.5 mm/h; 0.1 mm/h gives the same picture. First the chance of rain at each moment ahead:

![The chance of rain at one spot, at each moment ahead](figures/28-local-chance.svg)

- **One hour ahead the model is close to STEPS, two hours ahead level with it:** a Brier improvement over persistence of {{lp:0.5:gw_grow:60:imp}} against {{lp:0.5:steps_grow_cal:60:imp}} at +60 minutes, and {{lp:0.5:gw_grow:120:imp}} against {{lp:0.5:steps_grow_cal:120:imp}} at +2 hours. STEPS keeps a small lead in the first half hour ({{lp:0.5:steps_grow_cal:10:imp}} against {{lp:0.5:gw_grow:10:imp}} at +10 minutes). The same forecast read as rain or no rain reaches only {{lp:0.5:gw:60:imp}} at +60 minutes.

Then statements about timing, for 30 minutes, 1 hour and 2 hours ahead: *rain starts within* (where it is dry now), *rain within* (anywhere), and *dry for good within*, meaning no rain from then until +2 hours (where it is raining now):

![Statements about timing at one spot](figures/29-local-timing.svg)

- **The model reaches 92 to 100% of STEPS' improvement:** {{lt:0.5:start:60:gw_shift:pct}} for "rain starts within an hour" and {{lt:0.5:start:120:gw_shift:pct}} within two hours, where the two do not differ significantly. The forecast read as rain or no rain reaches about half.

*What did not help.* Stretching the offsets along the motion, adding the forecasts of the last half hour as extra copies, and calibrating the model's chances changed nothing or made them worse: its chances are honest as they are. For timing, treating each lead time separately instead of keeping each copy coherent does clearly worse at longer horizons.

**And cell size?** Everything in this appendix was run on the 3.2 km grid only; finer grids were not tested. The expectation, from the cell-size study (Appendix B.2) rather than from a measurement, is that the conclusions do not change. A neighbourhood probability is the rainy share of an area in kilometres, and a finer grid only samples the same area more finely; judged over about 30 km, cell size changes rain placement by less than 0.01 for every method. What would change is the cell-by-cell score: a smaller cell is a smaller target, wet less often and harder to hit exactly, so a forecast that can only say rain or no rain would fall further behind STEPS there, the built-in advantage this fair comparison removes. The radar truth also becomes patchier on a finer grid, so Brier values are comparable between grids only as improvements over persistence. For someone at one spot, a finer grid gives the chance for a smaller place, but how far rain is typically misplaced within an hour keeps the useful window at tens of kilometres.

## Appendix D. Uncertainty and robustness

D.1 explains the 95% intervals used throughout the report. D.2 to D.4 are the robustness checks summarised in section 6: the results by month, with coarser resampling units, and with settings chosen on held-out months. D.5 gives the full result tables behind section 5.

### D.1 How the intervals are made

Every score in this report comes from a limited sample of rain: {{n:units}} rain episodes. A different six months would give somewhat different numbers, and the 95% intervals show by how much. They come from a *bootstrap*, which imitates having observed a different sample of rainy periods by drawing again from the ones we have:

1. Take the {{n:units}} rain episodes.
2. Draw {{n:units}} of them at random, *allowing repeats*. Some episodes appear twice or three times and about a third are left out: a new sample, similar to the real one but not the same.
3. Compute the score on that sample, exactly as on the real one.
4. Repeat 2,000 times. Leaving out the lowest and the highest 2.5% of the 2,000 scores, the range of the rest is the *95% interval*.

![Resampling whole rain episodes](figures/07-bootstrap.svg)

For example, pysteps Lucas-Kanade improves on persistence by {{d:pysteps-lk:60}} at +60 minutes, with a 95% interval of {{ci:pysteps-lk:60}}: with another sample of similar rain, the gain would very likely fall in that range.

**Why episodes, not single forecasts.** Forecasts issued an hour apart within one rainy period share the same weather: if a method struggles with that weather, it struggles in all of them. Resampling single forecasts would treat them as independent evidence and give intervals that are far too narrow; the rain episode is the unit that is roughly independent.

**Comparing two methods.** When two methods are compared, each of the 2,000 samples uses the *same* episodes for both and records the difference. A difficult period then counts against both at once, so the interval shows how consistently one method beats the other; an interval that does not include 0 means the difference is statistically significant. The report also gives the share of individual episodes in which one method beats the other. When that share and the pooled difference disagree, a few very rainy episodes are driving the pooled number.

**A caveat.** Episodes cut from one long rainy spell are still related to each other, so the intervals may be somewhat too narrow; resampling whole days or spells instead changes no conclusion (Appendix D.3).

### D.2 By month

FSS gain over persistence at +60 minutes, by month of the rain episode:

{{table:months}}

Every method gains in every month. In April and May persistence scores high (its own FSS is about 0.67, against 0.52 to 0.60 in summer), so there is less to gain. The reason was not investigated. Slower rain and different weather types are plausible: across Europe, convective rain in summer is more common over land, where it follows the daytime heating, while over the seas it shows little daily cycle ([Lombardo and Bitting, 2024](https://doi.org/10.1175/MWR-D-23-0156.1)), so the mix of rain carried in from the sea and showers formed over land shifts through the season. pysteps leads in every month, Lucas-Kanade in five of the six and the STEPS mean in August (figure in section 6).

### D.3 Wider resampling units

The intervals in this report resample rain episodes (Appendix D.1), which may be too fine a unit (the caveat in D.1). Two coarser units were tried instead: whole calendar days (UTC), and whole rainy spells, with episodes less than 3 hours apart merged. The {{n:units}} episodes form {{rb:intervals.units.day:0f}} days and {{rb:intervals.units.spell:0f}} spells. The figure shows the 95% interval of each comparison under each unit, drawn around its own estimate (given under each label) so the interval sizes can be compared directly; the dashed line marks where a difference of 0 lies, when it falls on the chart (FSS over about 30 km, `scripts/robustness.py`; its random draws differ from section 5's, so the episode intervals can differ in the third decimal):

![Intervals by resampling unit](figures/26-resampling-units.svg)

Spells widen the intervals by a median of {{rb:summary.median_wider_spell:pct}}, and no interval widens by more than {{rb:summary.widest:pct}}. Every difference that is significant with episodes stays significant with days and with spells, and none that is not becomes significant.

### D.4 Settings chosen on other months

Some settings were chosen on the same data they are scored on (section 5). To test how much that flatters them, each was chosen again on April to June only, by its FSS gain over persistence at +60 minutes, and scored on July to September, and the other way round. The *regret* is how much the held-out half loses against the setting that would have been best on it.

{{table:heldout}}

- **History, and how the whole-map vector is built, carry over between the halves:** the regret is at most {{rb:summary.max_regret_history:4f}}. Both halves pick 2 hours of history for block matching, a little more than the hour used in section 5, which scores almost the same on either half.
- **Block size is the exception.** Chosen on April to June, the 26 km blocks lose {{rb:summary.blocksize_regret:3f}} on July to September against blended 102 km blocks; chosen on July to September, the blended 102 km blocks lose nothing on April to June. Either way, block size matters little (Appendix B.3).

The methods, each at the history chosen on the other half, compared on the held-out half alone:

{{table:heldoutfinal}}

pysteps Lucas-Kanade stays significantly ahead of both simple methods on either half. Block matching is ahead of the whole-map vector on both, significantly on April to June but not on July to September.

### D.5 Full result tables

All the scores at +60 minutes (section 3.2; CSI as in section 5.6, here cell by cell over the map):

{{table:headline_full}}

FSS gain over "nothing moves" at every lead time to 3 hours:

{{table:leads}}

The methods head to head, on exactly the same rain episodes: *A − B* is the difference in FSS with its 95% interval, and *episodes where A is better* counts the individual episodes A wins:

{{table:paired}}

Rain at the five cities in the second hour (60 to 120 minutes):

{{table:cities2}}

CSI for the next hour, city by city:

{{table:citiesbycity}}

## Appendix E. Reproducing this

Everything is in this repository. Data and virtual environment are git-ignored. `--stride 2` (the default) is the 10-minute axis of full-range scans; `--stride 1` uses every scan. `scripts/backfill.py --regrid` rebuilds the grids from the raw files already on disk.

```
# Set-up and data
python3 -m venv .venv && . .venv/bin/activate
pip install -e . pytest pysteps opencv-python-headless markdown cairosvg
python scripts/backfill.py 2026-04-01 2026-09-23        # about 4.5 GB raw scans, about 90 min
python scripts/build_index.py                            # memory-mappable day files, about 7 GB
pytest

# Section 5 and Appendix B.1: main benchmark (about 35 min on 12 cores), history and long leads (about 15 min)
python scripts/run_eval.py --events fine --every 6 --hist 7 --leads 30,60,90,120,180 \
    --models persistence,block,block-windows,global-windows,global-windows-smoothed,pysteps-lk,pysteps-lk7,pysteps-sprog,pysteps-steps \
    --out results/benchmark-10min.jsonl
python scripts/run_eval.py --events fine --every 6 --hist 13 --leads 30,60,90,120,180,240,360 \
    --models persistence,block-windows,global-windows,pysteps-lk,pysteps-lk7,pysteps-lk13 --out results/benchmark-10min-window.jsonl
python scripts/run_cities.py && python scripts/run_cities.py --update bw7   # section 5.6, about 10 min
python scripts/run_eval.py --issues-from results/benchmark-10min.jsonl --hist 7 --leads 30,60,90,120,180 \
    --models persistence,pysteps-steps-bps,pysteps-steps-default --out results/steps-defaults.jsonl   # Appendix C, STEPS at its defaults

# Appendices B.1 and B.4: motion statistics
python scripts/motion_stats.py

# Appendix B.1: history in steady and turning flow (needs data/era5 from scripts/fetch_era5.py)
python scripts/turning_flow.py

# Appendix C: a chance of rain at one spot (every cell, every 10 minutes to +2 h; about 30 min on 20 cores)
python scripts/local_probs.py 20 && python scripts/local_probs_summary.py
# Appendix C: timing at one spot (about 25 min on 22 cores)
python scripts/local_timing.py 22 && python scripts/local_timing_summary.py

# Appendix A.2: scans 5 or 10 minutes apart
python scripts/run_eval.py --stride 2 --region common --events fine --every 6 --hist 7 --leads 30,60,90,120,180 \
    --models persistence,block,block-windows,global-windows,pysteps-lk,pysteps-lk7 --out results/check-cadence-10min.jsonl
python scripts/run_eval.py --stride 1 --region common --issues-from results/check-cadence-10min.jsonl --hist 13 \
    --leads 30,60,90,120,180 --models persistence,block,block-windows,global-windows,pysteps-lk,pysteps-lk7,pysteps-lk13 \
    --out results/check-cadence-5min.jsonl

# Appendix A.3: fixed echoes
python scripts/climatology.py && python scripts/fixed_echo_mask.py
python scripts/run_eval.py --region clean --issues-from results/benchmark-10min.jsonl --hist 7 --leads 30,60,90,120,180 \
    --models persistence,block,global-windows,pysteps-lk,pysteps-lk7,pysteps-sprog,pysteps-steps --out results/benchmark-clean.jsonl
python scripts/run_cities.py --half 2 --out results/cities-5x5.jsonl
python scripts/run_cities.py --half 2 --region clean --out results/cities-5x5-clean.jsonl
python scripts/motion_stats.py 10 clean && python scripts/compare_mask.py > results/REPORT-fixed-echo.md

# Appendix B.2: cell size (builds the 2 and 1 km archives and reruns on each grid; hours)
bash scripts/run_grid_study.sh

# Appendix B.3: block size, tracked motion, station winds
python scripts/motion_coherence.py && python scripts/fetch_station_wind.py && python scripts/station_vs_rain.py
python scripts/fetch_era5.py && python scripts/era5_vs_rain.py   # winds aloft (needs a CDS account and ~/.cdsapirc)
python scripts/fetch_gauges.py && python scripts/radar_vs_gauges.py   # Appendix A.4, radar against rain gauges
python scripts/run_eval.py --issues-from results/benchmark-10min.jsonl --hist 7 --leads 30,60,90,120,180 \
    --models persistence,block,block-13km,block-51km,block-102km,block-smooth-13km,block-smooth-26km,block-smooth-51km,block-smooth-102km,global-windows \
    --out results/blocksize-3.2km.jsonl                   # and NOWCAST_GRID=2km ... --out results/blocksize-2km.jsonl

# Appendix B.4: speed, speed-ups and sub-cell matching (subcell.jsonl: the same with block-sub,global-windows-sub; both also on the
# cadence check's issue times, with its --stride/--region/--hist, -> subcell[-all]-cadence-10min/5min.jsonl)
python scripts/vector_speed.py
python scripts/run_eval.py --issues-from results/benchmark-10min.jsonl --hist 7 --leads 30,60,90,120,180 \
    --models persistence,global-scaled --out results/speed-scaling.jsonl
python scripts/run_eval.py --issues-from results/benchmark-10min.jsonl --hist 7 --leads 30,60,90,120,180 \
    --models persistence,block-sub-all,global-windows-sub-all --out results/subcell-all.jsonl
python scripts/run_cities.py --out results/cities.jsonl --update block-sub-all && python scripts/subcell_cities.py   # sub-cell matching at the cities

# Numbers quoted in the text, figures, report
python scripts/explain_checks.py
python scripts/robustness.py                             # Appendix D.3 and D.4: resampling units, held-out months
python scripts/run_eval.py --issues-from results/benchmark-10min.jsonl --hist 7 --leads 30,60,90,120,180 --neighbourhood \
    --models persistence,block-windows,global-windows,pysteps-lk,pysteps-sprog,pysteps-steps,pysteps-steps-default \
    --out results/probs.jsonl && python scripts/compare_probs.py   # section 5.5 and Appendix C, neighbourhood probabilities
python scripts/make_schematics.py && python scripts/make_result_figures.py && python scripts/make_case_figures.py
python scripts/build_report.py && python scripts/build_page.py
```

| Path | What |
|---|---|
| `src/nowcastlab/radar.py` | Radar file to rain-rate grid (no data stays missing) |
| `src/nowcastlab/data.py` | The archive as a time axis: full-range scans every 10 minutes by default |
| `src/nowcastlab/grid.py` | The analysis grid: cell size set with `NOWCAST_GRID` (3.2km, 2km or 1km); sizes in km converted to cells |
| `src/nowcastlab/motion.py`, `models.py` | Motion estimation and all forecasting methods behind one interface |
| `src/nowcastlab/evaluate.py`, `metrics.py`, `report.py` | Hindcast harness, scores, rain-episode bootstrap |
| `scripts/` | Download, benchmark, figures, report and page builders |
| `docs/REPORT.template.md`, `docs/REPORT.md` | This report: template and generated text (numbers are filled from `results/`) |
| `results/` | Scored forecasts (`*.jsonl`) and the tables built from them |

## Appendix F. Glossary

- **Nowcast**: a forecast for the next minutes to hours.
- **Scan**: one radar image. DMI makes one every 5 minutes, alternating full-range and doppler; this report uses the full-range ones, every 10 minutes.
- **Lead time**: how far ahead the forecast looks; "+60" is 60 minutes after the issue time.
- **Issue time**: the moment the forecast is made; only scans up to then may be used.
- **Hindcast**: forecasting a past moment using only what was known then, so the forecast can be scored.
- **Persistence**: the reference forecast that the latest scan stays unchanged.
- **Motion vector**: how far, and in which direction, the rain moves per time step.
- **Block matching**: finding where each block of one scan went in the next; one motion vector per block (section 4.2).
- **Whole-map vector**: one motion vector for the whole map, the confidence-weighted mean of the blocks' matches (section 4.3).
- **Sub-cell matching**: refining a whole-cell match to a fraction of a cell (Appendix B.4).
- **Optical flow**: estimating a motion vector at every point of an image sequence.
- **S-PROG, STEPS**: pysteps methods that let small-scale detail fade with lead time; STEPS adds random noise to make an ensemble (section 4.4).
- **Ensemble**: several forecasts, each an equally likely possibility.
- **Rain episode**: a rainy period of at most 12 hours, the unit of independent evidence in the scoring.
- **FSS, Brier score, rain ratio**: see section 3.2. How FSS is computed: for every cell, the share of wet cells in its neighbourhood is taken for the forecast and for the radar; the squared differences between the two are added up over the map (the *mismatch*), as are the squares of both shares (the *reference*, the largest the mismatch could be); FSS is 1 minus mismatch divided by reference. Scores are pooled: mismatches and references of all forecasts in a group are added up before dividing, so rainy forecasts, with more to get right or wrong, weigh more than nearly dry ones.
- **CSI**, critical success index: hits divided by hits, misses and false alarms; see section 5.6.
- **Skill**: how much better a forecast is than persistence.
- **Fixed echo**: a radar signal that looks like rain but stays put, from structures, turbines or the ground (Appendix A.3).
- **Cloud-layer wind**: the mean wind between about 1.5 and 9 km up, which carries rain cells (Appendix B.3).
- **Propagation**: movement of a storm by new cells forming on one side and old ones dying on the other, as opposed to drift with the wind (Appendix B.3).
- **Low**: a low-pressure system, also called a depression, typically several hundred to a thousand km across; in the northern hemisphere the wind circulates around it anticlockwise, so as it passes the wind keeps changing direction and the flow carrying the rain is curved.
- **Front**: the boundary between two air masses, usually trailing from a low. Rain often lines up along it in a band, and the wind turns as it passes: over Denmark a cold front typically turns it from south-westerly to westerly or north-westerly.
- **Convective rain**: showers and thunderstorms from rising warm air, usually small and short-lived; the opposite is widespread, longer-lasting rain from large weather systems.
