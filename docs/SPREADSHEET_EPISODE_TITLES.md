# Spreadsheet episode-title matching

The builder recognizes `Show`/`Series` columns paired with `Name`, `Title` or
`Episode title`. Explicit Season/Episode coordinates still take priority.
When coordinates are absent, the extractor emits:

```text
CSI: Crime Scene Investigation | Episode title: Cool Change
```

This requests title matching inside the named show's TMDB catalogue. Custom
`Code`, `Number`, release-order keys and spreadsheet dates are not decoded as
season/episode numbers. Worksheet row order remains the watch order.

Structured title-only rows search specials and regular seasons, up to 100 regular
seasons per show. TMDB responses use the existing metadata cache. Failed catalogue
reads require a retry instead of accepting incomplete results. Ordinary prose
special entries retain their narrower matching scope.

Exact matches are preferred. If none exist, catalogue rows can normalize leading
“The”, `and`/`&`, and numbered part labels such as `Part II` versus `(2)`. Adjacent
parts 1 through N of the same named story in one season can become one episode
range. The proposed range is shown for confirmation. Different candidates remain
choices, and spelling discrepancies require correction; no fuzzy match is
silently accepted.

Use the review screen and expanded-order preview before saving. A successful
extraction proves that rows were retained, not that all source titles are correct
or that their order is an independently verified chronology.
