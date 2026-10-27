# Parallel watch blocks

Use Build from website or text, infer entries, match the shows and confirm their
scopes. Explicit parallel blocks alternate one episode from each listed scope.
The first listed title starts. This is a requested watch pattern, not an inferred
airing-date or crossover chronology.

## Supported forms

Two named, scoped titles on one line:

```text
Criminal Minds (Season 11) / Criminal Minds: Beyond Borders (Season 1)
Criminal Minds (Season 12) / Criminal Minds: Beyond Borders (Season 2)
Criminal Minds (Seasons 13-15)
```

Each slash-separated line is its own parallel block. The final line resumes
ordinary sequential order. Up to eight lanes are supported.

A parallel note followed by the exact other scope:

```text
Criminal Minds (Season 6, Episodes 1-13)
Criminal Minds: Suspect Behavior (Season 1) (Runs parallel to the rest of Criminal Minds Season 6)
Criminal Minds (Season 6, Episodes 14-24)
Criminal Minds (Seasons 7-10)
```

The note connects Suspect Behavior to the next explicitly scoped Criminal Minds
entry. Suspect Behavior starts because it is listed first in that block. The
earlier episodes 1-13 remain outside the block. A note without an explicit next
scope requires correction; the parser does not invent what “the rest” means.

## Unequal lengths and review

Shorter lanes stop when exhausted. Longer lanes finish without dropping any
episodes, then normal list order resumes. Multiple seasons in a lane run in
season/episode order inside that lane.

The review cards show lane numbers and the starting lane. After confirming all
matches, use Preview expanded order to inspect the actual interleaving. It reads
metadata without saving a list or requesting downloads. Saving validates the
scopes again. Make block sequential removes alternation from all lanes in that
block and asks you to reconfirm them.

Whole seasons in parallel blocks expand into verified episode records. Missing,
duplicate or incomplete episode numbering requires correction. If you remove a
lane, restore it or make the remaining block sequential. Show-only and movie
entries cannot be parallel lanes. When appending to an existing list, duplicate
skipping still applies; disable it if repeating an episode is intentional.

Parent-show matching remains explicit. Edition names and revival branding do not
override TMDB season numbering; review the parent match and available seasons.
