# Design research — restrained product sites

Studied 2026-07-03 (live fetches). Purpose: extract the actual mechanics of the
"expensive, quiet" feel before redesigning the OrphicOS landing page.

## Site notes

### anthropic.com
- Hero: nav → one declarative headline → one supporting paragraph → one CTA. ~4 elements above the fold.
- Type: single sans family, headline ~48–56px vs ~17px body (≈3x jump); hierarchy from scale, not from mixing faces.
- Monochrome black/white/grey; accent color only on interactive elements.
- Essentially static — institutional gravitas over micro-interactions.
- Lesson: confidence = one message, huge, alone.

### stripe.com
- Hero: value proposition left, one animated visual right; two CTAs max.
- Serif-weight display headline vs sans body — serif for authority, sans for utility.
- Strict, consistent vertical padding between sections; uniform grid gaps ("curated, not cluttered").
- Neutrals-forward; accent color rationed to CTAs.
- Lesson: one indulgent visual is allowed if everything else is austere.

### linear.app
- Centered hero, one sentence, repeated rather than escalated. Restraint through repetition.
- Avoids size extremes between supporting text levels; testimonials spatially isolated so each breathes.
- Near-monochrome; motion reserved for interactive elements only.
- Lesson: elegance by subtraction — consistent scale, whitespace instead of decoration.

### vercel.com
- Modular narrative: each section = headline + one visual, identical padding cadence → predictability reads as reliability.
- One conservative sans family across all weights.
- Animation-minimal; every visual is informational, never decorative.
- Lesson: rhythmic regularity is itself a trust signal for infrastructure products.

### arc.net
- Hero anchored by a human quote instead of marketing claim; download buttons immediately present.
- Consistent image → headline → description interval per section.
- Neutrals let product screenshots carry the color.
- Lesson: conversational honesty + immediate conversion path.

### teenage.engineering
- Modular grid, clinical product photography: cropped, centered, no lifestyle context.
- Technical naming (EP–133, PO-32) in caps/lowercase pairs = engineering credibility.
- Grayscale until color MEANS something (the one red unit).
- Lesson: clinical documentation of the object reads as precision; ration color to a single deliberate accent.

### are.na
- Whitespace as a thinking tool; ideas in isolated chunks; lowercase, plain language.
- Sparse imagery — typography and ideas dominate.
- Lesson: the page can model the product's calm instead of describing it.

### rijksmuseum.nl/collection (museum reference)
- Neutral white/grey ground; artwork as the only saturated object → the object reads premium.
- Small, quiet sans captions that never compete with the image; heavy vertical spacing.
- Institutional markers (certifications, opening hours) ground digital in physical authority.
- Lesson: "historical, seriously" = neutral gallery ground + framed object + small factual caption plate.

### davidrumsey.com (archive reference)
- Standardized archival caption format: Title; Creator; Date; Number. Structure itself signals scholarship.
- Serif for formal authority, uppercase for section breaks, sparing blue accents.
- Emphasis on the artifact, minimal framing chrome.
- Lesson: rigid metadata formatting is an aesthetic — precision as decoration.

## The "expensive" formula (recurring across all nine)

1. **Oversized type, few words.** One headline, 3–4x body size, serif or heavy — then silence.
2. **Extreme whitespace.** Vertical padding most sites would consider wasteful.
3. **Tiny element count.** 4–5 things above the fold, one CTA path.
4. **Perfect alignment + strict rhythm.** Identical section cadence; predictability = reliability.
5. **Monochrome until it matters.** Neutral ground; one accent, rationed.
6. **Restrained motion.** Static or one gentle move; nothing decorative.
7. **Honesty as a design element.** Real commands, factual captions, archival formatting.

## Rules adopted for the OrphicOS variants

- Type scale ratio ≥ 1.5 between levels; hero headline `clamp(3rem, 8vw, 7rem)`.
- Max 2 font families per variant; body line-height ≥ 1.6.
- Spacing on a strict 8px rhythm.
- One accent interaction max; zero JS.
- Palette = the sampled banner tokens (the colors are the brand, not the image placement).
- Museum plate (A) borrows Rijksmuseum: bone gallery wall, framed artwork, factual caption plate.
- Terminal heritage (B) borrows teenage.engineering + Vercel: monospace precision, clinical documentation of one real command.
- Type only (C) borrows Anthropic + are.na: the sentence IS the page.
