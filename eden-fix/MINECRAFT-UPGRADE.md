# Minecraft split-screen: upgrading to a new Eden release

## Known-good reference

- Known-good behavior baseline: v53 (Minecraft 1.26.45 / update v0.160.0).
- Clean production packaging: v54.
- Historical Eden baseline: `54046ac60ef5d8876b550be2546b89d48751de7e`.
- Do not replay the historical v7-v53 sequence on a new Eden release. Those revisions are the
  debugging history, not a permanent dependency chain.

## Porting strategy

1. Create a fresh branch from the new Eden release commit/tag.
2. Run unmodified Eden with Minecraft 1.26.45 using the known-good game settings.
3. Test in this order:
   - title boot and main menu;
   - existing save/world load;
   - Player 2 profile selection;
   - split-screen join;
   - 5+ minutes of gameplay;
   - both players' HUD/menu;
   - death/respawn;
   - clean exit/relaunch.
4. Only port a compatibility area when the vanilla test demonstrates it is still missing.
5. After each port, rerun the short matrix above. Keep one patch per functional area, not one patch
   per historical experiment.

## Functional compatibility areas

### 1. Boot / memory compatibility
Historical core: v17.

Minecraft used DeviceShared transfer memory that the pinned Eden baseline rejected. Port only if
the new Eden still fails during transfer-memory creation.

### 2. Graphics / image-alias compatibility
Historical core: v26-v30.

Important behaviors include framebuffer extent clamping, viewport-transform-sensitive pipeline
keys, sample-aware alias synchronization, and relaxed alias discovery across MSAA sample counts.
Port only the pieces still absent from the new texture-cache/render code.

### 3. Cache / save-data compatibility
Historical core: v31-v38 plus v52.

This includes cache-storage sizing/reader behavior, save-data UUID/program-ID handling, quota
reporting, and Minecraft 1.26.45's fsp-srv command 33 DeleteCacheStorage compatibility behavior.

### 4. Additional-user / split-screen account state
Historical core: v39-v41.

This is the profile selector, second-controller navigation, additional-user selection, and shared
open-user state required for a real second local player.

### 5. Shader safety / rotating-prefix compatibility
Historical core: v42-v50.

Keep the safety invariants: no unbounded shader scan, no arbitrary synthesized bytes, reject
unmapped/malformed shaders safely, and only repair the proven narrow Minecraft rotating-boundary
cases with the canonical Maxwell EXIT.

### 6. Split-screen clear compatibility
Historical core: v53.

The successful run proved the flicker was caused by player-half clears becoming full 1280x720
clears. The guest had clear_control.use_clear_rect=1 while Eden's Vulkan clear path only used
clear_control.use_scissor. The old v53 compatibility patch uses the exact 1280x360 player-half
rectangle after split-screen activation.

For a new Eden release, prefer a correct generic implementation of Maxwell use_clear_rect if the
register semantics can be verified. Otherwise port the narrow v53 compatibility rule unchanged.

## Current upstream snapshot (2026-09-20)

Eden master `a277b62fe4328dddaced9a97d324c6e5478d16a0` is 146 commits ahead of the historical baseline.
At this snapshot, source inspection still shows:

- fsp-srv command 33 DeleteCacheStorage registered as unimplemented;
- Vulkan Clear selecting a rectangle from use_scissor, not use_clear_rect;
- GenericEnvironment::TryFindSize scanning up to 1 MiB without the mapped-boundary guard used by
  the Minecraft shader fixes;
- transfer-memory locking still rejecting DeviceShared in the generic path.

Therefore a future release cut from approximately this code will probably still need a small
Minecraft compatibility layer. It should be ported as functional patches, not 54 sequential
revisions.

## Recommended branch model

Keep the known-good v53/v54 branch frozen. For each new Eden release, create a new branch named
for the upstream release/commit, e.g. `eden-<release>-minecraft-port`. The old branch remains a
working fallback until the new branch passes the complete test matrix.
