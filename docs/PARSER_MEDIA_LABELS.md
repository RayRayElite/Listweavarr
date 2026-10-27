# Titles, years and media labels

The text builder separates labels from searchable titles, for example:

- `Jurassic Park (1993 Movie)` → movie, Jurassic Park, 1993.
- `Dune: Prophecy (2024 TV Series) — 2 Seasons, 14 Episodes` → the TV show,
  with its year. These catalogue totals do not request a season/episode range.
- `My Hero Academia: Two Heroes (Movie 1)` → movie; the sequence number is not
  included in the search query.
- `Vought Rising (Upcoming Prequel Series) — Set in the 1950s` → TV show;
  the story's setting is not its release year.
- `Seven on 7 with Cameron Coleman (Web Series — Episodes 1–9)` → a continuous
  episode range of the named show.
- `The Boys Presents: Diabolical — Episode 6: "Nubian vs Nubian" & Episode 7:
  "John and Sun-Hee"` → two episode proposals, retaining their stated order.

Explicit season scopes still take priority. Placement notes stay available in
the source for review; they do not invent additional episode scopes.

Anime, OVA, ONA and special labels do not by themselves establish a movie or
parent-show episode identity. These entries search movie and TV catalogues for
review. If TMDB stores an entry only under its parent show's specials, select
the parent and enter its verified episode scope (usually season 0). A label is
not enough evidence to invent that scope. Upcoming catalogue entries may also
have incomplete metadata.

The builder rejects a year/media annotation with no title instead of guessing
which film was intended. Title parentheses such as `(Hero League Baseball)`
remain searchable; recognized catalogue labels are removed.
