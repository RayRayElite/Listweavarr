# Official updates and community publishing

## What is ready locally

Favorites from Plex builds editable local snapshots from watched titles with a personal rating of at least 8/10 or at least two recorded plays. It does not use audience scores as personal ratings, nor treat a TV episode total as a series replay count. A 50-title Favorites snapshot was created in the developer workspace.

Manage list replaces the compressed dropdown with a grouped dialog: Edit & share, Watch order, Plex & watched progress, Source & metadata, Publisher tools and Remove list. Existing handlers and explicit destructive confirmations remain.

## Update delivery without app upgrades

1. A publisher makes and reviews changes in their authoring workspace, then publishes a new local Official version.
2. Publishing generates official-lists.json and official-lists.manifest.json together in the private catalogue directory. Export them and upload both to the same protected publishing location, catalogue first and manifest last.
3. A user configures that public catalogue URL once. Opening Official Lists checks only the small sibling manifest. A newer version produces an Updates available indicator and an inbox notice after the check. No full catalogue, personal list or Plex playlist is automatically replaced.
4. The user opens Updates, previews the source and downloads/installs the reviewed catalogue when ready.
5. They separately preview changes to their personal copy, choose merge/replace/skip, and can roll back the copy update.
6. Updating a Plex playlist is a separate preview and confirmation. Media acquisition remains separate too.

Only compatible data changes can be delivered this way; a future catalogue schema requiring new code still needs an app update. The default public publisher endpoint is now the repository's raw `main/catalogue/bundled/official-lists.json`, with its sibling manifest. An explicitly saved custom URL is preserved; saving an empty source disables checks. Automatic manifest checks occur once per browser session when Official Lists opens, not while the app is closed.

### Maintainer publishing procedure

1. Publish/review local Official versions with curator mode. Export the public
   catalogue and review it for redistribution rights. The public repository must
   not include embedded third-party artwork or private runtime fields.
2. Put the reviewed, artwork-free JSON at
   `catalogue/bundled/official-lists.json`. Keep stable list IDs; increment each
   changed list's version. No version increment is needed for unchanged lists.
3. Run `python scripts/prepare_catalogue_feed.py`, then
   `python scripts/check_release.py`. Commit the catalogue and generated manifest
   together. CI rejects a missing/stale manifest.
4. Review/merge that commit into main. GitHub serves the new data at the same raw
   URL; users do not need to install new application code. Allow for HTTP caching.
5. Users choose the catalogue update, personal-copy update and Plex update
   independently. Publishing does not initiate any of those writes for them.

The repository's CODEOWNERS requests publisher review for catalogue changes. It
does not itself enforce review: required-review/ruleset configuration is a
separate GitHub repository administration step. Direct write access must be
restricted to trusted maintainers; no credentials are shipped to consumers.

## Publisher and curator authority

Normal launches disable the Official publishing API and hide the publisher tools. The developer launcher Start Listweavarr Curator.cmd enables local authoring via LISTWEAVARR_CURATOR_MODE=1. Restart the server when switching modes.

This local flag prevents accidental publication in consumer installations; it is NOT authentication or proof of approved-curator identity. Anyone controls their own local installation. The shared source must enforce publishing authority independently: for the first release, GitHub repository permissions plus protected branches/review requirements. Users can edit their own copies but cannot write to your repository. No shared publisher credential should ever be embedded in the app. Curators submit changes for review; you retain final release control. A future hosted publishing API must check server-issued roles on every write and retain revocation/audit history.

## Recommended low-cost hosting

Start Official distribution with a public GitHub repository and a static catalogue URL. Public repository collaboration and protected branches are available on GitHub Free. Separate catalogue data from the app so releases are independent. Keep account secrets and local app state out of that repository. A custom domain is optional.

For a real Community directory, prefer a Cloudflare Worker API with D1 for indexed list metadata/version history and R2 for poster files and immutable list snapshots. Workers Free currently offers 100,000 requests/day, D1 has a free allocation, and R2 Standard includes 10 GB-month storage with free Internet egress. Free allowances may cover a small launch; that is an estimate, not a guarantee. Workers Paid starts at US$5/month plus usage; database/storage/operations can add costs. Enforce quotas, size limits, pagination and caching from day one.

Supabase is the simpler alternative when built-in authentication and Postgres matter more than the lowest upgrade cost. Free includes 500 MB database and 1 GB file storage but pauses inactive projects after a week; Pro starts at US$25/month. Cloudflare is the stronger fit for the requested low monthly budget, with more authentication integration work.

Sources checked 26 October 2026:
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/r2/pricing/
- https://supabase.com/pricing

## Proposed Community scope (not deployed)

Keep Community separate from Official. Lists are private by default and publication is explicit. Share only title IDs/order, descriptions, creator-selected art, tags and public author identity; never share Plex inventory/watch history, ratings, download routes, requests or credentials. Show the exact public preview before upload.

Begin with accounts, author profiles, public/unlisted/private visibility, versioned snapshots, search/filtering, follows, update notices and personal-copy imports. Add attribution/source links, spoiler labels and curator picks. Avoid comments/direct messages initially to limit moderation overhead.

Required service controls: authenticated ownership checks, trusted curator role distinct from list author, rate limits, reporting, hide/unpublish, moderator audit trail, account revocation and removal of inappropriate uploads. An official badge comes from your approved source or verified server role, never from a client-supplied field. Users receive the same opt-in version-update workflow as Official lists.

No accounts, public repository, hosting service or billing plan were created in this change. File-based list sharing remains available while the hosted directory is being designed.

## Verification

333 Python tests passed, plus the Node UI regression harness and static shell checks. Chrome confirmed the saved 50-title Favorites list, reusable preview with personal-rating/play-count reasons, grouped management dialog, working Close and catalogue return navigation. No public list upload, account creation, Plex playlist update or acquisition was performed.
