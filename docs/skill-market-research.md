# Skill Market Research — which apps to gate, in what order, at what price

Compiled 2026-07-03 from two web-research sweeps (app usage/install base; automation
demand + comparable pricing, with a claim-verification pass: 19/20 spot-checks
confirmed, 0 refuted). Internal document — informs the Skill Store branch order.
Figures marked *est.* were not verifiable on an official page.

## 1. The most-used Windows desktop software (usage × who already pays)

Ranked by Windows-desktop install base and active use, 2024–2026:

| # | App | Base | Paying users of the app itself |
|---|-----|------|-------------------------------|
| 1 | File Explorer / shell | all ~1.4B Windows devices | — (covered by OrphicOS base plan) |
| 2 | Chrome | ~70% of desktop browsing | — (but carries Gmail, Canva, Xero, most SaaS) |
| 3 | Edge | preinstalled; ~12–14% share | — |
| 4 | **Excel** | 750M–1.5B users | 345M paid M365 seats + 89M consumer subs |
| 5 | **Word** | same M365 base | same |
| 6 | **Outlook desktop** | 400M+ Outlook users (all variants) | same; note: only ~8% of email OPENS are Outlook desktop vs ~28% Gmail |
| 7 | Teams | 320–360M MAU | paid per-seat in most orgs |
| 8 | PowerPoint | same M365 base | same |
| 9 | Acrobat Reader | 64% PDF market, 100M+ daily | Acrobat Pro inside 41M Creative Cloud subs |
| 10 | VLC | ~4.8B Windows downloads | — |
| 11 | Steam | 147M MAU | — (client free) |
| 12–18 | Spotify, Zoom, WhatsApp, Discord, 7-Zip/WinRAR, Canva, CapCut | large but low automation surface / mobile-web heavy | mostly freemium |
| 19 | **Photoshop** | ~30–33M users | inside 41M paid Creative Cloud |
| 20 | **Premiere Pro** | ~30M users | same |
| 21 | VS Code | tens of millions (#1 IDE 4 yrs running) | — (free; devs already have AI tools) |
| 22 | Notion | 100M users | 4M paying |
| 23 | **QuickBooks** | ~7M users, 62% accounting market | ~6.5–7M paying |
| 24 | **AutoCAD** (Autodesk) | 7.79M paid subscriptions | all paying |
| 25 | **DATEV** | 850K customers, ~80% of German tax advisors | all paying (DACH vertical) |

Where the hours go (Microsoft Work Trend Index 2025 + HBR): 57% of work time is
communication (email/meetings/chat) vs 43% creating; ~11 h/week in email alone;
~1,200 app switches/day ≈ 4 h/week lost — the tax an OS-level agent uniquely removes.

**The money overlap:** the population that is BOTH huge and already paying for the
app concentrates in Microsoft 365 desktop (Excel, Outlook, Word) and Adobe Creative
Cloud, then vertical pro apps (QuickBooks US, DATEV in DACH, AutoCAD).

## 2. What people actually want automated (verified demand ranking)

1. **Cross-app data entry / moving data between apps** — "most dreaded task"; 76% of
   SMB knowledge workers spend 1–3 h/day on it (Zapier/OnePoll n=1,000); 59% want
   data input automated (UiPath n=4,500).
2. **Email triage/drafting/responding** — #1 task workers want automated (60%,
   UiPath); ~28% of the workweek is email (McKinsey).
3. **Finding information/documents** — 86% want AI for this, the #1 AI wish
   (Microsoft WTI 2023, n=31,000).
4. **Data analysis + report generation** — analyze data 52%, input data 50%, run
   reports 48% (UiPath 2023/24).
5. **Scheduling/meetings** — 57% want scheduling automated; 80% want AI meeting summaries.
6. **Invoice processing / AP** — the most-deployed paid RPA use case (accounting vertical).
7. Error fixing/data cleanup (83% spend 1–3 h/day), status updates, CRM entry,
   document drafting, creative batch work (weakest evidence trail of the list).

Demand order ≈ Excel/data-movement, then email, then documents/search, then
scheduling, then invoices/AP — matching the planned branch order almost exactly.

## 3. Pricing evidence

**The accepted market anchor for agent capability is ~$20/mo.** $200-tier agent
gating failed twice in the market (OpenAI folded Operator into the $20 Plus tier
within 6 months; Google's $249.99 Mariner shut down May 2026). Higher tiers only
survive as usage quota, not capability. **The $19 OrphicOS base sits exactly on the
accepted anchor.**

Per-app comparables (what a SINGLE app's AI/automation sustains standalone):

| Product | Scope | $/mo |
|---|---|---|
| Power Automate Premium | attended Windows desktop RPA | $15/user (closest direct comp) |
| MS 365 Copilot | AI inside Office | $30/user ($21 Business SKU) |
| Superhuman / Shortwave / Fyxer | email only | ~$25–30 / $30–45 / $30 |
| SaneBox | email triage only | $7–36 |
| Ajelix / Formula Bot | Excel/Sheets AI only | $20 / $18–29 |
| Aftershoot / Topaz | photo batch only | ~$10–48 / $17–33 |
| Zapier Professional | cloud-to-cloud glue | $20–30 |
| Retouch4me | ~$124–159 ONE-TIME per effect | precedent for per-capability pricing |

**Implication:** Gmail +$9 and Excel +$12 price BELOW every standalone single-app
comparable (email tools alone sustain $25–45; Excel AI tools $18–29). The planned
skill prices are conservative — safe for launch, with headroom to raise once each
skill hits the 3-flawless-recipes bar. A base+2-skills user at $40/mo still
undercuts a Copilot seat + one email tool.

## 4. Who pays most readily (segment ranking, individual-payer lens)

1. **Lawyers (solo/small firm)** — $349/hr average rate; 79% already use AI; already
   pay $49–149/user for practice tools. 10 min/day saved justifies $100/mo.
2. **Real estate agents** — 24% of Realtors spend >$500/mo on tech OUT OF POCKET
   (NAR 2025); best self-payer evidence found.
3. **Accountants/bookkeepers** — $150–400/hr; pay per-client tool pricing (~$18/client);
   own invoice processing, RPA's #1 proven paid use case.
4. **Ecommerce sellers** — self-pay $49–279/mo for seller tools; ROI buyers, churn-prone.
5. **Sales/recruiters** — deep budgets but team-sold, not individual conversion.

Photographers/editors show the most automation-specific buying (supports Adobe skill
at +$15, not higher). Medical admin / EAs score lowest for a screen-data-to-server
product (compliance objections).

## 5. Recommendation — gating & branch order

Confirmed (evidence supports the planned order, with two adjustments worth noting):

1. **`skill-gmail` +$9** — email is the #1 wanted automation; flow already proven
   live. On Windows the email battle is Gmail-in-Chrome (~28% of opens) vs Outlook
   desktop (~8%): Gmail-first is right.
2. **`skill-excel` +$12** — #1 demand cluster (data entry/analysis/reports) on the
   #1 paid desktop population (345M M365 seats). Comparables say this could carry
   $15–20 later.
3. **`skill-adobe` +$15** — 41M paying CC subs, high WTP, killer demo video; but the
   demand evidence is the weakest of the top tier (vendor-mediated surveys). Keep
   third; let locked-hit logs confirm before deep investment.
4. **`skill-accounting` +$15** — QuickBooks (US). **DACH note:** DATEV owns ~80% of
   German tax advisors, all paying, boring captive workflows — a natural
   founder-market-fit variant of this branch for the German launch.
5. **Long tail by locked-hit logs.** Watch for: **Outlook** (same recipes as Gmail,
   the enterprise mirror — likely the cheapest high-value follow-on), Word/
   PowerPoint, Teams/scheduling, PDF/Acrobat (100M+ daily users, forms/signing).

What NOT to gate: File Explorer, browsing/search, window management, generic typing
— that is the $19 door, and the data (app-switching tax, "finding information" as
#1 wish) says the door itself is the daily-habit product that earns the upsell moment.
