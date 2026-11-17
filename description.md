# Transcode If Not Direct Playable

Unmanic file-test plugin. Queues a file for transcoding **only** when its
video is not directly playable on modern clients (Nvidia Shield, Google TV,
desktop browsers, current Roku/Fire TV hardware).

## What gets queued

- Containers that never direct play: `avi, wmv, flv, ogm, ts, m2ts, mov`
  (configurable)
- Legacy / software-only codecs: `mpeg4, msmpeg4*, mpeg1video,
  mpeg2video, vc1, vp8, theora, av1` (configurable)
- H.264 that is not 8-bit 4:2:0 — Hi10P (`yuv420p10le`), `yuvj420p`,
  `yuv422p` — no hardware decoder exists for these (configurable)

## What is deliberately left alone

- **HEVC** (including Main 10 / HDR) — direct plays everywhere modern
- **8-bit H.264** (`yuv420p`) — the universal codec
- **VP9** — hardware-decoded on all modern clients

Unknown video codecs are queued (assumed not playable) rather than
silently skipped. Unprobable files return no answer so other plugins
can decide.

## Setup

1. Install this plugin in Unmanic.
2. In each library's **File Test flow**, place it **first**, ahead of the
   Transcode Video Files plugin. Unmanic stops at the first definitive
   answer, so files answered "no" here never reach the transcoder.
3. Tune the codec/container lists in the plugin settings if needed.
