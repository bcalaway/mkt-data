# Phase 4: CME rates and FX futures

**Status (2026-10-08): step 1 deployed (captures running daily); step 2's calendars all built and live (`CME-IR`, `CME-FX`, `GB`, `TARGET`, `JP`, `CA`, `CH`, `AU`, `NZ`, `SE`, `NO`, `DK`, `MX`, with SIX's and Norges Bank's lists parsed); step 2a (products and contracts for the main 20) deployed (secmaster-svc #20) and running daily; step 2b (FIGIs, tickers and root checks through OpenFIGI) deployed (secmaster-svc #21); its first run matched FX contracts to other futures, fixed and re-run (#22); done 2026-10-08: 19 of 20 Bloomberg roots confirmed (#24; TWEA not), FIGIs and live tickers on every listed contract OpenFIGI knows, and SR3's dates corrected (#25). Bill's decisions are under "Decisions".** Phase 3 (Treasury securities by CUSIP) is complete: see [phase-3.md](phase-3.md). Analytics are deferred to a much later build-out ([analytics-later.md](analytics-later.md)); this phase is data only.

**Goal:** every interest-rate and FX future CME lists, as real instruments in secmaster-svc: products, every contract with its dates, and for the Treasury futures each contract's **deliverable basket with conversion factors** (Bill, 2026-10-07). With them, the fixings they settle on or track (SOFR, EFFR, and the Fed's and ECB's daily FX rates) and the CFTC's weekly positioning, through the same layers as phases 2 and 3.

**Scope (Bill, 2026-10-07):** all of CME's rates and FX futures ("anything IR or FX that we can get"), no analytics, and no settlement prices this phase: contracts, dates, baskets, conversion factors, fixings and positioning. Non-US rates futures wait for a phase that adds their government bonds (so their baskets come with them), and energy is a later phase of its own (below). Not in this phase: cheapest-to-deliver, implied repo, gross and net basis, futures-implied rates or a SOFR curve from futures prices, options on futures, intraday data.

## What changes from phase 3

- **The prices aren't free to collect.** Settlement prices, volume and open interest are CME's market data. CME's website shows settlements free to view (after midnight Central for the previous day), but its terms forbid copying CME data in bulk with scripts or crawlers, so a capture job can't read them from cmegroup.com. Prices need a licensed feed (see "Settlements" below), and everything else in this phase comes from free, public sources or is derived from published rules.
- **Instruments come from rules, not a feed.** Phase 3's securities arrived in Treasury's records. Futures contracts are listed by CME on a published cycle, with dates set by its rulebook, so secmaster-svc generates them from a reviewed product seed file and a CME business-day calendar. A licensed feed's contract definitions, if we get one, become a cross-check.
- **Instruments that refer to other instruments.** A Treasury futures contract's basket is a set of phase 3's securities (by sec_id, through their CUSIPs), each with a conversion factor; a STIR contract names the rate it settles on (SOFR, EFFR), and an FX contract its currency pair, each an instrument with daily fixings.

## Products

A product seed file in secmaster-svc (like the CMT seed: the source of truth, changed only in a reviewed PR), one row per product with CME's contract specs, each field citing CME's spec page or rulebook chapter. Step 2 starts from CME's full list of listed rates and FX futures and adds every one with a reasonable history; the main ones:

**Rates**

| Product | Bloomberg root (name) | CME code | Settles on | Contract months |
|---|---|---|---|---|
| One-month SOFR | SER? | SR1 | Average SOFR over the contract month | Monthly |
| Three-month SOFR | SFR | SR3 | Compounded SOFR over the reference quarter (IMM date to IMM date) | Quarterly, plus serial months near the front |
| 30-day Fed funds | FF | ZQ | Average EFFR over the contract month | Monthly |
| 2-year T-note | TU | ZT | Physical delivery from its basket | March, June, September, December |
| 3-year T-note | 3Y | Z3N | Physical delivery | Quarterly |
| 5-year T-note | FV | ZF | Physical delivery | Quarterly |
| 10-year T-note | TY | ZN | Physical delivery | Quarterly |
| Ultra 10-year T-note | UXY | TN | Physical delivery | Quarterly |
| T-bond | US | ZB | Physical delivery | Quarterly |
| Ultra T-bond | WN | UB | Physical delivery | Quarterly |
| 20-year T-bond | TWEA? | TWE | Physical delivery | Quarterly |
| 13-week T-bill | TZR | TBF3 | The 13-week bill auction rate | Quarterly (4) plus the nearest 2 serial months (CME's spec page, 2026-10-08) |

**FX** (physically delivered currency; quarterly on the IMM cycle, plus serial months near the front for some)

| Product | Bloomberg root (name) | CME code | Pair |
|---|---|---|---|
| Euro | EC | 6E | EUR/USD |
| Japanese yen | JY | 6J | JPY/USD |
| British pound | BP | 6B | GBP/USD |
| Australian dollar | AD | 6A | AUD/USD |
| Canadian dollar | CD | 6C | CAD/USD |
| Swiss franc | SF | 6S | CHF/USD |
| Mexican peso | PE | 6M | MXN/USD |
| New Zealand dollar | NV | 6N | NZD/USD |

Plus CME's smaller rates and FX contracts (cross rates, emerging-market currencies, E-micros) where they have a reasonable history; step 2 lists them.


3Y, TZR and TWEA are from the vendor-code tables on CME's product pages (2026-10-08); TWEA looks odd for a root and SER (one-month SOFR) has no source yet. Roots marked ? (and every root, before anything is named) are confirmed through OpenFIGI in step 2. Per product: contract size, price quotation and tick (with the reduced ticks some contracts have), listing cycle (how many months are listed), trading hours, and the date rules below. Specs are effective-dated, because CME changes them: the notional coupon behind the conversion factors went from 8% to 6% with the March 2000 contracts, CME changed the 10-year's basket in 2022, and the Ultra 10-year and Ultra bond were launched later than the rest. The exact listing counts, dates and baskets are confirmed against CME's rulebook chapters in step 2, not taken from memory.

### Contract rules from CME's rulebook (read 2026-10-08)

The rulebook chapters leave the listing schedule to the Exchange ("the number of contract expiration months open for trading ... shall be determined by the Exchange"); everything else the contracts need is in them. Dates count CME business days.

| Product | Chapter | Unit | Tick (outright) | Last trading day | Delivery or final settlement |
|---|---|---|---|---|---|
| ZT 2-year | CBOT 21 | $200,000 face | 1/8 of 1/32 ($7.8125) | Last business day of the contract month | Delivery through the 3rd business day after the last business day of the month |
| Z3N 3-year | CBOT 39 | $200,000 | 1/8 of 1/32 ($7.8125) | Last business day of the month | Through the 3rd business day after the month's last business day |
| ZF 5-year | CBOT 20 | $100,000 | 1/4 of 1/32 ($7.8125) | Last business day of the month | Through the 3rd business day after the month's last business day |
| ZN 10-year ("6½ to 8-Year") | CBOT 19 | $100,000 | 1/2 of 1/32 ($15.625) | No trading in the last 7 business days of the month (so the 8th business day before month end is the last; close at 12:00 noon) | Any business day of the month through its last business day |
| TN Ultra 10-year | CBOT 26 | $100,000 | 1/2 of 1/32 | As ZN | As ZN |
| TWE 20-year | CBOT 25 | $100,000 | 1/32 ($31.25) | As ZN | As ZN |
| ZB T-bond | CBOT 18 | $100,000 | 1/32 ($31.25) | As ZN | As ZN |
| UB Ultra bond | CBOT 40 | $100,000 | 1/32 ($31.25) | As ZN | As ZN |
| ZQ 30-day Fed funds | CBOT 22 | $41.67 a basis point | 0.005 ($20.835); 0.0025 in some months | Last business day of the month | 100 minus the month's average daily EFFR (every calendar day; a day without a rate takes the previous published one), rounded to 0.1 bp |
| SR1 one-month SOFR | CME 461 | $41.67 a bp | 0.005; 0.0025 in some months | Last business day of the month | 100 minus the month's average daily SOFR (every day; prior published value on days without one), rounded to 0.001 |
| SR3 three-month SOFR | CME 460 | $25 a bp ($2,500 × index) | 0.005 ($12.50); 0.0025 within four months of expiry | Business day before the 3rd Wednesday of the contract month | 100 minus compounded SOFR over the reference quarter (3rd Wednesday of the 3rd month before, to the 3rd Wednesday of the contract month, excluded), SIFMA business days, rounded to 0.0001 |
| TBF3 13-week bill | CME 457 | $25 a bp | 0.005; 0.0025 in the last month | 2:00 p.m. on the Monday of the expiry week (the next business day if Treasury holds no auction that Monday) | 100 minus that auction's 13-week high discount rate, rounded to 0.001 |
| 6E euro | CME 261 | €125,000 | $0.00005 ($6.25) | 2nd business day before the 3rd Wednesday | Physical delivery on the 3rd Wednesday |
| 6J yen | CME 253 | ¥12,500,000 | $0.0000005 ($6.25) | 2nd business day before the 3rd Wednesday | 3rd Wednesday |
| 6B pound | CME 251 | £62,500 | $0.0001 ($6.25) | 2nd business day before the 3rd Wednesday | 3rd Wednesday |
| 6A Australian dollar | CME 255 | A$100,000 | $0.00005 ($5.00) | 2nd business day before the 3rd Wednesday | 3rd Wednesday |
| 6C Canadian dollar | CME 252 | C$100,000 | $0.00005 ($5.00) | **1st** business day before the 3rd Wednesday | 3rd Wednesday |
| 6S Swiss franc | CME 254 | CHF 125,000 | $0.00005 ($6.25) | 2nd business day before the 3rd Wednesday | 3rd Wednesday |
| 6M Mexican peso | CME 256 | MXN 500,000 | $0.00001 ($5.00) | 2nd business day before the 3rd Wednesday | 3rd Wednesday |
| 6N New Zealand dollar | CME 258 | NZ$100,000 | $0.00005 ($5.00) | 2nd business day before the 3rd Wednesday | 3rd Wednesday |

FX business days: the last trading day moves earlier if it's a Chicago or New York bank holiday, and delivery moves later if the 3rd Wednesday isn't a business day in the delivery country or is a Chicago or New York bank holiday. So the FX contracts need each currency's bank holidays as well as the `CME` calendar (an open question below).

**Deliverable grades** (all: fixed-principal, fixed semi-annual coupon notes or bonds; remaining term measured from the first day of the contract month; a new issue joins on its issue date; the Exchange may exclude a new issue):

| Product | Original term | Remaining term | Conversion factor rounding |
|---|---|---|---|
| ZT | ≤ 5 years 3 months | ≥ 1 year 9 months and ≤ 2 years | Down to whole months |
| Z3N | ≤ 7 years | ≥ 2 years 9 months and ≤ 3 years | Down to whole months |
| ZF | ≤ 5 years 3 months | ≥ 4 years 2 months | Down to whole months |
| ZN | ≤ 10 years | ≥ 6 years 6 months and < 8 years (the chapter's current text; the earlier basket, before CME's 2022 change, comes from the change's notice in step 2) | Down to quarters |
| TN | ≤ 10 years | ≥ 9 years 5 months | Down to quarters |
| TWE | (none stated) | ≥ 19 years 2 months and < 19 years 11 months | Down to quarters |
| ZB | (none) | ≥ 15 years and < 25 years (a callable bond: not callable for at least 15 years and maturing in under 25) | Down to quarters, to first call if callable |
| UB | (none) | ≥ 25 years | Down to quarters |

Conversion factor: the price per one point of par at which a bond with the same coupon and the rounded time to maturity yields 6% (each chapter, B rule), from CME's published method.

Sources: CBOT rulebook chapters [18](https://www.cmegroup.com/rulebook/CBOT/II/18.pdf), [19](https://www.cmegroup.com/rulebook/CBOT/II/19.pdf), [20](https://www.cmegroup.com/rulebook/CBOT/II/20.pdf), [21](https://www.cmegroup.com/rulebook/CBOT/II/21.pdf), [22](https://www.cmegroup.com/rulebook/CBOT/III/22.pdf), [25](https://www.cmegroup.com/rulebook/CBOT/III/25.pdf), [26](https://www.cmegroup.com/rulebook/CBOT/III/26.pdf), [39](https://www.cmegroup.com/rulebook/CBOT/III/39.pdf), [40](https://www.cmegroup.com/rulebook/CBOT/III/40.pdf); CME rulebook chapters [251](https://www.cmegroup.com/rulebook/CME/III/250/251/251.pdf), [252](https://www.cmegroup.com/rulebook/CME/III/250/252/252.pdf), [253](https://www.cmegroup.com/rulebook/CME/III/250/253/253.pdf), [254](https://www.cmegroup.com/rulebook/CME/III/250/254/254.pdf), [255](https://www.cmegroup.com/rulebook/CME/III/250/255/255.pdf), [256](https://www.cmegroup.com/rulebook/CME/III/250/256/256.pdf), [258](https://www.cmegroup.com/rulebook/CME/III/250/258/258.pdf), [261](https://www.cmegroup.com/rulebook/CME/III/250/261/261.pdf), [457](https://cmegroup.com/rulebook/CME/V/450/457.pdf), [460](https://www.cmegroup.com/rulebook/CME/V/450/460/460.pdf), [461](https://www.cmegroup.com/content/dam/cmegroup/rulebook/CME/IV/400/461.pdf).

**Listing schedules** (CME's spec pages, read by hand 2026-10-08 into [cme-contract-specs-2026-10.md](cme-contract-specs-2026-10.md)): the Treasury futures 3 consecutive quarterlies; ZQ 60 consecutive months; SR1 25 months; SR3 39 quarterlies and the nearest 6 serial months; TBF3 4 quarterlies and the nearest 2 serial months; 6E, 6J, 6B, 6A, 6C and 6M 20 quarterlies with serial contracts "listed for 16 months"; 6S 20 quarterlies; 6N 6 quarterlies. **Still to find:** the dates each rule took effect (the ZN basket change, the 6% coupon), the launch dates of ZT, 6M and 6N, each launched product's first contract month, CBOT's delivery chapter for the Treasury futures' first intention and notice days, and the Bloomberg roots through OpenFIGI (step 2b).

## Calendars (calendar-svc; Bill, 2026-10-08: all of them first)

Every contract date counts business days: CME's for trading, and for the FX contracts also Chicago's and New York's bank holidays and the delivery country's (CME rulebook, chapters 251–261). So before any contract is generated, calendar-svc gets nine new calendars, built the way phase 1 built FED, SIFMA-US and NYSE: a publisher's own list where one exists (captured raw by mkt-data, parsed to near-raw), rules with cited exceptions for the years before it, and a projection to 2100 from the same rules. Chicago and New York bank holidays are the Federal Reserve's (FED, already there).

| Calendar | For | Publisher's list (captured) | Rules and exceptions for older years |
|---|---|---|---|
| `CME-IR`, `CME-FX` | CME's business days (a trade date and a settlement) for the rates and the FX futures, separately: on one-off days CME has closed one and not the other (2018-12-05: rates closed, FX open) | CME's notices, read by hand (CME's terms rule out capturing its pages) and cited in the rules files, which are extended a year at a time | NYSE's holidays (Good Friday, Juneteenth from 2022), with cited exceptions: the payrolls Good Fridays CME traded and settled (2007, 2010, 2012, 2015, 2021, 2023, 2026), September 11–12, 2001, Sandy (2012-10-29, rates) and the Bush mourning day (2018-12-05, rates). Built in mkt-data #118 |
| `TARGET` | euro | The ECB's closing days, fixed since 2002 "until further notice" ([1999](https://www.ecb.europa.eu/press/pr/date/1999/html/pr990715_1.en.html), [2001](https://www.ecb.europa.eu/press/pr/date/2000/html/pr000525_2.en.html), [2002 on](https://www.ecb.europa.eu/press/pr/date/2000/html/pr001214_4.en.html)), so the rules file is the calendar, 1999–2100, no projection | 1999: New Year and Christmas only, plus 31 Dec 1999; 2000: the standing set; 2001: plus 31 Dec. No weekend observance. Built in mkt-data #121 |
| `GB` | sterling (London) | [gov.uk bank holidays JSON](https://www.gov.uk/bank-holidays.json), England and Wales, 2019 on (`GB-GOVUK`) | Rules 1990–2018 (substitute days to the next free weekday) with the one-offs cited: VE Day 1995, the Millennium, the 2002 and 2012 jubilees, the 2011 royal wedding; gov.uk itself lists 2020, 2022 and 2023's. Built in mkt-data #119 |
| `JP` | yen (Tokyo) | [Cabinet Office national holidays CSV](https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv), 1955 to next year (Shift_JIS), `JP-CAO` | The banks' December 31 and January 2–3 (`JP-BANK`, adds dates only, 1990–2100); a projection to 2100 under the law as it stands since 2020, with the equinoxes by formula, substitute holidays and citizens' holidays (`JP-PROJECTED`). Built in mkt-data #122; the CSV's names in English, as the projection names them, a 休日 named as a substitute (`Children's Day (observed)`) or a citizens' holiday from the days around it (#124) |
| `AU` | Australian dollar (Sydney) | None capturable: data.gov.au's dataset stopped at 2025, and NSW's list is a web page a year or two ahead. Checked against ANZ's 2024–2026 lists and NSW's 2026–2027 | Rules, 1990–2100 (`AU-RULES`): NSW public holidays and the August Bank Holiday, all non-business days for AUD FX (ANZ; RBA: RITS closes only when Sydney and Melbourne both do). New Year, Australia Day, Christmas and Boxing Day move off weekends; Anzac Day doesn't, but the 2026 order added Mondays for 2026 and 2027 only (exceptions). Also exceptions: 2011-04-26 (Easter Monday's substitute, Anzac Day being Easter Monday) and 2022-09-22 (day of mourning). Before 1994 Australia Day is taken as the Monday on or after January 26, unchecked for NSW. Built in mkt-data #128 |
| `CA` | Canadian dollar (Toronto) | None capturable: Payments Canada's system closure schedule is a web page (to be read once its URL is approved); checked against RBC's 2025, PNC's 2026 and BMO's 2023 published lists | Rules, 1990–2100 (`CA-RULES`): New Year, Good Friday, Victoria Day, Canada Day, Labour Day, Truth and Reconciliation (from 2021), Thanksgiving, Remembrance Day, Christmas, Boxing Day; a weekend holiday moves to Monday, Christmas and Boxing Day to the next free weekdays. Regional days (Family Day, the Civic Holiday) and Easter Monday process; so did the 2022-09-19 day of mourning (Payments Canada's notice). Before 2021 the rules are unchecked against a published list. Built in mkt-data #125 |
| `CH` | Swiss franc (Zurich) | [SIX's SIC banking holidays](https://www.six-group.com/dam/download/banking-services/interbank-clearing/en/payment_services/sic/banking-holidays.pdf) (PDF, next year: 2027 now; `SIX-SIC`, parsed by `app/calendars/six_sic.py` from #127) | Rules, 1990–2100 (`CH-RULES`): New Year, Berchtold's Day, Good Friday, Easter Monday, Labour Day, Ascension, Whit Monday, Swiss National Day (from 1994, its first year as a federal holiday), Christmas, St Stephen's; never moved for a weekend, and a holiday on another is one day (`"collision": "share"`: Ascension on May 1, 2008). Reproduces SIX's 2027 and the 2026 list exactly; before 2026 unchecked against a published list. Built in mkt-data #126 |
| `MX` | Mexican peso (Mexico City) | None stable: the CNBV's yearly closing days are a DOF notice at a new address each year. Checked against its 2024 list (DOF, 2023-12-12) and 2026's (DOF, 2025-12-10, as reported) | Rules, 1990–2100 (`MX-RULES`): the CNBV's closing days, with the Monday holidays from 2006 (fixed dates before), Holy Thursday, November 2, December 12, and the inauguration every six years (December 1 to 2018, October 1 from 2024); never moved for a weekend. Built in mkt-data #130 |
| `NZ` | New Zealand dollar (national: ESAS) | None capturable (govt.nz's list is a web page; data.govt.nz's is behind bot protection). Checked against ANZ's 2023–2025 list | Rules, 1990–2100 (`NZ-RULES`): the national holidays banks, NZClear and ESAS close for. Not the Auckland and Wellington anniversary days: ANZ lists them as NZD settlement days, and the NZFMA's business-day calendar has treated them as good days since January 2026. New Year, January 2, Christmas and Boxing Day move off weekends; Waitangi and Anzac Day from 2014. Matariki from the 2022 Act's table (2022–2052; later dates come by Order in Council). Exception: 2022-09-26 (Queen's memorial day). Built in mkt-data #129 |
| `SE` | Swedish krona (Stockholm) | None capturable (no official list found). Checked against SEB's 2024 and 2026 Nordic bank holiday lists | Rules, 1990–2100 (`SE-RULES`): public holidays plus the banks' eves (Midsummer, Christmas, New Year's); National Day from 2005 in place of Whit Monday; never moved for a weekend. Built in mkt-data #130 |
| `NO` | Norwegian krone (Oslo) | [Norges Bank's NBO settlement days](https://www.norges-bank.no/en/topics/Norges-Banks-settlement-system/Settlement-days/) (web page, this year; `NO-NBO`, parsed by `app/calendars/nbo.py` from #131) | Rules, 1990–2100 (`NO-RULES`): NBO's closing days, Maundy Thursday and Christmas Eve included, New Year's Eve open; never moved for a weekend. Matches Norges Bank's 2026 list and SEB's 2024 and 2026. Built in mkt-data #130 |
| `DK` | Danish krone (Copenhagen) | None capturable. Checked against SEB's 2024 and 2026 lists | Rules, 1990–2100 (`DK-RULES`): the banks' closing days, Maundy Thursday, the day after Ascension, Constitution Day, Christmas Eve and New Year's Eve included, May 1 not; Great Prayer Day to 2023; never moved for a weekend. Built in mkt-data #130 (Bill, 2026-10-08: with Norway and Sweden) |

Each calendar's rules must reproduce its publisher's list exactly for every year both cover (as FED's and NYSE's did); a difference is fixed or cited before the calendar is used. History starts in 1990 (1999 for TARGET), the earliest a futures contract here is generated from (open question below). The rules engine (`app/calendars/rules.py`) needs a few additions: substitute days that move to the next free weekday (the UK's Christmas and Boxing Day pair), "the Monday on or before a date" (Victoria Day), and a fixed table of dates (Matariki, Japan's CSV years).

**Build order:** the rules engine additions (#117, done), then `CME-IR` and `CME-FX` (all the rates contracts need), then `GB`, `TARGET`, `JP` (the biggest FX contracts), then `CA`, `CH`, `AU`, `NZ`, `MX`, `SE` and `NO` to round out the G10, and `DK` with them (Bill, 2026-10-08). Each calendar is a PR in mkt-data (sources, rules, tests against its publisher) and, where needed, one in calendar-svc (registering the calendar); the Calendars screen and home-mcp's business-day tool pick them up with no change.

## Contracts (`secmaster-svc`)

- **Instruments:** types `fut_stir`, `fut_treasury` and `fut_fx` for each contract (one per product and contract month), generated from the seed's listing cycle as far back as each product's history and forward to everything currently listed.
- **Dates per contract**, derived from the rulebook with the rule recorded (the "derived" provenance from phase 3): first and last trading day; for the STIR contracts, the reference period the settlement rate is averaged or compounded over and the final settlement date; for the Treasury futures, first intention (position) day, first notice day, first and last delivery day; for the FX futures, last trading day and settlement (delivery) day. These need CME's business days, so this phase adds a **`CME` calendar** in calendar-svc built from rules with cited exceptions (like NYSE's), with CME's holiday notices read by hand as the check (not scraped, under CME's website terms).
- **Short names** (Bill, 2026-10-07): Bloomberg tickers with a two-digit year, `TYZ26`, `SFRH27`, `FFX26`, `USZ26`. Bloomberg itself writes `TYZ6` while a contract trades and `TYZ26` once it has expired; the two-digit form from the start means a name never changes. Identifiers per contract: Bloomberg's live ticker (`TYZ6 Comdty`, scheme `TICKER`, valid while listed) and FIGI from OpenFIGI (the key phase 3 already uses), and CME's code (`ZNZ6`, scheme `CME`, valid while listed). A product instrument is named by its root (`TY`).
- **Rolling aliases** like phase 3's on-the-run, named like Bloomberg's generics: `TY1`, `TY2` (front and second contract), with validity, so "the front 10-year future" on a past date resolves to that day's contract. A Treasury contract stops being the front on its first intention day, when positions roll (Bill, 2026-10-07), unlike Bloomberg's default `TY1`, which rolls at expiry; a STIR or FX contract is the front until its last trading day.
- **Status:** listed, trading, in delivery (Treasury futures, between first intention day and last delivery day), expired.

## Deliverable baskets and conversion factors (`secmaster-svc`)

Bill wants basket info for the bond futures (2026-10-07). It's reference data, not analytics: which securities a short may deliver, and the conversion factor each is invoiced at, are both fixed by CME's rules from the security's terms, and phase 3 already holds those terms for every Treasury since 1980.

- **Eligibility:** per product, an effective-dated rule in the seed: fixed-coupon notes and bonds only (no bills, TIPS, FRNs or STRIPS), with a limit on original term and a window of remaining term measured from a date in the delivery month (to first call for the old callable bonds). A security auctioned after a contract's listing joins its basket from its auction date (it's deliverable once issued), so a basket has history: `futures_deliverable` (contract, security, conversion factor, `valid_from`, rule version).
- **Conversion factor:** CME's published formula, the security's price per dollar of face at the notional coupon (6%; 8% before March 2000), with its remaining term rounded down to whole months or quarters as each product specifies, rounded to four decimals. Computed from phase 3's coupon and maturity; recorded with its rule like any derived term.
- **Check:** CME publishes conversion factor lookup tables and a calculator. Bill downloads the current contracts' tables once by hand; they become test fixtures that every computed basket and factor must match, with any difference explained (as with the TIPS reference CPIs). Not a scheduled download, under CME's website terms.
- **Deliverable supply:** each basket security's amount outstanding (from TreasuryDirect's auction records, less amounts stripped from MSPD) is already in secmaster-svc, so the basket can show the deliverable supply. The CTD and basis wait for analytics.

## Fixings

**Rates the STIR contracts settle on:** the New York Fed's reference rates API (free; terms of use recorded in step 1), new sources in mkt-data like phase 2's yields:

| Source | What | History |
|---|---|---|
| `NYFED-SOFR` | SOFR: rate, percentiles, volume | April 2018 |
| `NYFED-EFFR` | EFFR: rate, percentiles, volume, target range | 2000 on the API (H.15 has the older daily series) |
| `NYFED-SOFR-AVG` | SOFR Averages (30, 90, 180-day) and the SOFR Index | March 2020 |

Instruments `SOFR`, `EFFR`, `SOFR-AVG-30D`, `SOFR-AVG-90D`, `SOFR-AVG-180D`, `SOFR-INDEX` (type `rate_fixing`, a seed file like the CMTs), quotes in quote-svc as decimals (`0.0433` = 4.33%) per the Decimal rule. Phase 2 left fixings for later; the STIR contracts make them part of this phase.

**FX rates the FX futures track** (free, official, long histories):

| Source | What | History |
|---|---|---|
| `FRB-H10` | The Fed's H.10 daily nominal dollar indexes (broad, advanced foreign economies, emerging market economies), the Data Download Program's "Daily Indexes" package | January 2006 |
| `FRB-H10-RATES` | The Fed's H.10 daily rates: noon buying rates in New York, certified by the New York Fed, for each currency, the DDP's "Daily rates" package (series id from the DDP page, Bill 2026-10-08) | 1971 for most majors |
| `ECB-EXR` | The ECB's euro reference rates (about 30 currencies against the euro, set around 14:15 CET), through the ECB data portal's API | 1999 |

Instruments per source and pair, type `fx_fixing`, named by pair and source (`EURUSD-H10`, `USDJPY-H10`, `EURUSD-ECB`), each quoted in the source's own convention as printed (H.10 gives some currencies as dollars per unit, the rest as units per dollar; the ECB always units per euro), recorded on the instrument rather than inverted.

## Positioning: CFTC Commitments of Traders

The CFTC's Traders in Financial Futures report (TFF; futures only, and futures and options combined): weekly positions as of Tuesday, published Friday afternoon, long, short and spreading by trader category (dealers, asset managers, leveraged funds, other reportables, non-reportables), plus open interest, for each CFTC contract market code, CME's rates and FX futures included. Public, through the CFTC's Public Reporting Environment API (Socrata), history from 2006 for TFF (the legacy report goes back further; checked in step 1).

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
- **Fixings** (rates and FX) on charts like the CMTs; **positioning** as a weekly chart per product and trader category.
- **Voice:** home-mcp tools `mkt_data_future` (a contract or alias such as `TY1`: its dates and status) and `mkt_data_basket` (a contract's deliverables and conversion factors), so "what's in the December 10-year basket" works.

## Monitoring and alerts

The patterns from phases 2 and 3: stale-capture and parse alerts for the new sources (the Sources screen picks them up from mkt-data's catalog); fixings missing on a FED business day; a contract listed by the rules with no settlement on a CME business day (when there are prices); a basket check against the fixtures failing; CFTC's report late (it moves after federal holidays).

## Steps

1. **Raw capture first** (mkt-data): `NYFED-SOFR`, `NYFED-EFFR`, `NYFED-SOFR-AVG`, `FRB-H10`, `ECB-EXR` and `CFTC-TFF` captured daily (weekly for CFTC) and kept raw; read the first captures on the hub, record each source's terms and history depth, export fixtures. No price source this phase.
   - **Built (2026-10-07, mkt-data #110, deployed 2026-10-08 01:26 UTC):** `app/futures/sources.py`, seven sources kept raw (no parser yet): `NYFED-SOFR`, `NYFED-EFFR` and `NYFED-SOFR-AVG` (the New York Fed's reference rates API, JSON, by month), `FRB-H10` (the DDP's H.10 "Daily rates" package, CSV, by month), `ECB-EXR` (every euro reference rate, the ECB data portal's SDMX API, CSV, by month), and `CFTC-TFF` and `CFTC-TFF-COMBINED` (Traders in Financial Futures, futures only and with options, every market, Socrata CSV, by report date). A period with nothing published yet (the New York Fed's empty `refRates`, the ECB's 404, a CFTC answer with only its header) is a failed fetch marked `NOT_PUBLISHED`, never a capture. Job `POST /jobs/futures/{source}/capture?period=`. DAG `mkt_data__futures_sources_capture` (weekdays 7:45 p.m. New York; the months of the last ten days to yesterday, and the last two CFTC reports due) and manual `mkt_data__futures_sources_probe` (one sample period a year per source, for history depth). The Sources screen lists them as a new group, `futures`. Checked from here: the New York Fed's three endpoints (SOFR, EFFR and SOFRAI field names) and both CFTC datasets (TFF futures only `gpe5-46if`, combined `yw9f-hn96`); the H.10 package's series id and the ECB's answer are checked on the first captures.
   - **First captures (probe, 2026-10-08 01:29–01:39 UTC, captures #8069–#8248):** one June a year per source. The New York Fed: SOFR from 2018, EFFR from mid-2000 or 2001 (June 2000 empty, June 2001 there; a month grows from about 4 KB to 6 KB in 2016, likely when the New York Fed's percentiles and volume start), SOFR Averages and Index from 2020 (3.5 KB). ECB: every year from 1999, about 640 rows and 150–200 KB a month, one row per currency and day (`KEY`, `TIME_PERIOD`, `OBS_VALUE`, `OBS_STATUS`, `TITLE`, …). CFTC: both reports every sampled year from 2006, about 95 markets and 25–73 KB a report, each row with an `id` (report date, market code, F or C), the market's name and codes and every position column. FRB-H10 came back as the H.10 **Daily Indexes** package, not the rates: the series id from a 2018 link was that package's. The three dollar indexes start in 2006 (1971–2005 are headers only) and are kept as `FRB-H10`; the rates package is `FRB-H10-RATES` (its id read off the DDP page by Bill, 2026-10-08). The DDP also answered empty to every other request, so its fetch now waits and asks again. The probe failed at its end only because it asked for EFFR in 1999, before the source's first period (fixed). The daily DAG ran once on unpausing (2026-10-07's run) and worked.
   - **H.10 rates (mkt-data #111, deployed 2026-10-08 12:36 UTC; probe 12:38, captures #8259 on):** `FRB-H10-RATES` is the right package: 23 currencies (AUD, EUR, NZD, GBP, BRL, CAD, CNY, DKK, HKD, INR, JPY, MYR, MXN, NOK, ZAR, SGD, KRW, LKR, SEK, CHF, TWD, THB, VEB), six header lines (description, unit, multiplier, currency, unique identifier, series code) then one row per business day, `ND` for no data and an empty cell before a series starts. Series codes say the quoting: `RXI$US_N.B.xx` is dollars per unit (AUD, EUR, NZD, GBP), `RXI_N.B.xx` units per dollar (the rest). June 1971 has ten currencies (AUD, NZD, GBP, CAD, DKK, JPY, MYR, NOK, SEK, CHF); the euro starts in 1999 and the package carries no legacy currencies (no Deutsche mark or French franc). About 5–6 KB a month. The DDP's empty answers were all absorbed by the fetch's retry: no failed checks.
2. **Calendars, then products and contracts** (mkt-data, calendar-svc, secmaster-svc): the calendars first (done, #117–#131); then, in secmaster-svc:
   - **2a.** The product seed (`seeds/futures.toml`) for the main 20, every spec cited and effective-dated; the contract generator (pure: product rules plus calendar-svc's closed days, fetched once per calendar through `Closes`); a `futures_contract` table with each contract's dates and the rule behind each; short names (`TYZ26`), CME codes (`ZNZ6`) and the generics (`TY1`, `TY2`) as identifiers with validity. Checked against CME's rulebook and listings on a handful of known contracts.
     - **Deployed (2026-10-08, secmaster-svc #20):** `seeds/futures.toml` (the 20 products, specs verbatim from the reference doc with each page's URL, listing cycles, date rules each with its source, history starts with theirs), `app/futures.py` (pure generator), `app/futures_load.py` (products as `fut_product` instruments named by root; contracts `fut_treasury`/`fut_stir`/`fut_fx` named `TYZ26`, dates in `futures_contract` with the rule behind each; CME codes valid while listed; generics `TY1` as `GENERIC` identifiers, resolvable as of a date), migration 0007, a calendar-svc client, `POST /jobs/futures` and the daily DAG `secmaster_svc__futures` (00:12 New York). Checked by hand on a 2026 calendar: ZNZ6 last trading Dec 21, first intention and notice Nov 27 and 30; ZTZ6 last delivery Jan 6; SR3Z6 Dec 15 with reference quarter Sep 16 to Dec 16; ZQV6 final settlement Nov 2; 6EZ6 Dec 14, settling Dec 16; 6CZ6 Dec 15; TBF3Z6 Dec 14; ZT's listed contracts match CME's quotes page. History: from launch where a source dates it (UB 2010-01-11, TN 2016-01-11, TWE 2022-03-07, SR1 and SR3 2018-05-07, TBF3 2023-10-02; Z3N from its 2020-07-13 redesign), from 1990 for the older products (1999 for the euro), and only today's listings for ZT, 6M and 6N until their launches are found. A first trading day is derived only for contracts listed today (replaying today's cycle); serial months are kept only while listed. On the hub, run against the real calendars (2026-10-08): 20 products, 2,401 contracts (372 listed), 12,222 generic intervals. Listed counts match CME's spec pages (Treasuries 3, ZQ 60, SR1 25, SR3 45, TBF3 6, the FX majors 31, 6S 20, 6N 6), fronts are right (TYZ26, SFRV26, ECV26), and a second run changed nothing.
   - **2b.** Bloomberg roots confirmed and FIGIs and live tickers through OpenFIGI (the phase 3 job, extended).
     - **Deployed (2026-10-08, secmaster-svc #21):** each listed contract is asked twice in one request, by our ticker (`TYZ6`) and by CME's code (`ZNZ6`, `ID_EXCH_SYMBOL`). If they agree (or only the ticker is found), the contract keeps its FIGI and Bloomberg's live ticker (`TYZ6 Comdty`, scheme `TICKER`, valid while its CME code is). If CME's code maps to another root, nothing is stored and Bloomberg's root is reported. Answers go in `futures_figi_lookup`; the job is `POST /jobs/futures-figi`, the futures DAG's second task. To do after deploy: read the hub run's per-product report, then set `root_confirmed` (and fix any root) in `seeds/futures.toml` in a reviewed PR.
     - **First run (2026-10-08):** 338 of 372 listed contracts matched by ticker. Names checked by eye: the Treasury futures ("US 10YR NOTE (CBT)"), ZQ, SR1 ("1 MONTH SOFR FUT", so SER is right), SR3, TBF3, 6J, 6A, 6C, 6S and 6M are right. **BP, EC and NV were wrong:** BPV6, ECV6 and NVZ6 under Comdty are soybean, crude and heating oil futures, since Bloomberg's FX futures are under Curncy. Not found: TWEA (3) and SFR from 2029 out (30). CME's code (`ID_EXCH_SYMBOL`) matched nothing.
     - **Fix (secmaster-svc #22, deployed):** ticker lookups in the product's market sector, two-digit-year tickers too, every lookup re-checked, and wrong matches' FIGIs and tickers retired by the job. The log now shows what OpenFIGI said for anything not found.
     - **Second run (2026-10-08):** 366 of 372 confirmed. Every product's example is right: the pound, euro and New Zealand dollar under Curncy (CME), the Treasury futures and ZQ under Comdty (CBT), SR1, SR3 and TBF3 under Comdty (CME). The wrong matches were retired, including some AD contracts that the first run had matched to Index-sector futures (`ADH8 Index`). Not found: TWEA (none of `TWEAZ6`, `TWEAZ26`; Bloomberg's root for the 20-year is still unknown), SFR's April and May 2027 serials (`SFRJ7`, `SFRK7`), and 6C's February 2027 (`CDG7`). CME's code (`ID_EXCH_SYMBOL`) is never found. **Then (2026-10-08):** #23's tally showed every product's listed contracts are one future, so secmaster-svc #24 sets `root_confirmed` for 19 products (not TWEA). CME's quotes pages, read by hand: 6CG7 and SR3J7 are listed (OpenFIGI just lacks them). **SR3 was dated a quarter off:** CME still lists the Jul, Aug and Sep 2026 contracts, so it names a contract by the month its reference quarter starts (SR3U6: Sep 16 to Dec 16, last trading Dec 15). Step 2a read "delivery month" as the contract month. CME also lists 7 SR3 serials (not 6) and 3 TBF3 serials (not 2). Fixed in secmaster-svc #25, which also gives contracts the rules stop generating a status (expired, or withdrawn). On the hub after deploy: 79 SFR contracts redated, SFRN26, SFRQ26, SFRU26 and TZRF27 created, SFRK27 and SFRM36 withdrawn, 46 SFR and 7 TZR listed. OpenFIGI then found SFRN6 as "3 MONTH SOFR FUT Jul26", which confirms CME's naming. Not found at OpenFIGI (all listed at CME): CDG7, SFRJ7, TZRF7. **Still to do:** re-check the serial windows after SR3N6 and TBF3V6 expire (Oct 19–20); find TWE's Bloomberg root.
   - **2c.** The FX crosses and the E-micro FX and Treasury futures (seed rows; the generator as it stands).
   - **2d.** The emerging-market FX futures: each currency's calendar in mkt-data and calendar-svc, then its seed rows.
3. **Baskets and conversion factors** (secmaster-svc): eligibility rules, `futures_deliverable` with history, conversion factors; checked against CME's lookup tables (Bill's one-off download as fixtures) for every currently listed Treasury contract.
4. **Fixings** (mkt-data near-raw, secmaster-svc seed, quote-svc): SOFR, EFFR, the SOFR averages and index, H.10 and the ECB's rates, backfilled to each source's start.
5. **Positioning** (mkt-data, secmaster-svc product instruments, quote-svc): TFF backfilled from 2006.
6. **Schedule and monitoring:** DAGs, Assets, metrics, alerts.
7. **Screens and voice:** Futures screen, basket view, fixings and positioning charts, home-mcp tools.

## Decisions (Bill, 2026-10-07)

- **Scope:** every rates and FX future CME lists, data only, no analytics; the bond futures' deliverable baskets included; FX fixings from the Fed's H.10 and the ECB. Non-US rates futures later, with their government bonds; energy later, likely phase 5.
- **Prices:** none this phase; settlements, volume and open interest later, from a licensed source.
- **Short names:** Bloomberg tickers with a two-digit year (`TYZ26`), generics `TY1`/`TY2`; Bloomberg's live ticker, FIGI and CME's code (`ZNZ6`) as identifiers.
- **Front-contract roll:** Treasury futures at first intention day; STIR and FX at last trading day.
- **History (2026-10-08):** contracts from 1990, or from a product's launch if later (the euro from 1999), the calendars' start.
- **More products (2026-10-08):** beyond the main 20, the FX crosses, the E-micro FX and Treasury futures, and the emerging-market FX futures (each of those needs its own country calendar first).

## Open questions

- Which city each FX calendar follows where a country has several (Sydney for Australia, Toronto for Canada, Zurich for Switzerland, New Zealand's national calendar, since ESAS settles on the anniversary days: settled in #129).
- ~~The FX contracts' calendars~~: settled. Every delivery country has one (above), 1990 on (1999 for TARGET), built in mkt-data #118–#131.
- The `CME` calendar's early closes and Good Friday sessions (CME has traded rates futures on some Good Fridays when payrolls were released).

## Later (not this phase)

- Settlements, volume and open interest, from a licensed source (above); then Databento's license for historical CME statistics on a personal platform, and whether history before its 2010 start matters.
- CTD, implied repo, basis, futures-implied rates and a SOFR curve from futures: the analytics build-out ([analytics-later.md](analytics-later.md)).
- **Non-US rates futures with their government bonds** (Eurex Bund, Bobl, Schatz and Buxl; ICE gilts, SONIA and Euribor; €STR futures): each needs its own holiday calendar (TARGET2, UK) and, for its baskets, that country's government bonds in secmaster-svc, a phase-3-sized job per country. Both debt offices publish their bond lists free (Germany's Finanzagentur, the UK Debt Management Office).
- **Energy, likely phase 5** (Bill, 2026-10-07: wait): CME and ICE energy futures, built on this phase's machinery (contracts from rules, calendars, CFTC capture), with the CFTC's disaggregated report and the EIA's free API for daily spot prices (WTI, Brent, Henry Hub, products; a free key in SSM).
- Options on futures, intraday data.

## Sources consulted (2026-10-07)

- CME, [Access to settlement data FAQ](https://www.cmegroup.com/articles/faqs/access-to-cme-group-settlement-data-faq.html), [market data disclaimer](https://www.cmegroup.com/trading/market-data-explanation-disclaimer.html), [website terms of use](https://www.cmegroup.com/tools-information/cme-website-terms-of-use-new.html)
- CME, [Calculating U.S. Treasury futures conversion factors](https://www.cmegroup.com/trading/interest-rates/files/Calculating_U.S.Treasury_Futures_Conversion_Factors.pdf), [conversion factor lookup tables](https://www.cmegroup.com/trading/interest-rates/us-treasury-futures-conversion-factor-lookup-tables.html), [10-year delivery basket change (2022)](https://www.cmegroup.com/news/2022/proposed-enhancements-to-10-year-delivery-basket-us-treasury.html)
- Databento, [GLBX.MDP3](https://databento.com/datasets/GLBX.MDP3), [pricing](https://databento.com/pricing), [retrieving open interest and settlement prices](https://databento.com/docs/examples/futures/retrieving-oi-and-settlement-prices)
- CFTC, [Commitments of Traders report descriptions](https://www.cftc.gov/node/128971)
