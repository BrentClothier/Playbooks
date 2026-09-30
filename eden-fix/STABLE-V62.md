# Eden Minecraft Stable v62 Baseline

Status: **known-good / frozen baseline**

This document records the exact build state that passed the long-duration two-player Minecraft split-screen test on Linux. The stable code itself is preserved unchanged on branch `eden-minecraft-stable-v62`.

## Source identity

- Repository: `BrentClothier/Playbooks`
- Frozen branch: `eden-minecraft-stable-v62`
- Investigation branch: `eden-minecraft-v62-investigation`
- Frozen Playbooks commit: `711443437fd7f92d9343939c3387743f0a1ea5da`
- Pinned Eden source: `eden-emulator/mirror` commit `54046ac60ef5d8876b550be2546b89d48751de7e`
- Release tag: `eden-minecraft-linux-accurate-cpu-v62-2`

## Binary identity

- AppImage: `Eden-Linux-minecraft-accurate-cpu-v62-amd64-gcc-standard.AppImage`
- AppImage size: `91,135,998` bytes
- AppImage SHA256: `f92a94dd02901cd8345731c0a705db90147b8b734dd7a4f9980e4cd9b02564dd`
- Source tarball SHA256: `89e43bafdab1eb073ef06984613b03688aa5c67be159e9e45e253951dc7d530e`
- SHA256SUMS asset SHA256: `f468d88f9bf2a735ec4a4758a75fab0836d41a07d4010ad3308ac15b667f5165`

## Tested game/environment

- Minecraft title ID: `0100D71004694000`
- Minecraft version: `1.26.45`
- Update: `v0.160.0`
- Firmware: `22.5.0`
- Linux Mint 22.3
- Intel Core i7-13700KF
- NVIDIA GeForce RTX 3060 Ti
- NVIDIA driver 580.178.4
- Vulkan 1.4.312
- Docked mode
- 1x resolution
- 1920x1080 output, two-player split-screen
- Vulkan renderer
- GPU accuracy High
- async GPU emulation off
- async presentation off
- GPU buffer readback on
- sync memory operations on
- CPU accuracy Accurate for Minecraft

## Stability result

Long-duration test completed on 2026-09-29/30.

- Player 2 joined successfully.
- Two-player gameplay remained stable for about 1 hour 50 minutes after Player 2 joined.
- This exceeded the historical ~21 minute failure window by more than 5x.
- No recurrence of the prior null-execution fault (`Cannot execute instruction at unmapped address 0x0`).
- HUD/menu flicker remained fixed.
- Controllers remained functional.
- Save commits remained successful throughout the run.
- Session ended by manual emulator stop, not by the historical runtime failure.

This is the baseline to return to if later experiments regress behavior.

## Required compatibility stack

Preserve the complete working stack through v62. In particular:

- v42 shader scan bound / runaway assertion fix
- v43 malformed graphics pipeline rejection
- v53 split-screen half-screen clear behavior
- v55 save/session and additional-user state fixes
- v59 Docked accelerated presentation / HUD flicker fix
- v60 durable filesystem commit
- v62 Minecraft-only Accurate Dynarmic CPU behavior

Do not add the speculative v61 null-callback bypass to this baseline.

## Known non-fatal diagnostics

The successful long run still contains diagnostic noise that is not currently considered release-blocking:

- Maxwell macro assertion: `assert method == executing_macro + 1`
- bounded malformed/unterminated shader rejections caught by the v42 guard
- a large burst of unmapped guest-memory read/write diagnostics during part of the run
- tolerated legacy `D401` SVC diagnostics
- shutdown-time guest panic after manually force-stopping the emulation thread

These may be investigated on `eden-minecraft-v62-investigation`, but no fix should be merged into the frozen baseline without a separate long-duration regression test.

## Future deployment direction

A future goal is to package/deploy this stable Eden build in a RomM-adjacent/containerized game-streaming workflow so launching Minecraft can be presented through a friendlier library UI instead of relying on a manual Sunshine/Moonlight launch path.

Treat that as a deployment/integration project. Do not modify the frozen emulator baseline merely to accommodate the frontend.
