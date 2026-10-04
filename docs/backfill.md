# Calendar backfill: sources and plan (phase 1, step 5)

Research done 2026-10-04, before building anything. Every source below was read through a web-fetch summarizer: the build sandbox can't download pages directly, and web.archive.org was blocked to it. So the dates are leads to check against the documents themselves, not checked data. Each backfill PR checks its source's dates against the real bytes.

## SIFMA-US: published history, 1996–2025

| Years | Source | Format |
|---|---|---|
| 2015–2025 | [U.S. Holiday Archive](https://www.sifma.org/resources/guides-playbooks/us-holiday-archive) | One HTML page with a section per year, laid out like today's schedule page |
| 1996–2019 | [Historical recommendations PDF](https://www.sifma.org/wp-content/uploads/2017/08/Misc-US-Historical-Holiday-Market-Recommendations-SIFMA.pdf) | One table: year, holiday, early close (2 p.m. unless noted), full close |
| 2026+ | Today's schedule page (already parsed) | |

- **The HTML archive** is close to what `sifma.py` already reads. It also needs to handle:
  - "Noon" as well as "12:00 p.m.", and a missing colon;
  - "Early Close Only (…): <date> – <note>";
  - a heading with no date (Presidents Day 2015 and 2016, Veterans Day 2023) or "None" (Veterans Day 2017);
  - "Early Market Close: (…):" (Dec 30, 2016);
  - the holiday's date line plus an early close on that same date (Good Friday 2015).

  Done in #12, from the real capture. SIFMA's page gives no date for Presidents Day 2015 or 2016, though both were full closes: the PDF should fill them. The page links the PDF as "US Holiday Archives 1996-2017".
- **The PDF** is source `SIFMA-US-HISTORY`: captured raw first (#15), then parsed from the real capture (#17). Its parser reads cell positions. Plain text loses which column a date sits in, so the extract couldn't tell full closes from early closes. It also writes times inline in mixed styles ("noon EST", "11:00 am", "1:00 pm") and often leaves out the year. Since it never changes, parse it once, check the result by hand, and keep the PDF as the raw capture.
- **Unscheduled recommendations:** the PDF has Hurricane Sandy (Oct 29, 2012 early close at noon, Oct 30 full close) and George H.W. Bush (Dec 5, 2018 full close). Jimmy Carter (Jan 9, 2025, early close at 2 p.m.) is missing from both documents. It's the one entry in `rules/sifma_us_exceptions.json` (#19), cited to [SIFMA's press release](https://www.sifma.org/news/press-releases/sifma-recommends-early-market-close-on-january-9-2025-for-the-national-day-of-mourning-in-honor-of-former-president-carter).

  SIFMA's press releases and its Unscheduled Close Market Matrix are the sources. What SIFMA recommended on 9/11, and on the Reagan (2004) and Ford (2007) mourning days, isn't confirmed.
- **Good Friday:** usually a full close. It's a noon early close in jobs-report years (2010, 2012, 2015, 2021, 2023, 2026), and was 11 a.m. in 2007. 2015 is a noon early close on the archive page (it lists the date and then the noon early close under Good Friday). The PDF still has the original 2015 recommendation: an early close on Thursday, Apr 2 and a full close on Friday, Apr 3. The archive outranks it on Apr 3. The Apr 2 early close is kept from the PDF (Bill, 2026-10-04).
- **Reliability:** 2005 onward is solid. 1996–2004 has less regular times, so review it by hand.

## FED: rules, confirmed against NY Fed circulars

**Built (#19):** `rules/fed.json` (source `FED-RULES`, 1986–2025). All seven circulars (2003–2009) match it; 11720, 11797 and 11879 are 2006, 2007 and 2008. The circulars were first read through a web-fetch summarizer, with their dates pinned in `tests/test_rules.py`. **Since #39/#40 (2026-10-04) each is its own source**, `FED-NYFED-2003` … `FED-NYFED-2009` (captures #15–#22), parsed by `app/calendars/nyfed.py` and ranked above `FED-RULES`, so the circulars are the record for 2003–2009. Parsed from the real captures, all seven match the rules day for day (`tests/test_nyfed_parser.py`).

- **No archived K.8 is reachable.** `federalreserve.gov/releases/k8/k8a.htm` (2005) exists but its body didn't come through, and the Wayback Machine was blocked.
- **Official per-year lists, 2003–2009:** NY Fed operating circulars, one per year. Found so far:
  - [11465](https://www.newyorkfed.org/banking/circulars/11465.html) (2003)
  - [11532](https://www.newyorkfed.org/banking/circulars/11532.html) (2004)
  - [11615](https://www.newyorkfed.org/banking/circulars/11615.html) (2005)
  - [11980](https://www.newyorkfed.org/banking/circulars/11980.html) (2009)
  - 11720, 11797 and 11879 are probably 2006–2008.
- **Rules from statute** (5 U.S.C. 6103):
  - New Year's, Independence Day, Veterans Day and Christmas on their fixed dates.
  - Monday holidays from 1971.
  - Veterans Day was the 4th Monday of October from 1971 to 1977.
  - MLK Day from 1986.
  - Juneteenth from 2021. Check June 18, 2021: the law was signed June 17.
  - Inauguration Day isn't a Fed holiday.
  - Saturday holiday: the Banks stay open the Friday before (confirmed for 2004 and 2009). Sunday holiday: closed the Monday after.
- **No one-off exceptions.** The Reserve Banks and Fedwire stayed open on 9/11, through Hurricane Sandy, and on every national day of mourning (2004, 2007, 2018, 2025); only the Board closed.
- **Reliability:**
  - 2003 onward: checked against the circulars.
  - 1986–2002: from statute, not checked.
  - Before 1980: Banks closed on different days (FRASER district notices), so don't go back that far.
- **Watch:** Fedwire Funds and NSS move to Sunday–Friday, including weekday holidays, in 2028 or 2029; Fedwire Securities doesn't. From then on, FED means the Reserve Banks' holidays, not "Fedwire Funds closed".

## NYSE: rules plus a cited exceptions table, 1990 onward

**Built (#20):** `rules/nyse.json` (source `NYSE-RULES`, 1990–2025). It reproduces the hours page's 2026–2028 table and ICE's 2023–2025 announcement exactly. MLK Day is confirmed from 1998. ICE's 2019–2021 announcement came through the summarizer garbled, so it isn't used as a check.

- **Sources:**
  - **"History of New York Stock Exchange Holidays"** (NYSE PDF): 1885 to Jan 2011, with regular closings, special closings and early closes with times. Only third-party copies were found:
    - [through Nov 2008](https://www.ltadvisors.net/Info/research/closings.pdf)
    - [through Jan 2011](https://s3.amazonaws.com/armstrongeconomics-wp/2013/07/NYSE-Closings.pdf)
  - **Yearly NYSE Group holiday-calendar press releases** (ir.theice.com, three years each) for after 2011, e.g. [2019–2021](https://ir.theice.com/press/news-details/2018/NYSE-Group-Announces-2019-2020-and-2021-Holiday-and-Early-Closings-Calendar/default.aspx) and [2023–2025](https://ir.theice.com/press/news-details/2022/NYSE-Group-Announces-2023-2024-and-2025-Holiday-and-Early-Closings-Calendar/default.aspx).
  - **Rule 7.2 text:** in SEC filing [SR-NYSE-2021-56](https://www.sec.gov/files/rules/sro/nyse/2021/34-93183.pdf).
- **Holiday rules:**
  - The holidays: New Year's, MLK, Presidents', Good Friday, Memorial, Juneteenth (from 2022), Independence, Labor, Thanksgiving, Christmas.
  - Saturday holiday: closed the Friday before. Exception: a Saturday New Year's Day gets no Friday holiday (policy since 1959).
  - Sunday holiday: closed the Monday after.
  - When MLK Day was first observed (reportedly 1998) isn't confirmed.
- **Early-close rules** (about 2008 onward, all at 1:00 p.m.):
  - the day after Thanksgiving;
  - July 3 when it falls Monday–Thursday;
  - Dec 24 when it falls Monday–Thursday.
- **Earlier early closes were irregular:**
  - 2:00 p.m. closes through 1992;
  - 1:00 p.m. from Nov 26, 1993;
  - extra early closes on Jul 5 1996, Dec 26 1997, Dec 31 1999, Jul 5 2002 and Dec 26 2003.
- **Unscheduled full closes since 1990:**
  - Apr 27, 1994 (Nixon)
  - Sep 11–14, 2001
  - Jun 11, 2004 (Reagan)
  - Jan 2, 2007 (Ford)
  - Oct 29–30, 2012 (Hurricane Sandy)
  - Dec 5, 2018 (George H.W. Bush)
  - Jan 9, 2025 (Carter)
- **Unscheduled early closes:**
  - Feb 11, 1994, 2:30 p.m. (snow)
  - Jan 8, 1996, 2:00 p.m. (snow)
  - Oct 27, 1997, 3:30 p.m. (circuit breakers)
- **Reliability:** 1990 onward. Earlier is possible from the History PDF if ever needed.
- **The History PDF as a source (#39/#40, 2026-10-04):** `NYSE-HISTORY` (capture #17, the January 2011 copy), parsed by `app/calendars/nyse_history.py`. It's a list of special closings, not a per-year table, so it covers no years: it contributes the special full and early closes it lists for 1990–2010 and outranks `NYSE-RULES` on those dates. Cross-check: 54 of its 55 days match the rules exactly, and every special day in the rules is in it. The one addition is **June 1, 2005**, a systems halt at 3:56 p.m. after which trading didn't resume, kept as an early close like the 1997 circuit-breaker halt (`tests/test_nyse_history_parser.py`). Not counted: July 2, 2009's 4:15 p.m. late close, opening delays, halts that resumed, and moments of silence.

## Approach (agreed with Bill, 2026-10-04)

- **Raw stays raw.** Each document becomes a `capture` under its own `source`, so processed rows still point at what justifies them:
  - the SIFMA archive page and PDF;
  - the NY Fed circulars;
  - the NYSE History PDF and press releases.
- **Rule-generated years** get their own source per calendar, e.g. `FED-RULES` and `NYSE-RULES`. Their "capture" is the rule set's version: a small, versioned file in the repo listing the rules and the exceptions, each with a citation URL.
- **Precedence:** where a published document and the rules disagree, the published document wins. The disagreement is reported in the capture's summary rather than silently overwritten.
- **Order:** SIFMA-US first (the HTML archive reuses the current parser), then FED, then NYSE.
- **Ranges:** SIFMA-US from 1996, FED from 1986 (2003 onward checked against the circulars), NYSE from 1990.
- **Getting the documents:** the hub fetches them through the job API like today's pages. The sandbox can't, so each source is first fetched once by a `capture` job, and its bytes come back through `GET /jobs/captures/{id}` to build test fixtures.

## Forward: projected to 2100 (Bill, 2026-10-04)

Payment schedules for bonds and swaps need business days decades ahead. FED gives New York banking days (USD swap and bond payments); SIFMA-US gives U.S. Government Securities Business Days (SOFR fixings and Treasury settlement). Publishers list 1–5 years ahead, so each calendar's rules run forward to 2100 as a projected source.

- **Lowest precedence:** a projection fills only years no other source covers.
- **Whole years:** once a publisher covers a year, the projection's rows for that year are retired, not just the dates the publisher lists.
- **Full closes only.**
- **Flagged:** `business-day` answers from projected years say `"projected": true`.
- **Known uncertainty:**
  - SIFMA's Good Friday is a noon early close in jobs-report years, which can't be predicted decades ahead.
  - A future change to the statutory holidays (as Juneteenth was in 2021) needs a rules-file update. The old projected rows are then kept as history.
