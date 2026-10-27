# Continuous episode numbering

In **Build from website or text**, named episode ranges without a season are
automatically treated as continuous numbering:

```text
Naruto (Episodes 1–101)
Naruto the Movie: Ninja Clash in the Land of Snow
Naruto (Episodes 102–160)
```

Match and confirm the parent show, then use **Preview expanded order** to inspect
the resulting episodes before creating the list. Movies keep their positions
between episode blocks. Explicit scopes such as `Season 2, Episodes 1–3` retain
per-season numbering. The row's Numbering control allows a manual override.

The mapper counts regular TMDB seasons in order, excludes specials, and reads
actual episode records in the intersecting seasons. This supports both seasons
that restart at episode 1 and anime seasons that retain continuous episode
numbers. Missing seasons, inconsistent episode counts and out-of-range requests
require correction rather than silently dropping episodes.

Select the correct series and edition. A recut, edited dub, production order or
guide that includes specials in its episode count may not match the regular TMDB
order. Continuous numbering alone cannot establish equivalence between editions.
Optional movies remain proposed entries; exclude any you do not want before saving.
