# Encoding Benchmarks

Reproducible strategy for comparing post-download encoding modes.

## Modes to Compare

1. **Direct / remux** — source already compatible; stream copy
2. **Software x264 medium** — `-preset medium -crf 28`
3. **Software x264 ultrafast** — `-preset ultrafast -crf 28`
4. **Android MediaCodec H.264** — `h264_mediacodec` VBR (when available)
5. **Android MediaCodec HEVC** — `hevc_mediacodec` VBR (when available)

## Fixture Requirements

- Use a **local file** produced by the downloader or a synthetic fixture
- Do **not** embed adult URLs in scripts or tests
- Same source file, target max height, and comparable duration window for all runs

Suggested synthetic baseline (matches reference device tests):

```bash
ffmpeg -hide_banner -y \
  -f lavfi -i testsrc2=size=854x480:rate=30 \
  -t 30 -pix_fmt yuv420p \
  -c:v libx264 -preset medium -crf 23 \
  -c:a aac -b:a 128k \
  fixture_854x480_30s.mp4
```

Real-world benchmarks should repeat with at least one **downloaded** HLS merge output once Phase 1+ is deployed.

## Metrics

| Metric | How |
|--------|-----|
| Wall-clock time | `time` or app job elapsed |
| Realtime multiplier | `duration_sec / wall_sec` |
| Output size | `stat -c%s` |
| Average bitrate | `ffprobe -show_entries format=bit_rate` |
| CPU utilization | `top` / `/proc/stat` sample during encode (optional) |
| Temperature | thermal zone reads on Android (optional) |
| Failure / fallback | log whether hardware fallback occurred |

## Example Commands (Manual)

### Direct remux

```bash
ffmpeg -y -i fixture.mp4 -c copy -movflags +faststart out_remux.mp4
```

### Software medium

```bash
ffmpeg -y -i fixture.mp4 -vf scale=-2:480 \
  -c:v libx264 -preset medium -crf 28 -threads 0 \
  -c:a copy -movflags +faststart out_sw_medium.mp4
```

### Software ultrafast

```bash
ffmpeg -y -i fixture.mp4 -vf scale=-2:480 \
  -c:v libx264 -preset ultrafast -crf 28 -threads 0 \
  -c:a copy -movflags +faststart out_sw_ultra.mp4
```

### MediaCodec H.264 (Android)

```bash
ffmpeg -y -i fixture.mp4 -vf scale=-2:480 \
  -c:v h264_mediacodec -bitrate_mode vbr -b:v 1000k -g 60 \
  -c:a copy -movflags +faststart out_hw_h264.mp4
```

### MediaCodec HEVC (Android)

```bash
ffmpeg -y -i fixture.mp4 -vf scale=-2:480 \
  -c:v hevc_mediacodec -bitrate_mode vbr -b:v 1000k -g 60 \
  -c:a copy -movflags +faststart out_hw_hevc.mp4
```

## In-App Benchmarking (Future)

A dedicated script or pytest marker `@pytest.mark.device` may wrap the application `post_process_media()` path with timing hooks. CI runs unit tests only; device benchmarks are manual on reference hardware.

## Notes

- Synthetic `testsrc2` results **do not** predict full pipeline performance (HLS merge, decrypt, I/O).
- MediaCodec speed vs software depends on resolution, device, and whether decode+scale dominates.
- Record FFmpeg build flags (`ffmpeg -version`) with each benchmark row.
