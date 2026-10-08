# CME Group contract specifications — October 2026

Reference copy of CME Group contract specifications for the products the market data platform tracks. Every page was opened and read by hand, one page at a time, in a browser on 2026-10-08. No scripts, no JSON endpoints, no downloads.

> **Status: partial.** 15 emerging-market FX products have not been read yet. They are listed at the end of section 5.

## How to read this file

- Every value in the right-hand column is copied verbatim from the CME page, including CME's own typos (marked "(sic)" where they could look like transcription errors). Line breaks on the page are shown as `<br>`.
- "not shown" means the page did not display that field. Nothing was filled in from memory or other sources.
- **Clearing code** is the value after "Clearing:" in the page's PRODUCT CODE field. Other codes in that field (ClearPort, TAS, BTIC) are under "Other codes shown".
- **Vendor codes.** The specs pages only link to CME's "Quote Vendor Symbols Listing", which was not followed. Where the product's Overview page has its own vendor-codes table, the Bloomberg and Refinitiv codes from it are recorded and the Overview page is cited.
- **Settlement procedures.** Where the page only shows a link title, the title is recorded with "(link)". The linked documents were not opened.
- **Launch / first trade date.** No product's specs or Overview page showed one.
- **Citation.** Each product ends with the page URL(s) and the read date. Several URLs redirect from `<product>.contractSpecs.html` to `<product>/specs`; the final URL is cited.
- **Product universe.** FX products come from CME's FX Product Guide (https://www.cmegroup.com/markets/fx/fx-product-guide) and the FX product menu on cmegroup.com, both read 2026-10-08.

## Contents

1. Rates
2. G10 FX
3. E-micros (Micro Treasury, Treasury Yield and Micro FX futures)
4. FX cross rates
5. Emerging-market FX

## 1. Rates

### 2-Year T-Note Futures (ZT)

| Field | As shown on the page |
|---|---|
| Product name | 2-Year T-Note Futures |
| CME Globex code | ZT |
| Clearing code | 26 |
| Other codes shown | CME ClearPort: 26; TAS: ZTT |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab with a vendor-codes table) |
| Contract unit | Face value at maturity of $200,000 |
| Minimum price fluctuation | 1/8 of 1/32 of one point (0.00390625) = $7.8125<br>TAS: Zero or +/- 4 ticks in the minimum tick increment of the outright |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 3 consecutive quarters<br>TAS: A new TAS month will be listed on the 15th calendar day 3 months prior to the first day of the delivery month. Two TAS months (and corresponding calendar spread) will be supported for the two weeks prior to the nearer month's expiration. |
| Termination of trading | Trading terminates at 12:01 p.m.CT  on the last business day of the contract month<br>TAS:Trading terminates at 2:00 p.m.CT on the last business day of the calendar month preceding the contract month |
| Settlement method | Deliverable |
| Settlement procedures | Treasury Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m.ET (5:00 p.m. - 4:00 p.m. CT).  Monday - Thursday 5:00 p.m. - 6:00 p.m. ET (4:00 p.m. - 5:00 p.m. CT) daily maintenance period.<br>TAS: Sunday - Friday 6:00 p.m. - 3:00 p.m. ET (5:00 p.m. - 2:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT<br>TAS: Sunday 5:00 p.m. (6:00 p.m. ET) - Friday 2:00 p.m. - (3:00 p.m. ET) with a pause from 2:00 p.m. - 6:00 p.m. CT (3:00 p.m. - 7:00 p.m. ET), Monday - Thursday |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/interest-rates/us-treasury/2-year-us-treasury-note.contractSpecs.html — read 2026-10-08

### 3-Year T-Note Futures (Z3N)

| Field | As shown on the page |
|---|---|
| Product name | 3-Year T-Note Futures |
| CME Globex code | Z3N |
| Clearing code | 3YR |
| Other codes shown | CME ClearPort: 3YR |
| Vendor codes (Bloomberg / Refinitiv) | Specs page: not shown (links to "Quote Vendor Symbols Listing"). Overview page vendor-codes table (outright): Bloomberg 3Y; Refinitiv Globex RIC Root 1Y; Refinitiv Composite RIC Root YR |
| Contract unit | Face value at maturity of $200,000 |
| Minimum price fluctuation | 1/8 of 1/32 of a point (0.00390625) = $7.8125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 3 consecutive quarters |
| Termination of trading | Trading terminates at 12:01 p.m. CT, on the last business day of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Treasury Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m.ET (5:00 p.m. - 4:00 p.m. CT).  Monday - Thursday 5:00 p.m. - 6:00 p.m. ET (4:00 p.m. - 5:00 p.m. CT) daily maintenance period.<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/us-treasury/3-year-us-treasury-note.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/us-treasury/3-year-us-treasury-note.html (overview, vendor codes) — read 2026-10-08

### 5-Year T-Note Futures (ZF)

| Field | As shown on the page |
|---|---|
| Product name | 5-Year T-Note Futures |
| CME Globex code | ZF |
| Clearing code | 25 |
| Other codes shown | CME ClearPort: 25; TAS: ZFT |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; overview page has no vendor-codes table) |
| Contract unit | Face value at maturity of $100,000 |
| Minimum price fluctuation | 1/4 of 1/32 of one point (0.0078125) = $7.8125<br>TAS: Zero or +/- 4 ticks in the minimum tick increment of the outright<br>Calendar Spread: 1/8 of 1/32 of one point (0.00390625) = $3.90625 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 3 consecutive quarters<br>TAS:  A new TAS month will be listed on the 15th calendar day 3 months prior to the first day of the delivery month. Two TAS months (and corresponding calendar spread) will be supported for the two weeks prior to the nearer month's expiration. |
| Termination of trading | Trading terminates at 12:01 p.m.CT  on the last business day of the contract month<br>TAS:Trading terminates at 2:00 p.m.CT on the last business day of the calendar month preceding the contract month |
| Settlement method | Deliverable |
| Settlement procedures | Treasury Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>TAS: Sunday - Friday 5:00 p.m. - 2:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. – 6:00 p.m. CT<br>TAS: Sunday 5:00 p.m. - Friday 2:00 p.m. - with a pause from 2:00 p.m. - 6:00 p.m. CT, Monday - Thursday |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/us-treasury/5-year-us-treasury-note.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/us-treasury/5-year-us-treasury-note.html (overview) — read 2026-10-08

### 10-Year T-Note Futures (ZN)

| Field | As shown on the page |
|---|---|
| Product name | 10-Year T-Note Futures |
| CME Globex code | ZN |
| Clearing code | 21 |
| Other codes shown | CME ClearPort: 21; TAS: ZNS |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; overview page has no vendor-codes table) |
| Contract unit | Face value at maturity of $100,000 |
| Minimum price fluctuation | Outright:<br>1/2 of 1/32 of one point (0.015625) = $15.625<br>TAS: Zero or +/- 4 ticks in the minimum tick increment of the outright<br>CALENDAR SPREAD<br>1/4 of 1/32 of one point (0.0078125) = $7.8125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 3 consecutive quarters<br>New contract months become TAS eligible on the 15th day 3 months prior to the first day of the contract month. Two TAS months (and corresponding calendar spread) are supported for the two weeks prior to the nearer month's termination. |
| Termination of trading | Trading terminates at 12:01 p.m. CT, 7 business days prior to the last business day of the contract month.<br>TAS trading terminates at 2:00 p.m.CT on the last business day of the month prior to the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Treasury Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>TAS: Sunday - Friday 5:00 p.m. - 2:00 p.m. CT (6:00 p.m. - 3:00 p.m. ET)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. – 6:00 p.m. CT<br>TAS: Sunday 5:00 p.m. - Friday 2:00 p.m. - with a pause from 2:00 p.m. - 6:00 p.m. CT, Monday - Thursday |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/us-treasury/10-year-us-treasury-note.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/us-treasury/10-year-us-treasury-note.html (overview) — read 2026-10-08

### Ultra 10-Year U.S. Treasury Note Futures (TN)

| Field | As shown on the page |
|---|---|
| Product name | Ultra 10-Year U.S. Treasury Note Futures |
| CME Globex code | TN |
| Clearing code | TN |
| Other codes shown | CME ClearPort: TN; TAS: TNT |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; overview page has no vendor-codes table) |
| Contract unit | Face value at maturity of $100,000 |
| Minimum price fluctuation | Outright:<br>1/2 of 1/32 of one point (0.015625) = $15.625<br>TAS: Zero or +/- 4 ticks in the minimum tick increment of the outright<br>CALENDAR SPREAD<br>1/4 of 1/32 of one point (0.0078125) = $7.8125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, and Dec) listed for 3 consecutive quarters.<br>TAS becomes available for a new contract month on the 15th day 3 months prior to the first day of the contract month. Two TAS months (and corresponding calendar spread) are supported for the two weeks prior to the nearer month's termination. |
| Termination of trading | Trading terminates at 12:01 p.m. CT, 7 business days prior to the last business day of the contract month.<br>TAS trading terminates at 2:00 p.m.CT on the last business day of the month prior to the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT (6:00 p.m. - 5:00 p.m.ET).  Monday - Thursday 4:00 p.m. - 5:00 p.m. CT (5:00 p.m. - 6:00 p.m. ET) daily maintenance period.<br>TAS: Sunday - Friday 5:00 p.m. - 2:00 p.m. CT (6:00 p.m. - 3:00 p.m. ET)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT<br>TAS: Sunday 5:00 p.m. (6:00 p.m. ET) - Friday 2:00 p.m. - (3:00 p.m. ET) with a pause from 2:00 p.m. - 6:00 p.m. CT (3:00 p.m. - 7:00 p.m. ET), Monday - Thursday |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/us-treasury/ultra-10-year-us-treasury-note.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/us-treasury/ultra-10-year-us-treasury-note.html (overview) — read 2026-10-08

### 20-Year U.S. Treasury Bond Futures (TWE)

| Field | As shown on the page |
|---|---|
| Product name | 20-Year U.S. Treasury Bond Futures |
| CME Globex code | TWE |
| Clearing code | TWE |
| Other codes shown | CME ClearPort: TWE |
| Vendor codes (Bloomberg / Refinitiv) | Specs page: not shown (links to "Quote Vendor Symbols Listing"). Overview page "Vendor trading codes" table, 20-Year T-Bond Futures row: Bloomberg TWEA; Refinitiv ZP |
| Contract unit | Face value at maturity of $100,000 |
| Minimum price fluctuation | Outright:<br>1/32 of one point (0.03125) = $31.25<br>CALENDAR SPREAD<br>1/4 of 1/32 of one point (0.0078125) = $7.8125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 3 consecutive quarters |
| Termination of trading | Trading terminates at 12:01 p.m. CT, 7 business days prior to the last business day of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Treasury Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/us-treasury/20-year-us-treasury-bond.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/us-treasury/20-year-us-treasury-bond.html (overview) — read 2026-10-08

### U.S. Treasury Bond Futures (ZB)

| Field | As shown on the page |
|---|---|
| Product name | U.S. Treasury Bond Futures |
| CME Globex code | ZB |
| Clearing code | 17 |
| Other codes shown | CME ClearPort: 17; TAS: ZBT |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; overview page has no vendor-codes table) |
| Contract unit | Face value at maturity of $100,000 |
| Minimum price fluctuation | Outright:<br>1/32 of one point (0.03125) = $31.25<br>TAS: Zero or +/- 4 ticks in the minimum tick increment of the outright<br>CALENDAR SPREAD<br>1/4 of 1/32 of one point (0.0078125) = $7.8125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 3 consecutive quarters<br>TAS becomes available for a new contract month on the 15th day 3 months prior to the first day of the contract month. Two TAS months (and corresponding calendar spread) are supported for the two weeks prior to the nearer month's termination. |
| Termination of trading | Trading terminates at 12:01 p.m. CT, 7 business days prior to the last business day of the contract month.<br>TAS trading terminates at 2:00 p.m.CT on the last business day of the month prior to the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Treasury Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT (6:00 p.m. - 5:00 p.m.ET).  Monday - Thursday 4:00 p.m. - 5:00 p.m. CT (5:00 p.m. - 6:00 p.m. ET) daily maintenance period.<br>TAS: Sunday - Friday 5:00 p.m. - 2:00 p.m. CT (6:00 p.m. - 3:00 p.m. ET)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT<br>TAS: Sunday 5:00 p.m. (6:00 p.m. ET) - Friday 2:00 p.m. - (3:00 p.m. ET) with a pause from 2:00 p.m. - 6:00 p.m. CT (3:00 p.m. - 7:00 p.m. ET), Monday - Thursday |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/us-treasury/30-year-us-treasury-bond.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/us-treasury/30-year-us-treasury-bond.html (overview) — read 2026-10-08

### Ultra U.S. Treasury Bond Futures (UB)

| Field | As shown on the page |
|---|---|
| Product name | Ultra U.S. Treasury Bond Futures |
| CME Globex code | UB |
| Clearing code | UBE |
| Other codes shown | CME ClearPort: UBE; TAS: UBT |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab with a vendor-codes table) |
| Contract unit | Face value at maturity of $100,000 |
| Minimum price fluctuation | Outright:<br>1/32 of a point (0.03125) = $31.25<br>TAS: Zero or +/- 4 ticks in the minimum tick increment of the outright<br>CALENDAR SPREAD<br>1/4 of 1/32 of a point (0.0078125) = $7.8125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 3 consecutive quarters<br>TAS becomes available for a new contract month on the 15th day 3 months prior to the first day of the contract month. Two TAS months (and corresponding calendar spread) are supported for the two weeks prior to the nearer month's termination. |
| Termination of trading | Trading terminates at 12:01 p.m. CT, 7 business days prior to the last business day of the contract month.<br>TAS trading terminates at 2:00 p.m.CT on the last business day of the month prior to the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Treasury Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT (6:00 p.m. - 5:00 p.m.ET).  Monday - Thursday 4:00 p.m. - 5:00 p.m. CT (5:00 p.m. - 6:00 p.m. ET) daily maintenance period.<br>TAS: Sunday - Friday 5:00 p.m. - 2:00 p.m. CT (6:00 p.m. - 3:00 p.m. ET)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT<br>TAS: Sunday 5:00 p.m. (6:00 p.m. ET) - Friday 2:00 p.m. - (3:00 p.m. ET) with a pause from 2:00 p.m. - 6:00 p.m. CT (3:00 p.m. - 7:00 p.m. ET), Monday - Thursday |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/interest-rates/us-treasury/ultra-t-bond.contractSpecs.html — read 2026-10-08

### 30 Day Federal Funds Futures (ZQ)

| Field | As shown on the page |
|---|---|
| Product name | 30 Day Federal Funds Futures |
| CME Globex code | ZQ |
| Clearing code | 41 |
| Other codes shown | CME ClearPort: 41 |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; overview page has no vendor-codes table) |
| Contract unit | $4,167 x Contract IMM Index |
| Minimum price fluctuation | 1/2 of one basis point (0.005) = $20.835<br>Beginning at 5:00 p.m. CT on the Sunday preceding the first business day of the spot month: 1/4 of one basis point (0.0025) = $10.4175 |
| Listed contracts | Monthly contracts listed for 60 consecutive months |
| Termination of trading | Trading terminates on the last business day of the contract month. |
| Settlement method | Financially Settled |
| Settlement procedures | Expiring contracts are cash settled against the average daily Fed Funds overnight rate for the delivery month, rounded to the nearest one-tenth of one basis point. Final settlement occurs on the first business day following the last trading day. The daily Fed Funds overnight rate is calculated and reported by the Federal Reserve Bank of New York.<br>Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m.ET (5:00 p.m. - 4:00 p.m. CT).  Monday - Thursday 5:00 p.m. - 6:00 p.m. ET (4:00 p.m. - 5:00 p.m. CT) daily maintenance period.<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/stirs/30-day-federal-fund.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/stirs/30-day-federal-fund.html (overview) — read 2026-10-08

### One-Month SOFR Futures (SR1)

| Field | As shown on the page |
|---|---|
| Product name | One-Month SOFR Futures |
| CME Globex code | SR1 |
| Clearing code | SR1 |
| Other codes shown | CME ClearPort: SR1 |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab with a vendor-codes table) |
| Contract unit | $4,167 x contract-grade IMM Index |
| Minimum price fluctuation | Nearby delivery month:  0.0025 IMM index points (¼ basis point per annum) = $10.4175<br>All other delivery months: 0.005 IMM index points (½ basis point per annum) = $20.835<br>Min final settle fluctuation: 0.001 IMM index points |
| Listed contracts | Monthly contracts listed for 25 consecutive months |
| Termination of trading | Trading terminates on the last business day of the contract month. |
| Settlement method | Financially Settled |
| Settlement procedures | SR1 Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. (6:00 p.m. - 5:00 p.m. ET) with a 60-minute break each day beginning at 4:00 p.m. (5:00 p.m. ET)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/interest-rates/stirs/one-month-sofr.contractSpecs.html — read 2026-10-08

### Three-Month SOFR Futures (SR3)

| Field | As shown on the page |
|---|---|
| Product name | Three-Month SOFR Futures |
| CME Globex code | SR3 |
| Clearing code | SR3 |
| Other codes shown | CME ClearPort: SR3 |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; overview page has no vendor-codes table) |
| Contract unit | $2,500 x contract-grade IMM Index |
| Minimum price fluctuation | All contract months with four months or less until last day of trading (as defined in Rulebook section 46002.C): 0.0025 IMM Index points (¼ basis point per annum) = $6.25<br>All other contract months: 0.005 IMM Index points (½ basis point per annum) = $12.50<br>Min Final Settle Fluctuation: 0.0001 IMM Index points |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 39 consecutive quarters and the nearest 6 serial contract months |
| Termination of trading | Trading terminates on the business day prior to the 3rd Wednesday of contract delivery month. |
| Settlement method | Financially Settled |
| Settlement procedures | SR3 Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. (6:00 p.m. - 5:00 p.m. ET) with a 60-minute break each day beginning at 4:00 p.m. (5:00 p.m. ET)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/stirs/three-month-sofr.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/stirs/three-month-sofr.html (overview) — read 2026-10-08

### U.S. T-Bill Futures — 13-Week U.S. Treasury Bill (TBF3)

| Field | As shown on the page |
|---|---|
| Product name | U.S. T-Bill Futures (overview text calls it "13-Week U.S. Treasury Bill futures") |
| CME Globex code | TBF3 |
| Clearing code | TBF3 |
| Other codes shown | CME ClearPort: TBF3 |
| Vendor codes (Bloomberg / Refinitiv) | Specs page: not shown (links to "Quote Vendor Symbols Listing"). Overview page "Vendor Codes" table (outrights): Bloomberg TZR; Refinitiv TB3F. (SOFR-TBILL ICS column: Bloomberg SFRTZR Comdty; Refinitiv SRA-TB3F) |
| Contract unit | $2,500 x contract-grade IMM Index |
| Minimum price fluctuation | All contract months with one month or less until last day of trading (as defined in Rulebook section 45702.G): 0.0025 IMM Index points (¼ basis point per annum) = $6.25<br>All other contract months: 0.005 IMM Index points (½ basis point per annum) = $12.50<br>Min Final Settle Fluctuation: 0.001 IMM Index points |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 4 consecutive quarters and the nearest 2 serial contract months |
| Termination of trading | Trading terminates on the Monday prior to the 3rd Wednesday of contract month. If Monday is not a business day, then trading terminates on the next immediate business day. |
| Settlement method | Financially Settled |
| Settlement procedures | CME 13-Week U.S. Treasury Bill Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. (6:00 p.m. - 5:00 p.m. ET) with a 60-minute break each day beginning at 4:00 p.m. (5:00 p.m. ET)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/stirs/us-t-bill.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/stirs/us-t-bill.html (overview, vendor codes) — read 2026-10-08. Note: the requested URL path `/us-treasury/13-week-us-treasury-bill.contractSpecs.html` returned 404; the product lives under `/stirs/us-t-bill`.

## 2. G10 FX

### Euro FX Futures (6E)

| Field | As shown on the page |
|---|---|
| Product name | Euro FX Futures |
| CME Globex code | 6E |
| Clearing code | EC |
| Other codes shown | CME ClearPort: EC; BTIC: 6EB |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; overview page has no vendor-codes table) |
| Contract unit | 125,000 Euro |
| Minimum price fluctuation | CME Globex:<br>0.000050 per Euro increment = $6.25<br>BTIC: 0.000005 per Euro increment = $0.625<br>Spreads: 0.00002 per Euro increment = $2.50<br>Final Settlement: 0.00005<br>CME ClearPort:<br>0.000010 per Euro increment = $1.25<br>BTIC: 0.000001 per Euro increment = $0.125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 20 consecutive quarters and serial contracts listed for 16 months |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the third Wednesday of the contract month.<br>BTIC: Trading terminates at 3:40pm London time (9:40am CT) one business day prior to futures last trade date. |
| Settlement method | Deliverable |
| Settlement procedures | Physical Delivery<br>EUR/USD Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>BTIC: Sunday - Friday 5:00 p.m. - 4:00 p.m. CT with a trading close from 3:40 p.m. - 4:30 p.m. London time (9:40 a.m. - 10:30 a.m. CT)  and a 60-minute break each day beginning at 4:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT<br>BTIC: Sunday - Friday 5:00 p.m. - 5:45p.m. CT with a trading halt 9:40 a.m. to 11:30 a.m. CT, and with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/fx/g10/euro-fx/specs (specs) and https://www.cmegroup.com/markets/fx/g10/euro-fx (overview) — read 2026-10-08

### Japanese Yen Futures (6J)

| Field | As shown on the page |
|---|---|
| Product name | Japanese Yen Futures |
| CME Globex code | 6J |
| Clearing code | J1 |
| Other codes shown | CME ClearPort: J1 |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; overview page has no vendor-codes table) |
| Contract unit | 12,500,000 Japanese yen |
| Minimum price fluctuation | CME Globex:<br>0.0000005 per JPY increment = $6.25<br>Spreads: 0.0000002 per JPY increment = $2.50<br>Final Settlement: 0.0000005<br>CME ClearPort:<br>0.0000001 per JPY increment = $1.25 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 20 consecutive quarters and serial contracts listed for 16 months |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Physical Delivery<br>JPY/USD Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. (6:00 p.m. - 5:00 p.m. ET) with a 60-minute break each day beginning at 4:00 p.m. (5:00 p.m. ET)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or overview) |

Sources: https://www.cmegroup.com/markets/fx/g10/japanese-yen/specs (specs) and https://www.cmegroup.com/markets/fx/g10/japanese-yen (overview) — read 2026-10-08

### British Pound Futures (6B)

| Field | As shown on the page |
|---|---|
| Product name | British Pound Futures |
| CME Globex code | 6B |
| Clearing code | BP |
| Other codes shown | CME ClearPort: BP |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; Overview page has no vendor-codes table) |
| Contract unit | 62,500 British pounds |
| Minimum price fluctuation | CME Globex:<br>0.0001 per GBP increments = $6.25<br>Spreads: .000025 per GBP increment = $1.5625<br>Final Settlement: 0.0001<br>CME ClearPort:<br>0.00001 per GBP increment = $0.625 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 20 consecutive quarters and serial contracts listed for 16 months |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business days prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Physical Delivery<br>GBP/USD Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or Overview) |

Sources: https://www.cmegroup.com/markets/fx/g10/british-pound/specs (specs) and https://www.cmegroup.com/markets/fx/g10/british-pound (overview) — read 2026-10-08

### Australian Dollar Futures (6A)

| Field | As shown on the page |
|---|---|
| Product name | Australian Dollar Futures |
| CME Globex code | 6A |
| Clearing code | AD |
| Other codes shown | CME ClearPort: AD |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; Overview page has no vendor-codes table) |
| Contract unit | 100,000 Australian dollars |
| Minimum price fluctuation | CME Globex:<br>0.00005 per AUD increment = $5.00<br>Spreads: 0.00002 per AUD increment = $2.00<br>Final Settlement: 0.00005<br>CME ClearPort:<br>0.00001 per AUD increment = $1.00 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 20 consecutive quarters and serial contracts listed for 16 months |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business days prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Physical Delivery<br>AUD/USD Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT (with a 60-minute break each day beginning at 4:00 p.m.CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or Overview) |

Sources: https://www.cmegroup.com/markets/fx/g10/australian-dollar/specs (specs) and https://www.cmegroup.com/markets/fx/g10/australian-dollar (overview) — read 2026-10-08

### Canadian Dollar Futures (6C)

| Field | As shown on the page |
|---|---|
| Product name | Canadian Dollar Futures |
| CME Globex code | 6C |
| Clearing code | C1 |
| Other codes shown | CME ClearPort: C1 |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; Overview page has no vendor-codes table) |
| Contract unit | 100,000 Canadian dollars |
| Minimum price fluctuation | CME Globex:<br>0.00005 per CAD increment = $5.00<br>Spreads: 0.00002 per CAD increment = $2.00<br>Final Settlement: 0.00005<br>CME ClearPort:<br>0.00001 per CAD increment = $1.00 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 20 consecutive quarters and serial contracts listed for 16 months |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 1 business day prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Physical Delivery<br>Canadian Dollar Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or Overview) |

Sources: https://www.cmegroup.com/markets/fx/g10/canadian-dollar/specs (specs) and https://www.cmegroup.com/markets/fx/g10/canadian-dollar (overview) — read 2026-10-08

### Swiss Franc Futures (6S)

| Field | As shown on the page |
|---|---|
| Product name | Swiss Franc Futures |
| CME Globex code | 6S |
| Clearing code | E1 |
| Other codes shown | CME ClearPort: E1 |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 Swiss francs |
| Minimum price fluctuation | CME Globex:<br>0.00005 CHF increment = $6.25<br>Calendar spreads: 0.00005 CHF increment = $6.25<br>CME ClearPort:<br>0.00001 per CHF increment = $1.25 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 20 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | CHF/USD Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/swiss-franc/specs — read 2026-10-08

### Mexican Peso Futures (6M)

| Field | As shown on the page |
|---|---|
| Product name | Mexican Peso Futures |
| CME Globex code | 6M |
| Clearing code | MP |
| Other codes shown | CME ClearPort: MP |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 500,000 Mexican pesos |
| Minimum price fluctuation | CME Globex:<br>0.00001 per MXN increment = $5.00<br>CME ClearPort:<br>0.000001 per MXN increment = $0.50 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 20 consecutive quarters and serial contracts listed for 16 months |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Physical Delivery<br>Mexican Peso Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT (with a 60-minute break each day beginning at 4:00 p.m.CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/emerging-market/mexican-peso/specs — read 2026-10-08. (CME files this product under Emerging Markets; it is kept here because it was requested in the G10 list.)

### New Zealand Dollar Futures (6N)

| Field | As shown on the page |
|---|---|
| Product name | New Zealand Dollar Futures |
| CME Globex code | 6N |
| Clearing code | NE |
| Other codes shown | CME ClearPort: NE |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 100,000 New Zealand dollars |
| Minimum price fluctuation | CME Globex:<br>0.00005 per New Zealand dollar =$5.00<br>CME ClearPort:<br>0.00001 per NZD increment = $1.00 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Physical Delivery<br>New Zealand Dollar Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/new-zealand-dollar/specs — read 2026-10-08

### Swedish Krona Futures (SEK)

| Field | As shown on the page |
|---|---|
| Product name | Swedish Krona Futures |
| CME Globex code | SEK |
| Clearing code | SE |
| Other codes shown | CME ClearPort: SE |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 2,000,000 Swedish kronor |
| Minimum price fluctuation | CME Globex:<br>0.000025 per SEK increment = $50.00<br>Spreads: 0.000005 per SEK increment = $10.00<br>CME ClearPort:<br>0.000001 per SEK increment = $2.00 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT 2 business days prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | SEK/USD Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/swedish-krona/specs — read 2026-10-08

### Norwegian Krone Futures (NOK)

| Field | As shown on the page |
|---|---|
| Product name | Norwegian Krone Futures |
| CME Globex code | NOK |
| Clearing code | UN |
| Other codes shown | CME ClearPort: UN |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 2,000,000 Norwegian kroner |
| Minimum price fluctuation | CME Globex:<br>0.000025 per Norwegian krone increment = $50.00<br>Spreads: 0.000005 per Norwegian krone increment = $10.00<br>CME ClearPort:<br>0.000001 per Norwegian krone increments ($2.00/contract). |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT 2 business days prior to the third Wednesday of the contract quarter |
| Settlement method | Deliverable |
| Settlement procedures | NOK/USD Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/norwegian-krone/specs — read 2026-10-08

### Danish krone futures — not listed

CME's FX Product Guide (https://www.cmegroup.com/markets/fx/fx-product-guide, read 2026-10-08) lists no DKK futures contract; DKK appears only in the EBS spot and eFIX tables (EUR/DKK, USD/DKK). The guessed specs URL https://www.cmegroup.com/markets/fx/g10/danish-krone/specs returned "Page not found".

## 3. E-micros

### Micro Ultra 10-Year U.S. Treasury Note Futures (MTN)

| Field | As shown on the page |
|---|---|
| Product name | Micro Ultra 10-Year U.S. Treasury Note Futures |
| CME Globex code | MTN |
| Clearing code | MTN |
| Other codes shown | CME ClearPort: MTN |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; Overview page has no vendor-codes table) |
| Contract unit | Face value at maturity of $10,000 |
| Minimum price fluctuation | Outright:<br>1/2 of 1/32 of one point (0.015625) = $1.5625<br>CALENDAR SPREAD<br>1/4 of 1/32 of one point (0.0078125) = $.78125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, and Dec) listed for 2 consecutive quarters. |
| Termination of trading | Trading terminates at 2:00 p.m. CT, 2 business days prior to the contract month. |
| Settlement method | Financially Settled |
| Settlement procedures | Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT (6:00 p.m. - 5:00 p.m.ET).  Monday - Thursday 4:00 p.m. - 5:00 p.m. CT (5:00 p.m. - 6:00 p.m. ET) daily maintenance period.<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or Overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-ultra-10-year-us-treasury-note.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-ultra-10-year-us-treasury-note.html (overview) — read 2026-10-08

### Micro Ultra U.S. Treasury Bond Futures (MWN)

| Field | As shown on the page |
|---|---|
| Product name | Micro Ultra U.S. Treasury Bond Futures |
| CME Globex code | MWN |
| Clearing code | MWN |
| Other codes shown | CME ClearPort: MWN |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; Overview page has no vendor-codes table) |
| Contract unit | Face value at maturity of $10,000 |
| Minimum price fluctuation | Outright:<br>1/32 of a point (0.03125) = $3.125<br>CALENDAR SPREAD<br>1/4 of 1/32 of a point (0.0078125) = $.78125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 2 consecutive quarters |
| Termination of trading | Trading terminates at 2:00 p.m. CT, 2 business days prior to the contract month. |
| Settlement method | Financially Settled |
| Settlement procedures | Treasury Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT (6:00 p.m. - 5:00 p.m.ET).  Monday - Thursday 4:00 p.m. - 5:00 p.m. CT (5:00 p.m. - 6:00 p.m. ET) daily maintenance period.<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or Overview) |

Sources: https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-ultra-us-treasury-bond.contractSpecs.html (specs) and https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-ultra-us-treasury-bond.html (overview) — read 2026-10-08

#### Micro Treasury Yield futures (2YY, 5YY, 10Y, 30Y)

CME's Micro Treasury page groups these yield-quoted contracts with the Micro Treasuries; the specs pages title them "2-Year / 5-Year / 10-Year / 30-Year Yield Futures" and the URLs use `micro-N-year-yield`. They are included because the request named micro 2Y/5Y/10Y/30Y. None of the four has an Overview tab.

### 2-Year Yield Futures (2YY)

| Field | As shown on the page |
|---|---|
| Product name | 2-Year Yield Futures |
| CME Globex code | 2YY |
| Clearing code | 2YY |
| Other codes shown | CME ClearPort: 2YY |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 1,000 index points |
| Minimum price fluctuation | 0.001 Index points (1/10th basis point per annum) = $1.00 |
| Listed contracts | Monthly contracts listed for 2 consecutive months |
| Termination of trading | Trading terminates on the last business day of the contract month |
| Settlement method | Financially Settled |
| Settlement procedures | Treasury Yield Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-2-year-yield.contractSpecs.html — read 2026-10-08

### 5-Year Yield Futures (5YY)

| Field | As shown on the page |
|---|---|
| Product name | 5-Year Yield Futures |
| CME Globex code | 5YY |
| Clearing code | 5YY |
| Other codes shown | CME ClearPort: 5YY |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 1,000 index points |
| Minimum price fluctuation | 0.001 Index points (1/10th basis point per annum) = $1.00 |
| Listed contracts | Monthly contracts listed for 2 consecutive months |
| Termination of trading | Trading terminates on the last business day of the contract month |
| Settlement method | Financially Settled |
| Settlement procedures | Treasury Yield Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-5-year-yield.contractSpecs.html — read 2026-10-08

### 10-Year Yield Futures (10Y)

| Field | As shown on the page |
|---|---|
| Product name | 10-Year Yield Futures |
| CME Globex code | 10Y |
| Clearing code | 10Y |
| Other codes shown | CME ClearPort: 10Y |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 1,000 index points |
| Minimum price fluctuation | 0.001 Index points (1/10th basis point per annum) = $1.00 |
| Listed contracts | Monthly contracts listed for 2 consecutive months |
| Termination of trading | Trading terminates on the last business day of the contract month |
| Settlement method | Financially Settled |
| Settlement procedures | Treasury Yield Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-10-year-yield.contractSpecs.html — read 2026-10-08

### 30-Year Yield Futures (30Y)

| Field | As shown on the page |
|---|---|
| Product name | 30-Year Yield Futures |
| CME Globex code | 30Y |
| Clearing code | 30Y |
| Other codes shown | CME ClearPort: 30Y |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 1,000 index points |
| Minimum price fluctuation | 0.001 Index points (1/10th basis point per annum) = $1.00 |
| Listed contracts | Monthly contracts listed for 2 consecutive months |
| Termination of trading | Trading terminates on the last business day of the contract month |
| Settlement method | Financially Settled |
| Settlement procedures | Treasury Yield Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/interest-rates/us-treasury/micro-30-year-yield.contractSpecs.html — read 2026-10-08

### Micro EUR/USD Futures (M6E)

| Field | As shown on the page |
|---|---|
| Product name | Micro EUR/USD Futures |
| CME Globex code | M6E |
| Clearing code | M6E |
| Other codes shown | CME ClearPort: M6E |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 12,500 euros |
| Minimum price fluctuation | 0.0001 per euro = $1.25 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 2 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT 2 business day prior to the 3rd Wednesday of the contract quarter. |
| Settlement method | Deliverable |
| Settlement procedures | Micro Euro/American Dollar Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/e-micro-euro/specs — read 2026-10-08

### Micro GBP/USD Futures (M6B)

| Field | As shown on the page |
|---|---|
| Product name | Micro GBP/USD Futures |
| CME Globex code | M6B |
| Clearing code | M6B |
| Other codes shown | CME ClearPort: M6B |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 6,250 British pounds |
| Minimum price fluctuation | 0.0001 per GBP increment = $0.625 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 2 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT 2 business day prior to the 3rd Wednesday of the contract quarter. |
| Settlement method | Deliverable |
| Settlement procedures | Micro British Pound/American Dollar Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/e-micro-british-pound/specs — read 2026-10-08

### Micro AUD/USD Futures (M6A)

| Field | As shown on the page |
|---|---|
| Product name | Micro AUD/USD Futures |
| CME Globex code | M6A |
| Clearing code | M6A |
| Other codes shown | CME ClearPort: M6A |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 10,000 Australlian Dollars (sic) |
| Minimum price fluctuation | 0.0001 per Australian dollar = $1.00 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 2 consecutive quarters |
| Termination of trading | Trading terminates 2 business day prior to the 3rd Wednesday of the contract quarter. |
| Settlement method | Deliverable |
| Settlement procedures | Micro Australian Dollar/American Dollar Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/e-micro-australian-dollar/specs — read 2026-10-08

### Micro JPY/USD Futures (MJY)

| Field | As shown on the page |
|---|---|
| Product name | Micro JPY/USD Futures |
| CME Globex code | MJY |
| Clearing code | MJY |
| Other codes shown | CME ClearPort: MJY |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 1,250,000 JPY |
| Minimum price fluctuation | 0.000001 per JPY increment = $1.25 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 2 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT 2 business day prior to the 3rd Wednesday of the contract quarter. |
| Settlement method | Deliverable |
| Settlement procedures | Micro Japanese Yen/U.S. Dollar Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CTT (sic) |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/micro-jpy-usd/specs — read 2026-10-08. (The guessed URL `/markets/fx/g10/e-micro-japanese-yen/specs` returned "Page not found"; this URL is from CME's FX product menu.)

### Micro CAD/USD Futures (MCD)

| Field | As shown on the page |
|---|---|
| Product name | Micro CAD/USD Futures |
| CME Globex code | MCD |
| Clearing code | MCD |
| Other codes shown | CME ClearPort: MCD |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 10,000 Canadian dollars |
| Minimum price fluctuation | 0.0001 per Canadian dollar increment = $1.00 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 2 consecutive quarters |
| Termination of trading | Trading terminates 1 business day prior to the 3rd Wednesday of the contract quarter. |
| Settlement method | Deliverable |
| Settlement procedures | Micro Canadian Dollar/American Dollar Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/e-micro-canadian-dollar-us-dollar/specs — read 2026-10-08

### Micro CHF/USD Futures (MSF)

| Field | As shown on the page |
|---|---|
| Product name | Micro CHF/USD Futures |
| CME Globex code | MSF |
| Clearing code | MSF |
| Other codes shown | CME ClearPort: MSF |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 12,500 CHF |
| Minimum price fluctuation | 0.0001 per CHF increment = $1.25 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 2 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. 2 business day prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Micro Swiss Franc/American Dollar Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/e-micro-swiss-franc-us-dollar/specs — read 2026-10-08

### Micro INR/USD Futures (MIR)

| Field | As shown on the page |
|---|---|
| Product name | Micro INR/USD Futures |
| CME Globex code | MIR |
| Clearing code | MIR |
| Other codes shown | CME ClearPort: MIR |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 1,000,000 INR (≈ USD $15,728 as of June 18, 2015)<br>(10 lakh) |
| Minimum price fluctuation | 0.01 U.S. cents per 100 INR increments ($1.00/tick). Also, trades can occur in 0.005 U.S. cents per 100 INR increments ($0.50/contract) for INR/USD futures intracurrency spreads executed on CME Globex®. |
| Listed contracts | Monthly contracts listed for 12 consecutive months. |
| Termination of trading | Trading terminates at 1:00 p.m. Mumbai time two Indian business days immediately preceding the last Indian business day of the contract month. |
| Settlement method | Financially Settled |
| Settlement procedures | Settlement Procedure (link) |
| Trading hours | CME Globex:<br>Sunday: 5:00 p.m. - 4:00 p.m. CT next day. Monday - Friday: 5:00 p.m. - 4:00 p.m. CT the next day, except on Friday - closes at 4:00 p.m. and reopens Sunday at 5:00 p.m. CT.<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/e-micro-indian-rupee/specs — read 2026-10-08

#### Not included: E-mini FX

CME's FX Product Guide also lists two E-mini contracts (E-mini EUR/USD, E7; E-mini JPY/USD, J7). They are not micros, so they are left out of this section.

## 4. FX cross rates

All 22 cross-rate futures in CME's FX product menu (14 under "Cross Rates" and 8 listed under G10). The EUR-vs-EM crosses (CZK/EUR, HUF/EUR, PLN/EUR, RMB/EUR) are in section 5.

### Euro/British Pound Futures — EUR/GBP (RP)

| Field | As shown on the page |
|---|---|
| Product name | Euro/British Pound Futures |
| CME Globex code | RP |
| Clearing code | RP |
| Other codes shown | CME ClearPort: RP |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 euro |
| Minimum price fluctuation | CME Globex:<br>0.00005 per EUR increment = £6.25<br>Spreads: 0.000025 per EUR increment = £3.125<br>CME ClearPort:<br>0.00001 per EUR increment = £1.25 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters and serial contracts listed for 8 months. |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business days prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | EUR/GBP Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/euro-fx-british-pound/specs — read 2026-10-08

### Euro/Japanese Yen Futures — EUR/JPY (RY)

| Field | As shown on the page |
|---|---|
| Product name | Euro/Japanese Yen Futures |
| CME Globex code | RY |
| Clearing code | RY |
| Other codes shown | CME ClearPort: RY |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 euro |
| Minimum price fluctuation | CME Globex:<br>0.01 Japanese yen per euro increment = ¥1,250<br>Calendar spreads: 0.005 Japanese yen per euro increment = ¥625<br>CME ClearPort:<br>0.001 Japanese yen per Euro increment = ¥125 |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | EUR/JPY Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/euro-fx-japanese-yen/specs — read 2026-10-08

### Euro/Swiss Franc Futures — EUR/CHF (RF)

| Field | As shown on the page |
|---|---|
| Product name | Euro/Swiss Franc Futures |
| CME Globex code | RF |
| Clearing code | RF |
| Other codes shown | CME ClearPort: RF |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 euro |
| Minimum price fluctuation | CME Globex:<br>0.0001 Swiss francs per euro increment = 12.5 (Swiss francs)<br>Calendar spreads: 0.00005 Swiss francs per euro increment = 6.25 (Swiss francs)<br>CME ClearPort:<br>0.00001 Swiss francs per euro increment = 1.25 (Swiss francs) |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | EUR/CHF Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT (with a 60-minute break each day beginning at 4:00 p.m.CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/euro-fx-swiss-franc/specs — read 2026-10-08

### Euro/Australian Dollar Futures — EUR/AUD (EAD)

| Field | As shown on the page |
|---|---|
| Product name | Euro/Australian Dollar Futures |
| CME Globex code | EAD |
| Clearing code | CA |
| Other codes shown | CME ClearPort: CA |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 Euro |
| Minimum price fluctuation | CME Globex:<br>0.0001 per Euro increment = 12.5 AUD<br>Spreads: 0.00005 per Euro increment = 6.25 AUD<br>CME ClearPort:<br>0.00001 per Euro increment = 1.25 AUD |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT 2 business days prior to the 3rd Wednesday of the contract quarter. |
| Settlement method | Deliverable |
| Settlement procedures | EUR/AUD Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/euro-fx-australian-dollar/specs — read 2026-10-08

### Euro/Canadian Dollar Futures — EUR/CAD (ECD)

| Field | As shown on the page |
|---|---|
| Product name | Euro/Canadian Dollar Futures |
| CME Globex code | ECD |
| Clearing code | CC |
| Other codes shown | CME ClearPort: CC |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 Euro |
| Minimum price fluctuation | CME Globex:<br>0.0001 per Euro increment = 12.50 Canadian dollars<br>Spreads: 0.00005 per Euro increment = 6.25 Canadian dollars<br>CME ClearPort:<br>0.00001 per Euro increment = 1.25 Canadian dollars |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT 2 business day prior to the 3rd Wednesday of the contract quqrter. (sic) |
| Settlement method | Deliverable |
| Settlement procedures | EUR/CAD Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/euro-fx-canadian-dollar/specs — read 2026-10-08

### Euro/Norwegian Krone Futures — EUR/NOK (ENK)

| Field | As shown on the page |
|---|---|
| Product name | Euro/Norwegian Krone Futures |
| CME Globex code | ENK |
| Clearing code | CN |
| Other codes shown | CME ClearPort: CN |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 Euro |
| Minimum price fluctuation | CME Globex:<br>0.0025 per Euro increment = 312.5 Norwegian krone<br>Intra-currency spreads: 0.00025 per euro increment = 31.25 Norwegian krone<br>CME ClearPort:<br>0.0001 per Euro increment = 12.5 Norwegian krone |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business days prior to the 3rd Wednesday of the contract month |
| Settlement method | Deliverable |
| Settlement procedures | EUR/NOK Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m.<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/euro-fx-norwegian-krone/specs — read 2026-10-08

### Euro/Swedish Krona Futures — EUR/SEK (ESK)

| Field | As shown on the page |
|---|---|
| Product name | Euro/Swedish Krona Futures |
| CME Globex code | ESK |
| Clearing code | KE |
| Other codes shown | CME ClearPort: KE |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 euro |
| Minimum price fluctuation | CME Globex:<br>0.0025 per euro increments = 312.50 Swedish krona<br>0.00025 per euro increment = 31.25 Swedish krona for EUR/SEK futures intra-currency spreads executed electronically.<br>CME ClearPort:<br>0.0001 per Euro increments = 12.50 Swedish krona |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT on the second business day prior to the third Wednesday of the contract month (usually Monday). |
| Settlement method | Deliverable |
| Settlement procedures | EUR/SEK Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m. CT (sic)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/euro-fx-swedish-krona/specs — read 2026-10-08

### EUR/NZD Futures (ENZ)

| Field | As shown on the page |
|---|---|
| Product name | EUR/NZD Futures |
| CME Globex code | ENZ |
| Clearing code | ENZ |
| Other codes shown | CME ClearPort: ENZ |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 EUR |
| Minimum price fluctuation | CME Globex:<br>0.00005 New Zealand dollar per EUR increment = 6.25 NZD<br>Calendar spreads: 0.000025 New Zealand dollar per EUR increment = 3.125 NZD<br>CME ClearPort:<br>0.000005 New Zealand dollar per EUR increment = .625 NZD |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | not shown |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/eur-nzd/specs — read 2026-10-08

### British Pound/Swiss Franc Futures — GBP/CHF (PSF)

| Field | As shown on the page |
|---|---|
| Product name | British Pound/Swiss Franc Futures |
| CME Globex code | PSF |
| Clearing code | BF |
| Other codes shown | CME ClearPort: BF |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 British pounds |
| Minimum price fluctuation | CME Globex:<br>0.0001 per GBP increment = 12.50 Swiss francs<br>CME ClearPort:<br>0.00001 per GBP increment = 1.25 Swiss francs<br>CALENDAR SPREAD<br>0.00005 per GBP increment = 6.25 Swiss francs |
| Listed contracts | Six months in the March quarterly cycle (Mar, Jun, Sep, Dec) |
| Termination of trading | Trading terminates on 2nd business day before 3rd wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Daily GBP/CHF Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. Chicago Time/CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/british-pound-swiss-franc/specs — read 2026-10-08

### British Pound/Japanese Yen Futures — GBP/JPY (PJY)

| Field | As shown on the page |
|---|---|
| Product name | British Pound/Japanese Yen Futures |
| CME Globex code | PJY |
| Clearing code | BY |
| Other codes shown | CME ClearPort: BY |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 British pounds |
| Minimum price fluctuation | CME Globex:<br>0.01 per British pound = 1,250 Japanese yen.<br>Spreads: 0.005 per British pound 625 Japanese yen<br>CME ClearPort:<br>0.001 per British pound = 125 Japanese yen. |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT on the second business day prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | GBP/JPY Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/british-pound-japanese-yen/specs — read 2026-10-08

### GBP/AUD Futures (PAD)

| Field | As shown on the page |
|---|---|
| Product name | GBP/AUD Futures |
| CME Globex code | PAD |
| Clearing code | PAD |
| Other codes shown | CME ClearPort: PAD |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 GBP |
| Minimum price fluctuation | CME Globex:<br>0.0001 Australian dollar per GBP increment = 12.5 AUD<br>Calendar spreads: 0.00005 Australian dollar per GBP increment = 6.25 AUD<br>CME ClearPort:<br>0.00001 Australian dollar per GBP increment = 1.25 AUD |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | not shown |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/gbp-aud/specs — read 2026-10-08

### GBP/CAD Futures (PCD)

| Field | As shown on the page |
|---|---|
| Product name | GBP/CAD Futures |
| CME Globex code | PCD |
| Clearing code | PCD |
| Other codes shown | CME ClearPort: PCD |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 GBP |
| Minimum price fluctuation | CME Globex:<br>0.0001 Canadian dollar per GBP increment = 12.5 CAD<br>Calendar spreads: 0.00005 Canadian dollar per GBP increment = 6.25 CAD<br>CME ClearPort:<br>0.00001 Canadian dollar per GBP increment = 1.25 CAD |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | not shown |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/gbp-cad/specs — read 2026-10-08

### GBP/NOK Futures (PNK)

| Field | As shown on the page |
|---|---|
| Product name | GBP/NOK Futures |
| CME Globex code | PNK |
| Clearing code | PNK |
| Other codes shown | CME ClearPort: PNK |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 GBP |
| Minimum price fluctuation | CME Globex:<br>0.0001 Norwegian krone per GBP increment = 12.5 NOK<br>Calendar spreads: 0.00005 Norwegian krone per GBP increment = 6.25 NOK<br>CME ClearPort:<br>0.00001 Norwegian krone per GBP increment = 1.25 NOK |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | not shown |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/gbp-nok/specs — read 2026-10-08

### GBP/SEK Futures (PSK)

| Field | As shown on the page |
|---|---|
| Product name | GBP/SEK Futures |
| CME Globex code | PSK |
| Clearing code | PSK |
| Other codes shown | CME ClearPort: PSK |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 125,000 GBP |
| Minimum price fluctuation | CME Globex:<br>0.0001 Swedish krona per GBP increment = 12.5SEK<br>Calendar spreads: 0.00005 Swedish krona per GBP increment = 6.25 SEK<br>CME ClearPort:<br>0.00001 Swedish krona per GBP increment = 1.25SEK |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | not shown |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/gbp-sek/specs — read 2026-10-08

### Australian Dollar/Canadian Dollar Futures — AUD/CAD (ACD)

| Field | As shown on the page |
|---|---|
| Product name | Australian Dollar/Canadian Dollar Futures |
| CME Globex code | ACD |
| Clearing code | AC |
| Other codes shown | CME ClearPort: AC |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 200,000 Australian dollars |
| Minimum price fluctuation | CME ClearPort:<br>0.00001 Canadian dollars per Australian dollar increments (2.00 Canadian dollars).<br>0.0001 Canadian dollars per Australian dollar increments (20 Canadian dollars).<br>0.00005 Canadian dollars per Australian dollar increments (10 Canadian dollars) for AUD/CAD futures intra-currency spreads executed electronically.<br>(All three lines appear under the single "CME ClearPort:" heading on the page.) |
| Listed contracts | Six months in the March quarterly cycle (Mar, Jun, Sep, Dec) |
| Termination of trading | 9:16 a.m. Central Time (CT) on the second business day immediately preceding the third Wednesday of the contract month (usually Monday). |
| Settlement method | Deliverable |
| Settlement procedures | AUD/CAD Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. Chicago Time/CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/australian-dollar-canadian-dollar/specs — read 2026-10-08

### Australian Dollar/Japanese Yen Futures — AUD/JPY (AJY)

| Field | As shown on the page |
|---|---|
| Product name | Australian Dollar/Japanese Yen Futures |
| CME Globex code | AJY |
| Clearing code | AJ |
| Other codes shown | CME ClearPort: AJ |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 200,000 Australian dollars |
| Minimum price fluctuation | CME Globex:<br>0.01 Japanese yen per Australian dollar increments (2,000 Japanese yen).<br>0.005 Japanese yen per Australian dollar increments (1,000 Japanese yen) for AUD/JPY futures intra-currency spreads executed electronically.<br>CME ClearPort:<br>0.001 Japanese yen per Australian dollar increments (200 Japanese yen). |
| Listed contracts | Six months in the March quarterly cycle (Mar, Jun, Sep, Dec) |
| Termination of trading | 9:16 a.m. Central Time (CT) on the second business day immediately preceding the third Wednesday of the contract month (usually Monday). |
| Settlement method | Deliverable |
| Settlement procedures | AUD/JPY Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. Chicago Time/CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/australian-dollar-japanese-yen/specs — read 2026-10-08

### Australian Dollar/New Zealand Dollar Futures — AUD/NZD (ANE)

| Field | As shown on the page |
|---|---|
| Product name | Australian Dollar/New Zealand Dollar Futures |
| CME Globex code | ANE |
| Clearing code | AN |
| Other codes shown | CME ClearPort: AN |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 200,000 Australian dollars |
| Minimum price fluctuation | CME Globex:<br>0.0001 New Zealand dollars per Australian dollar increments (20 New Zealand dollars).<br>0.00005 New Zealand dollars per Australian dollar increments (10 New Zealand dollars) for AUD/NZD futures intra-currency spreads executed electronically.<br>CME ClearPort:<br>0.00001 New Zealand dollars per Australian dollar increments (2.00 New Zealand dollars). |
| Listed contracts | Six months in the March quarterly cycle (Mar, Jun, Sep, Dec) |
| Termination of trading | 9:16 a.m. Central Time (CT) on the second business day immediately preceding the third Wednesday of the contract month (usually Monday). |
| Settlement method | Deliverable |
| Settlement procedures | AUD/NZD Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. Chicago Time/CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/australian-dollar-new-zealand-dollar/specs — read 2026-10-08

### NZD/CAD Futures (NZC)

| Field | As shown on the page |
|---|---|
| Product name | NZD/CAD Futures |
| CME Globex code | NZC |
| Clearing code | NZC |
| Other codes shown | CME ClearPort: NZC |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 100,000 NZD |
| Minimum price fluctuation | CME Globex:<br>0.00005 Canadian dollar per NZD increment = 5 CAD<br>Calendar spreads: 0.000025 Canadian dollar per NZD increment = 2.5 CAD<br>CME ClearPort:<br>0.000005 Canadian dollar per NZD increment = .5 CAD |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | not shown |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/nzd-cad/specs — read 2026-10-08

### NZD/JPY Futures (NJY)

| Field | As shown on the page |
|---|---|
| Product name | NZD/JPY Futures |
| CME Globex code | NJY |
| Clearing code | NJY |
| Other codes shown | CME ClearPort: NJY |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 200,000 NZD |
| Minimum price fluctuation | CME Globex:<br>0.005 Japanese Yen per NZD increment = 1000 JPY<br>Calendar spreads: 0.0025 Japanese Yen per NZD increment = 500 JPY<br>CME ClearPort:<br>0.0005 Japanese Yen per NZD increment = 100 JPY |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | not shown |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/nzd-jpy/specs — read 2026-10-08

### Canadian Dollar/Japanese Yen Futures — CAD/JPY (CJY)

| Field | As shown on the page |
|---|---|
| Product name | Canadian Dollar/Japanese Yen Futures |
| CME Globex code | CJY |
| Clearing code | CY |
| Other codes shown | CME ClearPort: CY |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 200,000 Canadian dollars |
| Minimum price fluctuation | CME Globex:<br>0.01 Japanese yen per Canadian dollar increments (2,000 Japanese yen).<br>0.005 Japanese yen per Canadian dollar increments (1,000 Japanese yen) for CAD/JPY futures intra-currency spreads executed electronically.<br>CME ClearPort:<br>0.001 Japanese yen per Canadian dollar increments (200 Japanese yen). |
| Listed contracts | Six months in the March quarterly cycle (Mar, Jun, Sep, Dec) |
| Termination of trading | 9:16 a.m. Central Time (CT) on the second business day immediately preceding the third Wednesday of the contract month (usually Monday). |
| Settlement method | Deliverable |
| Settlement procedures | CAD/JPY Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. Chicago Time/CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/canadian-dollar-japanese-yen/specs — read 2026-10-08

### Swiss Franc/Japanese Yen Futures — CHF/JPY (SJY)

| Field | As shown on the page |
|---|---|
| Product name | Swiss Franc/Japanese Yen Futures |
| CME Globex code | SJY |
| Clearing code | SJ |
| Other codes shown | CME ClearPort: SJ |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 250,000 Swiss francs |
| Minimum price fluctuation | CME Globex:<br>0.005 Japanese yen per Swiss Franc increments (1,250 Japanese yen).<br>0.0025 Japanese yen per Swiss Franc increments (625 Japanese yen) for CHF/JPY futures intra-currency spreads executed electronically.<br>CME ClearPort:<br>0.001 Japanese yen per Swiss Franc increments (250 Japanese yen). |
| Listed contracts | Six months in the March quarterly cycle (Mar, Jun, Sep, Dec) |
| Termination of trading | 9:16 a.m. Central Time (CT) on the second business day immediately preceding the third Wednesday of the contract month (usually Monday). |
| Settlement method | Deliverable |
| Settlement procedures | CHF/JPY Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. Chicago Time/CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/swiss-franc-japanese-yen/specs — read 2026-10-08

### NOK/SEK Futures (NSK)

| Field | As shown on the page |
|---|---|
| Product name | NOK/SEK Futures |
| CME Globex code | NSK |
| Clearing code | NSK |
| Other codes shown | CME ClearPort: NSK |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 1,000,000 NOK |
| Minimum price fluctuation | CME Globex:<br>0.00001 Swedish krona per NOK increment = 10 SEK<br>Calendar spreads: 0.000005 Swedish krona per NOK increment = 5 SEK<br>CME ClearPort:<br>0.000001 Swedish krona per NOK increment = 1 SEK |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 6 consecutive quarters |
| Termination of trading | Trading terminates at 9:16 a.m. CT, 2 business day prior to the 3rd Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | not shown |
| Trading hours | CME Globex:<br>Sunday - Friday 6:00 p.m. - 5:00 p.m. (5:00 p.m. - 4:00 p.m. CT) with a 60-minute break each day beginning at 5:00 p.m. (4:00 p.m. CT)<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/g10/nok-sek/specs — read 2026-10-08

## 5. Emerging-market FX

### Brazilian Real Futures — BRL/USD (6L)

| Field | As shown on the page |
|---|---|
| Product name | Brazilian Real Futures |
| CME Globex code | 6L |
| Clearing code | BR |
| Other codes shown | CME ClearPort: BR |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; Overview page has no vendor-codes table) |
| Contract unit | 100,000 Brazilian reais |
| Minimum price fluctuation | CME Globex:<br>0.00005 per Brazilian real increment = $5.00<br>Final Settlement: 0.00001<br>CME ClearPort:<br>0.000005 per Brazilian real increment = $0.50 |
| Listed contracts | Monthly contracts listed for 60 consecutive months |
| Termination of trading | Trading terminates at 9:15 a.m. CT on the last business day of the month prior to the contract month, on which the Central Bank of Brazil is scheduled to publish its final end-of-month (EOM), "Commercial exchange rate for Brazilian reais per U.S. dollar for cash delivery" (PTAX rate). |
| Settlement method | Financially Settled |
| Settlement procedures | BRL/USD Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m. CT with a 60-minute break each day beginning at 4:00 p.m.<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown (specs or Overview) |

Sources: https://www.cmegroup.com/markets/fx/emerging-market/brazilian-real/specs (specs) and https://www.cmegroup.com/markets/fx/emerging-market/brazilian-real (overview) — read 2026-10-08

### Chilean Peso/US Dollar (CLP/USD) Futures (CHP)

| Field | As shown on the page |
|---|---|
| Product name | Chilean Peso/US Dollar (CLP/USD) Futures |
| CME Globex code | CHP |
| Clearing code | CHP |
| Other codes shown | CME ClearPort: CHP |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 50,000,000 Chilean Pesos |
| Minimum price fluctuation | $0.0000001 per Chilean Peso increments ($5.00/contract) also for CLP/USD futures intra-currency spreads executed electronically. |
| Listed contracts | Monthly contracts listed for 12 consecutive months and the next 4 March quarterly cycle months. |
| Termination of trading | Trading terminates at 09:15 Chicago time on the last Santiago, Chile business day of the month prior to the contract month. |
| Settlement method | Financially Settled |
| Settlement procedures | The reciprocal of the spot exchange rate of Chilean peso per U.S. dollar, ”CLP DÓLAR OBS (CLP10),” as reported for that day by Banco Central de Chile for the formal exchange market which is available at approximately 10:30 AM Santiago time and rounded to SEVEN decimal places. |
| Trading hours | CME Globex:<br>Sunday - Friday; 5:00 p.m. - 4:00 p.m/ CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday from 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/emerging-market/chilean-peso-us-dollar/specs — read 2026-10-08

### CNH/USD Futures (6H)

| Field | As shown on the page |
|---|---|
| Product name | CNH/USD Futures |
| CME Globex code | 6H |
| Clearing code | 6H |
| Other codes shown | CME ClearPort: 6H |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 500,000 CNH |
| Minimum price fluctuation | CME Globex:<br>0.00001 per CNH increment = 5 USD<br>Spreads: 0.000005 per CNH increment = 2.50 USD<br>Final Settlement: 0.00001<br>CME ClearPort:<br>0.000001 per CNH increment = 0.5 USD |
| Listed contracts | Quarterly contracts (Mar, Jun, Sep, Dec) listed for 5 consecutive quarters |
| Termination of trading | Trading terminates at 2:00 p.m. Hong Kong local time on the second Hong Kong business day prior to the third Wednesday of the contract month. |
| Settlement method | Deliverable |
| Settlement procedures | Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/emerging-market/cnh-usd/specs — read 2026-10-08

### Offshore Chinese Renminbi (CNH) Futures — USD/CNH (CNH)

> The page carries this notice: "Please Note: USD/CNH futures have been replaced by new CNH/USD futures. No new USD/CNH futures are being listed as they expire."

| Field | As shown on the page |
|---|---|
| Product name | Offshore Chinese Renminbi (CNH) Futures |
| CME Globex code | CNH |
| Clearing code | CNH |
| Other codes shown | CME ClearPort: CNH |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 100,000 USD |
| Minimum price fluctuation | CME Globex:<br>Outright:0.0005 per USD increment = 50 CNH                Spreads:0.00025 per USD increment = 25 CNH<br>CME ClearPort:<br>0.0001 per USD increment = 10 CNH |
| Listed contracts | Monthly contracts listed for 13 consecutive months and quarterly contracts (Mar, Jun, Sep, Dec) listed for the next 8  quarters. |
| Termination of trading | Trading terminates at 2:00 p.m. Hong Kong local time on the second Hong Kong business day prior to the third Wednesday of the contract month. |
| Settlement method | Financially Settled |
| Settlement procedures | USD/CNH Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday 5:00 p.m. - Friday - 4:00 p.m. CT with a daily maintenance period from 4:00 p.m. - 5:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/cross-rates/usd-cnh/specs — read 2026-10-08. (Listed in CME's FX product menu under Emerging Market; not in the FX Product Guide futures table.)

### Onshore Chinese Renminbi (CNY) Futures — RMB/USD (RMB)

| Field | As shown on the page |
|---|---|
| Product name | Onshore Chinese Renminbi (CNY) Futures |
| CME Globex code | RMB |
| Clearing code | RMB |
| Other codes shown | CME ClearPort: RMB |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 1,000,000 Chinese renminbi |
| Minimum price fluctuation | Outrights: 0.00001 per Chinese renminbi = $10.00.<br>Intra-currency spreads: 0.000005 per Chinese renminbi = $5.00 |
| Listed contracts | Monthly contracts listed for 13 consecutive months and quarterly contracts (Mar, Jun, Sep & Dec) listed for 8 consecutive quarters |
| Termination of trading | Trading terminates at 9:00 a.m. Beijing time on the second Beijing business day prior to the third Wednesday of the contract month (7:00 p.m. CT on Sunday during the winter and 8:00 p.m. CT on Sunday during the summer). |
| Settlement method | Financially Settled |
| Settlement procedures | RMB/USD Futures Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sunday - Friday 5:00 p.m. - 4:00 p.m/ CT with a 60-minute break each day beginning at 4:00 p.m. CT<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/emerging-market/chinese-renminbi/specs — read 2026-10-08

### Chinese Renminbi/Euro Futures — RMB/EUR (RME)

| Field | As shown on the page |
|---|---|
| Product name | Chinese Renminbi/Euro Futures |
| CME Globex code | RME |
| Clearing code | RME |
| Other codes shown | CME ClearPort: RME |
| Vendor codes (Bloomberg / Refinitiv) | not shown (specs page links to "Quote Vendor Symbols Listing"; product has no Overview tab) |
| Contract unit | 1,000,000 Chinese renminbi |
| Minimum price fluctuation | .00001 euro per Chinese renminbi increments (10 euro). .000005 euro per Chinese renminbi increments (5 euro) for RMB/EUR futures intra-currency spreads executed electronically. |
| Listed contracts | Thirteen consecutive calendar months plus 2 deferred March quarterly cycle contract months |
| Termination of trading | Trading ceases at 9:00 a.m. Beijing time* on the second Beijing business day immediately preceding the third Wednesday of the contract month (i.e., In Chicago, 7:00 p.m. CT on Sunday night during the winter and 8:00 p.m. CT on Sunday night during the summer). |
| Settlement method | Financially Settled |
| Settlement procedures | RMB/EUR Settlement Procedures (link) |
| Trading hours | CME Globex:<br>Sundays: 5:00 p.m. - 4:00 p.m. Central Time (CT) next day. Monday - Friday: 5:00 p.m. - 4:00 p.m. CT the next day, except on Friday - closes at 4:00 p.m. and reopens Sunday at 5:00 p.m. CT.<br>CME ClearPort:<br>Sunday 5:00 p.m. - Friday 5:45 p.m. CT with no reporting Monday - Thursday 5:45 p.m. - 6:00 p.m. CT |
| Launch / first trade date | not shown |

Source: https://www.cmegroup.com/markets/fx/emerging-market/chinese-renminbi-euro/specs — read 2026-10-08

### Not yet read (session ended before these pages were opened)

The remaining emerging-market futures from CME's FX product menu have not been read yet. Their pages are listed so the next pass can pick them up:

| Product (as named in CME's FX menu) | Page |
|---|---|
| CZK/USD | https://www.cmegroup.com/markets/fx/emerging-market/czech-koruna/specs |
| CZK/EUR | https://www.cmegroup.com/markets/fx/emerging-market/euro-fx-czech-koruna/specs |
| HUF/USD | https://www.cmegroup.com/markets/fx/emerging-market/hungarian-forint/specs |
| HUF/EUR | https://www.cmegroup.com/markets/fx/emerging-market/euro-fx-hungarian-forint/specs |
| PLN/USD | https://www.cmegroup.com/markets/fx/emerging-market/polish-zloty/specs |
| PLN/EUR | https://www.cmegroup.com/markets/fx/emerging-market/euro-fx-polish-zloty/specs |
| ILS/USD | https://www.cmegroup.com/markets/fx/emerging-market/israeli-shekel/specs |
| INR/USD | https://www.cmegroup.com/markets/fx/emerging-market/indian-rupee/specs |
| KRW/USD | https://www.cmegroup.com/markets/fx/emerging-market/korean-won/specs |
| RUB/USD | https://www.cmegroup.com/markets/fx/emerging-market/russian-ruble/specs |
| TRY/USD | https://www.cmegroup.com/markets/fx/emerging-market/turkish-lira-us-dollar-try-usd/specs |
| ZAR/USD | https://www.cmegroup.com/markets/fx/emerging-market/south-african-rand/specs |
| IDR/USD | https://www.cmegroup.com/markets/fx/emerging-market/idr-usd/specs |
| SGD/USD | https://www.cmegroup.com/markets/fx/emerging-market/sgd-usd/specs |
| THB/USD | https://www.cmegroup.com/markets/fx/emerging-market/thb-usd/specs |

(The Mexican peso, 6M, is filed under Emerging Markets by CME but appears in the G10 section above because it was requested there.)

