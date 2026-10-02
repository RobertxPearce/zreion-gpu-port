# Results

Metadata from the CPU reference campaigns on Bridges-2: logs, timings, provenance, and per-run records. HDF5 products and binaries are not in Git; they are kept on Ocean and on an offline copy, in the same layout as here.

```text
results/
  cpu-baseline-v2/
    ensemble/    cpu-{128,256,512,1024}-baseline-v2/
    scaling/     cpu-512-scaling-{128,064,032,016,008,004,001}t-v2/
    smoke/       a.log, b.log, c.log
  archive/
    cpu-1024-baseline-v1/
```

Case directories are named `<device>-<N>-<kind>-<version>`, e.g. `cpu-1024-baseline-v2`; scaling cases add the thread count, e.g. `cpu-512-scaling-064t-v2`.

## v2

The CPU reference, built from fork `b8126cf`: seeded runs, saved initial fields and routine-boundary checkpoints for validating the GPU port, and a thread-scaling curve.

### Ensemble

Ten independent realizations per grid size at 128 threads, each with its own seed. Initial fields (GRF) and checkpoints are saved for the leading runs, tapering with grid size.

| Case | Runs | GRF saved | Checkpoints |
|---|---:|---|---|
| `cpu-128-baseline-v2` | 10 | runs 1–10 | runs 1–10 |
| `cpu-256-baseline-v2` | 10 | runs 1–10 | runs 1–3 |
| `cpu-512-baseline-v2` | 10 | runs 1–10 | run 1 |
| `cpu-1024-baseline-v2` | 10 | runs 1–3 | run 1 |

```text
ensemble/
  cpu-128-baseline-v2/
    results.json, summary.csv, provenance.txt, sacct.txt, src.tar.gz
    run_001/   run.log, time.txt
    ...
    run_010/   run.log, time.txt
  cpu-256-baseline-v2/
  cpu-512-baseline-v2/
  cpu-1024-baseline-v2/        (each laid out as 128)
```

### Thread scaling

N=512 at 128, 64, 32, 16, 8, 4 and 1 threads, two runs per point, one fixed seed (`20250915`) throughout, no GRF or checkpoints. Threads are pinned one per core, packed, so 64 threads fill one socket.

```text
scaling/
  cpu-512-scaling-128t-v2/
    results.json, summary.csv, provenance.txt, sacct.txt, src.tar.gz
    run_001/   run.log, time.txt
    run_002/   run.log, time.txt
  cpu-512-scaling-064t-v2/
  ...
  cpu-512-scaling-001t-v2/     (each laid out as 128t)
```

### Smoke test

Three N=128 runs made before the campaign to check reproducibility: `a` generates a field from seed `12345`, `b` repeats that seed, and `c` replays `a`'s saved field. Only the run logs are in Git.

### Outside Git

Each run's `out/obs_grids.hdf5` and `pk_arrays.hdf5`, plus `grf.hdf5` and `checkpoints.hdf5` where listed above; each case's `ksz_2lpt.x`; the smoke test's HDF5 files; and one metadata bundle per job, whose contents are unpacked here.

## Archive

`cpu-1024-baseline-v1`: a first timing run of the reference essentially as received, before the fixes that went into v2. Ten unseeded, unpinned runs at N=1024 on 128 threads; no initial fields or checkpoints. Kept for history only; use v2 for comparisons.
