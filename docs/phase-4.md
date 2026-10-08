# Phase 4: interest-rate futures

**Status (2026-10-07): planned; Bill's decisions are under "Decisions", with the extra products still to name.** Phase 3 (Treasury securities by CUSIP) is complete except step 3's BLS history and step 7's last alert: see [phase-3.md](phase-3.md). Analytics are deferred to a much later build-out ([analytics-later.md](analytics-later.md)); this phase is data only.

**Goal:** CME's short-term interest-rate (STIR) and Treasury futures as real instruments in secmaster-svc: products, every listed contract with its dates, and for the Treasury futures each contract's **deliverable basket with conversion factors** (Bill, 2026-10-07). Then their daily settlements, volume and open interest in quote-svc, with the rates the STIR contracts settle on and the CFTC's weekly positioning, through the same layers as phases 2 and 3.

**Scope (Bill, 2026-10-07):** interest-rate futures, no analytics, and no settlement prices this phase (Bill, 2026-10-07): contracts, dates, baskets, conversion factors, fixings and positioning. Not in this phase: cheapest-to-deliver, implied repo, gross and net basis, futures-implied rates or a SOFR curve from futures prices, options on futures, intraday data.

## What changes from phase 3

- **The prices aren't free to collect.** Settlement prices, volume and open interest are CME's market data. CME's website shows settlements free to view (after midnight Central for the previous day), but its terms forbid copying CME data in bulk with scripts or crawlers, so a capture job can't read them from cmegroup.com. Prices need a licensed feed (see "Settlements" below), and everything else in this phase comes from free, public sources or is derived from published rules.
- **Instruments come from rules, not a feed.** Phase 3's securities arrived in Treasury's records. Futures contracts are listed by CME on a published cycle, with dates set by its rulebook, so secmaster-svc generates them from a reviewed product seed file and a CME business-day calendar. A licensed feed's contract definitions, if we get one, become a cross-check.
- **Instruments that refer to other instruments.** A Treasury futures contract's basket is a set of phase 3's securities (by sec_id, through their CUSIPs), each with a conversion factor; a STIR contract names the rate it settles on (SOFR, EFFR), which becomes an instrument with daily fixings.

## Products

A product seed file in secmaster-svc (like the CMT seed: the source of truth, changed only in a reviewed PR), one row per product with CME's contract specs, each field citing CME's spec page or rulebook chapter:

| Product | Bloomberg root (name) | CME code | Settles on | Contract months |
|---|---|---|---|---|
| One-month SOFR | SER? | SR1 | Average SOFR over the contract month | Monthly |
| Three-month SOFR | SFR | SR3 | Compounded SOFR over the reference quarter (IMM date to IMM date) | Quarterly, plus serial months near the front |
| 30-day Fed funds | FF | ZQ | Average EFFR over the contract month | Monthly |
| 2-year T-note | TU | ZT | Physical delivery from its basket | March, June, September, December |
| 3-year T-note | 3Y? | Z3N | Physical delivery | Quarterly |
| 5-year T-note | FV | ZF | Physical delivery | Quarterly |
| 10-year T-note | TY | ZN | Physical delivery | Quarterly |
| Ultra 10-year T-note | UXY | TN | Physical delivery | Quarterly |
| T-bond | US | ZB | Physical delivery | Quarterly |
| Ultra T-bond | WN | UB | Physical delivery | Quarterly |

Roots marked ? are unconfirmed; every root is confirmed through OpenFIGI in step 2 before anything is named. Per product: contract size, price quotation and tick (with the reduced ticks some contracts have), listing cycle (how many months are listed), trading hours, and the date rules below. Specs are effective-dated, because CME changes them: the notional coupon behind the conversion factors went from 8% to 6% with the March 2000 contracts, CME changed the 10-year's basket in 2022, and the Ultra 10-year and Ultra bond were launched later than the rest. The exact listing counts, dates and baskets are confirmed against CME's rulebook chapters in step 2, not taken from memory.

## Contracts (`secmaster-svc`)

- **Instruments:** types `fut_stir` and `fut_treasury` for each contract (one per product and contract month), generated from the seed's listing cycle as far back as each product's history and forward to everything currently listed.
- **Dates per contract**, derived from the rulebook with the rule recorded (the "derived" provenance from phase 3): first and last trading day; for the STIR contracts, the reference period the settlement rate is averaged or compounded over and the final settlement date; for the Treasury futures, first intention (position) day, first notice day, first and last delivery day. These need CME's business days, so this phase adds a **`CME` calendar** in calendar-svc built from rules with cited exceptions (like NYSE's), with CME's holiday notices read by hand as the check (not scraped, under CME's website terms).
- **Short names** (Bill, 2026-10-07): Bloomberg tickers with a two-digit year, `TYZ26`, `SFRH27`, `FFX26`, `USZ26`. Bloomberg itself writes `TYZ6` while a contract trades and `TYZ26` once it has expired; the two-digit form from the start means a name never changes. Identifiers per contract: Bloomberg's live ticker (`TYZ6 Comdty`, scheme `TICKER`, valid while listed) and FIGI from OpenFIGI (the key phase 3 already uses), and CME's code (`ZNZ6`, scheme `CME`, valid while listed). A product instrument is named by its root (`TY`).
- **Rolling aliases** like phase 3's on-the-run, named like Bloomberg's generics: `TY1`, `TY2` (front and second contract), with validity, so "the front 10-year future" on a past date resolves to that day's contract. A Treasury contract stops being the front on its first intention day, when positions roll (Bill, 2026-10-07), unlike Bloomberg's default `TY1`, which rolls at expiry; a STIR contract is the front until its last trading day.
- **Status:** listed, trading, in delivery (Treasury futures, between first intention day and last delivery day), expired.

## Deliverable baskets and conversion factors (`secmaster-svc`)

Bill wants basket info for the bond futures (2026-10-07). It's reference data, not analytics: which securities a short may deliver, and the conversion factor each is invoiced at, are both fixed by CME's rules from the security's terms, and phase 3 already holds those terms for every Treasury since 1980.

- **Eligibility:** per product, an effective-dated rule in the seed: fixed-coupon notes and bonds only (no bills, TIPS, FRNs or STRIPS), with a limit on original term and a window of remaining term measured from a date in the delivery month (to first call for the old callable bonds). A security auctioned after a contract's listing joins its basket from its auction date (it's deliverable once issued), so a basket has history: `futures_deliverable` (contract, security, conversion factor, `valid_from`, rule version).
- **Conversion factor:** CME's published formula, the security's price per dollar of face at the notional coupon (6%; 8% before March 2000), with its remaining term rounded down to whole months or quarters as each product specifies, rounded to four decimals. Computed from phase 3's coupon and maturity; recorded with its rule like any derived term.
- **Check:** CME publishes conversion factor lookup tables and a calculator. Bill downloads the current contracts' tables once by hand; they become test fixtures that every computed basket and factor must match, with any difference explained (as with the TIPS reference CPIs). Not a scheduled download, under CME's website terms.
- **Deliverable supply:** each basket security's amount outstanding (from TreasuryDirect's auction records, less amounts stripped from MSPD) is already in secmaster-svc, so the basket can show the deliverable supply. The CTD and basis wait for analytics.

## Fixings: the rates STIR contracts settle on

The New York Fed's reference rates API (free; terms of use recorded in step 1), new sources in mkt-data like phase 2's yields:

| Source | What | History |
|---|---|---|
| `NYFED-SOFR` | SOFR: rate, percentiles, volume | April 2018 |
| `NYFED-EFFR` | EFFR: rate, percentiles, volume, target range | 2000 on the API (H.15 has the older daily series) |
| `NYFED-SOFR-AVG` | SOFR Averages (30, 90, 180-day) and the SOFR Index | March 2020 |

Instruments `SOFR`, `EFFR`, `SOFR-AVG-30D`, `SOFR-AVG-90D`, `SOFR-AVG-180D`, `SOFR-INDEX` (type `rate_fixing`, a seed file like the CMTs), quotes in quote-svc as decimals (`0.0433` = 4.33%) per the Decimal rule. Phase 2 left fixings for later; the STIR contracts make them part of this phase.

## Positioning: CFTC Commitments of Traders

The CFTC's Traders in Financial Futures report (TFF; futures only, and futures and options combined): weekly positions as of Tuesday, published Friday afternoon, long, short and spreading by trader category (dealers, asset managers, leveraged funds, other reportables, non-reportables), plus open interest, for each CFTC contract market code. Public, through the CFTC's Public Reporting Environment API (Socrata), history from 2006 for TFF (the legacy report goes back further; checked in step 1).

- Source `CFTC-TFF`, captured weekly, one capture per report date; near-raw observations keyed by contract market code and field.
- The CFTC reports by product, not contract, so each product (`TY`, `SFR`, …) also gets a `fut_product` instrument, with its CFTC code as an identifier, and the positions are quotes on it.

## Settlements, volume and open interest (not this phase)

Not this phase (Bill, 2026-10-07). The options, kept for when we come back to it, cheapest first:

1. **Databento, usage-based** (GLBX.MDP3, CME Globex MDP 3.0): its `statistics` schema carries CME's settlement price, cleared volume and open interest per contract per day, and `definition` carries every contract's specs and dates. History back to 2010. Pay per GB with no subscription, $125 of free credits for a new account (they expire after six months), and a cost estimate endpoint (`metadata.get_cost`) we call before every pull, refusing anything over a limit. These schemas are small (a few records per contract per day), so the backfill for ten products may fit in the free credits; step 1 prices it before buying anything. Their Standard plan ($199 a month) includes 16+ years of statistics and definitions with license fees included. **To confirm before buying:** what CME's license (through Databento) allows for internal, non-display use of historical settlements on a personal platform with one viewer.
2. **CME DataMine** end-of-day files, licensed directly from CME (from about $105 a month): the official source, with a direct license from CME for internal use; daily files, history by purchase.
3. **No prices this phase:** contracts, dates, baskets, conversion factors, fixings and positioning, and settlements later. Every other step stands without them.

Whichever we pick: captures land raw in mkt-data as CSV (Databento can answer in CSV, so the capture text view works), an API key in SSM under `/home-platform/mkt-data/`, near-raw observations per contract and day (`settle`, `volume`, `open_interest`), quote-svc's fields of the same names, golden from the one source. CME publishes preliminary settlements then final ones, and open interest a day late, so a day is re-fetched (like FedInvest's end-of-day prices) until final.

## Custom UI and voice

- **Futures screen** in mkt-ui: products, then a product's contract strip (each contract's dates and status, its settlement, volume and open interest once there are prices), then a contract's page.
- **Basket view** on a Treasury contract's page: each deliverable security (short name, CUSIP, coupon, maturity, conversion factor, amount outstanding, when it joined), linked to the security's page; and on a security's page, the contracts it's deliverable into.
- **Fixings** on charts like the CMTs; **positioning** as a weekly chart per product and trader category.
- **Voice:** home-mcp tools `mkt_data_future` (a contract or alias such as `TY1`: its dates and status) and `mkt_data_basket` (a contract's deliverables and conversion factors), so "what's in the December 10-year basket" works.

## Monitoring and alerts

The patterns from phases 2 and 3: stale-capture and parse alerts for the new sources (the Sources screen picks them up from mkt-data's catalog); fixings missing on a FED business day; a contract listed by the rules with no settlement on a CME business day (when there are prices); a basket check against the fixtures failing; CFTC's report late (it moves after federal holidays).

## Steps

1. **Raw capture first** (mkt-data): `NYFED-SOFR`, `NYFED-EFFR`, `NYFED-SOFR-AVG` and `CFTC-TFF` captured daily (weekly for CFTC) and kept raw; read the first captures on the hub, record each source's terms and history depth, export fixtures. No price source this phase.
   - **Built (2026-10-07, waiting on merge):** `app/futures/sources.py`, seven sources kept raw (no parser yet): `NYFED-SOFR`, `NYFED-EFFR` and `NYFED-SOFR-AVG` (the New York Fed's reference rates API, JSON, by month), `FRB-H10` (the DDP's H.10 "Daily rates" package, CSV, by month), `ECB-EXR` (every euro reference rate, the ECB data portal's SDMX API, CSV, by month), and `CFTC-TFF` and `CFTC-TFF-COMBINED` (Traders in Financial Futures, futures only and with options, every market, Socrata CSV, by report date). A period with nothing published yet (the New York Fed's empty `refRates`, the ECB's 404, a CFTC answer with only its header) is a failed fetch marked `NOT_PUBLISHED`, never a capture. Job `POST /jobs/futures/{source}/capture?period=`. DAG `mkt_data__futures_sources_capture` (weekdays 7:45 p.m. New York; the months of the last ten days to yesterday, and the last two CFTC reports due) and manual `mkt_data__futures_sources_probe` (one sample period a year per source, for history depth). The Sources screen lists them as a new group, `futures`. Checked from here: the New York Fed's three endpoints (SOFR, EFFR and SOFRAI field names) and both CFTC datasets (TFF futures only `gpe5-46if`, combined `yw9f-hn96`); the H.10 package's series id and the ECB's answer are checked on the first captures.
2. **Products, the `CME` calendar and contracts** (calendar-svc, secmaster-svc): the seed file with every spec cited, the calendar from rules, contracts generated with their dates, short names and Bloomberg roots confirmed through OpenFIGI, Bloomberg tickers, FIGIs and CME codes, rolling aliases; checked against CME's rulebook and listings on a handful of known contracts.
3. **Baskets and conversion factors** (secmaster-svc): eligibility rules, `futures_deliverable` with history, conversion factors; checked against CME's lookup tables (Bill's one-off download as fixtures) for every currently listed Treasury contract.
4. **Fixings** (mkt-data near-raw, secmaster-svc seed, quote-svc): SOFR, EFFR, the SOFR averages and index, backfilled to each source's start.
5. **Positioning** (mkt-data, secmaster-svc product instruments, quote-svc): TFF backfilled from 2006.
6. **Schedule and monitoring:** DAGs, Assets, metrics, alerts.
7. **Screens and voice:** Futures screen, basket view, fixings and positioning charts, home-mcp tools.

## Decisions (Bill, 2026-10-07)

- **Scope:** interest-rate futures data, no analytics; the bond futures' deliverable baskets included.
- **Prices:** none this phase; settlements, volume and open interest later, from a licensed source.
- **Short names:** Bloomberg tickers with a two-digit year (`TYZ26`), generics `TY1`/`TY2`; Bloomberg's live ticker, FIGI and CME's code (`ZNZ6`) as identifiers.
- **Front-contract roll:** Treasury futures at first intention day; STIR at last trading day.
- **Products:** the ten above and more; which ones is still open.

## Open questions

- Which products beyond the ten (Bill, 2026-10-07: "add more").
- The `CME` calendar's early closes and Good Friday sessions (CME has traded rates futures on some Good Fridays when payrolls were released).

## Later (not this phase)

- Settlements, volume and open interest, from a licensed source (above); then Databento's license for historical CME statistics on a personal platform, and whether history before its 2010 start matters.
- CTD, implied repo, basis, futures-implied rates and a SOFR curve from futures: the analytics build-out ([analytics-later.md](analytics-later.md)).
- Options on futures, intraday data, other exchanges' rate futures.

## Sources consulted (2026-10-07)

- CME, [Access to settlement data FAQ](https://www.cmegroup.com/articles/faqs/access-to-cme-group-settlement-data-faq.html), [market data disclaimer](https://www.cmegroup.com/trading/market-data-explanation-disclaimer.html), [website terms of use](https://www.cmegroup.com/tools-information/cme-website-terms-of-use-new.html)
- CME, [Calculating U.S. Treasury futures conversion factors](https://www.cmegroup.com/trading/interest-rates/files/Calculating_U.S.Treasury_Futures_Conversion_Factors.pdf), [conversion factor lookup tables](https://www.cmegroup.com/trading/interest-rates/us-treasury-futures-conversion-factor-lookup-tables.html), [10-year delivery basket change (2022)](https://www.cmegroup.com/news/2022/proposed-enhancements-to-10-year-delivery-basket-us-treasury.html)
- Databento, [GLBX.MDP3](https://databento.com/datasets/GLBX.MDP3), [pricing](https://databento.com/pricing), [retrieving open interest and settlement prices](https://databento.com/docs/examples/futures/retrieving-oi-and-settlement-prices)
- CFTC, [Commitments of Traders report descriptions](https://www.cftc.gov/node/128971)
