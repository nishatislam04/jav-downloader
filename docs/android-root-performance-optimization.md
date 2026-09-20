# Android Root Performance Optimization — Future Roadmap

> **DOCUMENTATION ONLY** — Do not implement kernel/root tuning in the application yet.
> This plan is for a future phase after application-level encoding optimizations are stable.

## Scope Separation

| Layer | Status | Examples |
|-------|--------|----------|
| **Application-level (current)** | Implemented / in progress | Direct remux, MediaCodec, software fallback, thread config, temp file handling |
| **Root / kernel-level (future)** | Documented only | cpufreq, governors, cpusets, thermal sysfs, fixed-performance mode |

**DO NOT DISABLE THERMAL PROTECTION.** Future work must never bypass thermal throttling or cooling safeguards.

---

## Goals (Future)

- Reduce encoding wall-clock time during sustained loads on rooted Android devices
- Improve CPU/GPU availability **safely** and ** reversibly**
- Remain portable — no hardcoding for a single device (e.g. Snapdragon 7s Gen 2 / garnet)
- Capability-driven: detect sysfs nodes, governors, and APIs before use
- Log every change with before/after state for rollback

---

## 1. CPU Frequency Policy Inspection

**Future behavior:**

- Read `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq`
- Read `scaling_max_freq`, `scaling_min_freq`, `cpuinfo_max_freq`
- Compare online cores vs total cores
- Record governor name from `scaling_governor`

**Never assume** fixed frequencies. Values change with load, thermals, and charging state.

**Rollback:** Store original `scaling_max_freq` and governor per core before modification.

---

## 2. CPU Governor / WALT Behavior

Qualcomm Android kernels often expose **WALT** (Window-Assisted Load Tracking) on big.LITTLE devices.

**Future investigation:**

- When governor is `walt`, understand interaction with task placement
- Compare against `schedutil`, `performance`, `powersave`
- Opt-in `performance` governor only during active encode jobs, with automatic restore

**Risks:** Heat, battery drain, UI jank if applied globally or left enabled after crash.

**Detection:**

```text
/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors
```

Only offer governors present in that list.

---

## 3. CPU Affinity / taskset

**Future behavior:**

- Optionally pin ffmpeg worker threads to big cores (CPU 4–7 on typical 4+4 layouts)
- Use `sched_setaffinity` or `taskset` via subprocess wrapper
- Detect core topology from `/sys/devices/system/cpu/cpu*/topology/core_siblings_list`

**Fallback:** If affinity fails (EPERM, invalid mask), continue without pinning.

---

## 4. Process Priority / nice

**Future behavior:**

- Lower nice value (higher priority) for active encode child process only
- Requires appropriate privileges on some ROMs
- Restore on job completion / cancellation

**Safe default:** No change unless user enables “Performance mode (root)”.

---

## 5. Cpuset / Cgroup Considerations

**Future investigation:**

- Inspect `/dev/cpuset/` and cgroup v2 paths
- Some ROMs restrict background groups; encoding may run in restricted cpuset
- Potential: move encode process to top-app or foreground cgroup **if** KernelSU/root allows and ROM supports it

**High risk** on custom ROMs — must be opt-in with explicit warning.

---

## 6. schedutil / WALT Interactions

Document observed behavior on reference device (crDroid, Android 16, WALT governor):

- Reference only — do not hardcode
- Benchmark governor switches with sustained ffmpeg encode
- Measure thermal status via `/sys/class/thermal/thermal_zone*/temp`

---

## 7. Fixed Performance Mode

Android exposes (when available):

```bash
cmd power set-fixed-performance-mode-enabled true|false
```

**Future requirements:**

- Detect `cmd power` availability via subprocess probe
- Opt-in toggle with heat/battery warning
- Enable at job start, disable in `finally` block and crash handler
- Never treat as mandatory for downloads to work

---

## 8. Qualcomm / Android Performance Hints

**Future investigation:**

- `PowerManager` performance hints via JNI / Termux API bridge (if feasible)
- `ADPF` / game mode interactions on some OEM skins
- Document what works on crDroid vs stock MIUI without assuming either

---

## 9. GPU Performance Considerations

Hardware MediaCodec may use GPU/VPU blocks independently of CPU governor.

**Future work:**

- Monitor whether root CPU tuning materially affects MediaCodec throughput
- Avoid GPU sysfs writes unless proven safe on multiple devices
- Prefer application-level hardware encode before GPU tuning

---

## 10. Thermal Behavior

**Mandatory constraints:**

- Read thermal zones before, during, after encode
- Detect throttling via cooling device state and frequency drops
- **Abort or back off** root optimizations if skin/CPU temp exceeds user-configured threshold
- **Never disable** thermal cooling devices or trip points

Reference observation (garnet, one session): thermal status 0, ~39°C skin — not a universal baseline.

---

## 11. Sustained-Load Testing

Future benchmarks should run:

- ≥10 minute encode at fixed resolution
- Log frequency, temperature, and realtime multiplier every 30s
- Compare application-only vs root-assisted runs on same local fixture

---

## 12. Battery / Power Implications

Document tradeoffs in UI:

- Faster encode may significantly increase power draw
- Behavior on battery vs AC
- Optional: disable root optimizations on battery unless charging

---

## 13. Wakelocks

**Application-level (safe, current scope):**

- Keep screen/CPU awake during active download via existing process activity

**Future root scope:**

- Partial wakelocks only if required for long background encodes
- Always release on completion

---

## 14. Charging / Power Source Behavior

Future logic may enable aggressive tuning only when:

- `BatteryManager` reports charging or full
- User explicitly allows on-battery tuning

---

## 15. KernelSU Integration Possibilities

User environment: **KernelSU Next** with root.

**Future architecture:**

- Separate optional module or helper script invoked by app
- Principle of least privilege — only required sysfs writes
- No bundled kernel modules in main app repo
- Version gate KernelSU APIs

---

## 16. Safe Rollback Procedures

Every root optimization session must:

1. Snapshot relevant sysfs values to a session file
2. Register `atexit` / signal handler to restore
3. On unclean termination, restore on next app launch if session file exists
4. Log “rollback completed” or “rollback failed (manual intervention)” 

---

## 17. Detecting Unsupported Kernel / Sysfs Nodes

Use existence checks before read/write:

```python
def sysfs_readable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.R_OK)
```

Never assume paths from one kernel version exist on another.

---

## 18. Avoiding Device-Specific Assumptions

**Forbidden:**

```python
if device_model == "Redmi Note 13 Pro 5G":
    ...
```

**Required:** Feature detection, capability caches, per-session probes.

---

## 19. Benchmark Methodology

Align with `docs/encoding-benchmarks.md` (application-level):

1. Same local fixture file
2. Same target resolution and duration window
3. Measure wall time, output size, avg bitrate, peak temp
4. Record whether thermal throttling occurred
5. Multiple runs; report median

Root benchmarks add a column: `root_profile=none|cpu_perf|affinity|...`

---

## 20. Temperature Monitoring

**Future implementation sketch:**

- Poll thermal zones on interval during encode
- Expose in job log: `thermal max=XX°C zone=skin`
- Stop root tweaks if threshold exceeded

---

## 21. Thermal Throttling Detection

Indicators:

- `scaling_cur_freq` drops below expected under load
- Cooling device state active in `/sys/class/thermal/cooling_device*`
- Encode realtime multiplier degrades over time

Future system should **reduce** optimization level when throttling detected.

---

## 22. Before / After Measurements

Store JSON benchmark records:

```json
{
  "fixture": "local/sample_480p.mp4",
  "mode": "h264_mediacodec",
  "root_profile": "none",
  "wall_sec": 42.1,
  "realtime_x": 5.8,
  "output_bytes": 1048576,
  "peak_temp_c": 41.2
}
```

---

## 23. Risks and Failure Modes

| Risk | Mitigation |
|------|------------|
| Device overheating | Thermal caps; never disable protection |
| Kernel panic / instability | Reversible changes only; no permanent sysfs |
| Battery damage perception | Clear UI warnings |
| ROM-specific SELinux denials | Catch EPERM; fall back silently |
| Stuck performance mode after crash | Session rollback file |
| Worse performance | Auto-disable profile if benchmark regresses |

---

## Implementation Order (Future)

1. Read-only telemetry (freq, temp, governor) — no writes
2. Opt-in fixed-performance mode with restore
3. Opt-in governor switch with restore
4. Affinity / nice (if measurable benefit)
5. Advanced cgroup/cpuset (highest risk, last)

Each step requires incremental benchmark proof on **multiple** devices before default-on behavior.

---

## Related Documentation

- [encoding-architecture.md](./encoding-architecture.md) — current pipeline
- [encoding-benchmarks.md](./encoding-benchmarks.md) — reproducible app-level benchmarks
