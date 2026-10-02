# AshFall resource pack

Resource pack for the AshFall/AshFallSmp Minecraft server (BrotherSMP). Served to clients
from the URL in the server's `server.properties`, so the URL must stay stable.

Contains the custom title/logo assets and `ashfall/warden_spear` (the black Warden Spear
texture used by the AshFall plugin).

## Updating

1. Edit the sources in `pack/` or `build_pack.py`.
2. Rebuild: `python3 build_pack.py`
3. Copy the rebuilt `ashfall-pack.zip` from the parent directory over the one here.
4. Commit, push, then run `../set-pack.sh <raw-url>` on the server host to refresh the
   sha1 in `server.properties`.

The client rejects a pack whose sha1 does not match `resource-pack-sha1`, so step 4 is
required after every upload or players get a failed download.
