# Managed native Plex collections

Open a saved list, choose **Manage list → Plex & watched progress → Plex
collection**, select a library and preview. Only homogeneous lists of movies or
whole shows are eligible. Mixed movie/TV, season and episode watch orders remain
playlists. This follows Plex's collection model; collections are not a substitute
for an interleaved episode queue.

The preview names omitted/unmatched entries, duplicate memberships included once,
and additions/removals/order changes. Explicit provider IDs or a manually confirmed
match on this server are required. Matching collection names never authorize
overwriting an existing collection. A collection created here is saved by server,
library, collection key and GUID. Renames, replacements and smart collections
require separate attention rather than guessing what to overwrite.

Confirm publishes the reviewed contents in source order with custom collection
sorting and the portrait list poster when available. Previewing does not acquire
media or change Plex. A preview expires after 15 minutes; changed curation,
connections, availability or collection contents require another preview.

Later previews update that saved collection **in place**, retaining its identity
and existing Home visibility. Removing membership does not delete media files.
Home promotion itself is not configured by this workflow. Plex collections are
shared library objects, unlike a user's playlist; review removals accordingly.

Plex does not provide a transaction for the whole update. The target is
checkpointed locally before subsequent writes. If a request fails, the existing
collection and any completed changes remain. A visible attention note directs you
to preview its actual current contents; requests are not automatically retried.
This also avoids creating another collection after an interrupted creation.
An unconfirmed creation response still requires checking Plex before retrying.

Portable workspace restoration discards publication authority, just as it does
for playlists. Public shared/Official catalogue files do not contain managed
collection keys or ownership claims.

Verification: synthetic tests cover scope restrictions, duplicate members,
library selection, identity drift, interrupted checkpoint recovery and single-use
confirmation. A disposable live collection passed creation, addition, removal and
reordering while retaining its key, then was removed; existing user collections
and media were not changed. Poster upload uses the tested metadata-artwork helper.

API references: [Plex Media Server API](https://developer.plex.tv/pms/) and
[Python-PlexAPI collection contracts](https://python-plexapi.readthedocs.io/en/latest/modules/collection.html).
Our implementation is original code, not a copied client library.

If a target was deleted/renamed, or you want to publish somewhere else, choose
Unlink saved target. This removes only the local management link after explicit
confirmation; the collection in Plex remains unchanged. Unlink works even when
Plex is unavailable. Creating another collection still requires a unique name.
