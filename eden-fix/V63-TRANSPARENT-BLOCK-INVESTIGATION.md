# v63 Transparent-Block Investigation

This investigation is intentionally isolated from the frozen known-good branch `eden-minecraft-stable-v62`.

## User-visible symptom

During the successful long-duration v62 two-player test, many Minecraft blocks temporarily appeared transparent / missing. The visual problem later recovered without restarting the game.

The emulator did not crash and save commits continued.

## Correlated log event

The same gameplay session contains a large burst of unmapped guest-memory accesses in a very small virtual-address region beginning near:

`0x00001200000000`

Detailed offline analysis of the successful v62 log found:

- first suspect access: about 2053.384 s
- last suspect access: about 2575.451 s
- duration: about 522.067 s (~8m42s)
- Read8: 154,457
- Write8: 122,480
- Read64: 6
- Read32: 2
- WriteExclusive64: 2
- total suspect accesses: 276,947

The byte-access storm touches a contiguous span from:

- `0x0000120000004b`
- through `0x00001200000b1a`

That is exactly 2,768 bytes, equal to 173 * 16-byte records.

## Strong geometry/subchunk signature

The first write burst populates 1,696 bytes, exactly 106 * 16-byte records.

Interpreting each record as:

```text
uint32 index_or_id;
float x;
float y;
float z;
```

produces a strikingly coherent result:

- all 106 integer fields are monotonically increasing;
- all 106 XYZ triples are finite and plausible;
- all 106 XYZ coordinates are exact integer or half-integer values;
- X range: 0.0 to 14.0
- Y range: 0.5 to 10.5
- Z range: 0.5 to 15.5

Example records reconstructed directly from Write8 values:

```text
2,   2.0,  4.5,  2.5
6,   2.0,  5.5,  2.5
10,  2.0,  6.5,  2.5
15,  2.0,  8.5,  2.5
19,  5.0,  4.5,  1.5
23,  5.0,  5.5,  1.5
...
60, 12.0,  0.5, 12.5
64, 12.0,  1.5, 12.5
...
```

The 0..15.5 coordinate scale is highly consistent with Minecraft block/subchunk-local geometry.

The current leading hypothesis is that this is a per-face/per-quad render metadata array, potentially an index plus face center used for chunk mesh processing or transparency sorting. This is an inference from the binary pattern, not yet a symbol-level identification.

If Eden treats the virtual page as unmapped, reads return zero and writes are discarded. Repeated sort/update operations on such an array could therefore explain a temporary missing/transparent block rendering state. Later chunk rebuild/reallocation could explain self-recovery.

## Event structure

The event is bursty rather than a single continuous tight loop.

- Initial geometry-like write burst occurs at ~2053.39 s.
- There is then a long quiet gap.
- Heavy repeated read/write bursts resume around ~2305 s and continue intermittently until ~2575 s.
- Many later bursts contain equal read and write volumes, consistent with copying, sorting, or rewriting fixed-size records.
- At the end of the event, wider accesses appear around offsets 0xf0-0x138, including two WriteExclusive64 operations at `0x00001200000130`. These may represent synchronization/reference-count activity associated with the same stale object or allocation.

## v63 diagnostic goals

v63 preserves v62 execution behavior and adds only diagnostics/log rate limiting.

At the next reproduction, capture:

1. Live Dynarmic guest PC and instruction at accesses to `0x1200000000-0x120000ffff`.
2. Guest SP and general registers so the invalid base/index register can be identified.
3. CPU virtual map/unmap operations intersecting that range.
4. Rasterizer cached/uncached page transitions for that range.
5. GPU device virtual address -> CPU backing mappings involving that range.
6. GPU cached-page refcount changes for device pages backed by that range.

The critical distinction is:

- **kernel/page-table says the region should be mapped:** likely Eden CPU/GPU mapping bookkeeping bug;
- **kernel/page-table also says unmapped:** likely a stale guest pointer/lifetime problem exposed or tolerated by Eden;
- **GPU device mapping outlives CPU backing:** likely stale device/texture-cache mapping;
- **same guest PC repeatedly performs the accesses:** disassemble that instruction/function and identify the exact record operation.

## Safety

Do not change `eden-minecraft-stable-v62` while investigating.

Any behavioral fix derived from v63 must be implemented separately and pass another long-duration two-player regression test before it is considered for a future stable build.
