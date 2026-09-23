# Results

Metadata from the CPU reference campaigns on Bridges-2: logs, timings, provenance, and per-run records. HDF5 products and binaries are not in Git; they are kept on Ocean and on an offline copy, in the same layout as here.

```text
results/
  cpu-baseline-v1/
    cpu-1024-baseline-v1/
  cpu-baseline-v2/
    ensemble/    cpu-{128,256,512,1024}-baseline-v2/
    scaling/     cpu-512-scaling-{128,064,032,016,008,004,001}t-v2/
    smoke/       a.log, b.log, c.log
```

Case directories are named `<device>-<N>-<kind>-<version>`, e.g. `cpu-1024-baseline-v1`; scaling cases add the thread count, e.g. `cpu-512-scaling-064t-v2`. 

| Version | Contents |
|---|---|
| [v1](#v1) | N=1024, 10 unseeded runs, timing and memory only |
| [v2](#v2) | Ensembles at N=128–1024 with saved initial fields and checkpoints, an N=512 thread-scaling sweep, and a reproducibility smoke test |

## v1

`cpu-1024-baseline-v1` — the first baseline: the reference code essentially as received, run ten times at N=1024 on 128 threads. Kept as the only record of the code before the fixes that went into v2.


**Limitations:** Runs were unseeded and no seed was recorded, so no realization can be regenerated and comparisons with v1 are statistical only.

```text
cpu-1024-baseline-v1/
  results.json     binary + sha256, parameters, and per run: return code,
                   wall time, peak RSS, product hashes
  summary.csv      one row per run
  provenance.txt   CPU, memory, OS, modules, compiler, linked libraries
  run_{1..10}/
    run.log        stdout, including per-routine timings
    time.txt       /usr/bin/time -v
```

## v2

The definitive CPU reference, built from fork `b8126cf`: seeded runs, saved initial fields and routine-boundary checkpoints for validating the GPU port, and a thread-scaling curve.

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

N=512 at 128, 64, 32, 16, 8, 4 and 1 threads, two runs per point, one fixed
seed (`20250915`) throughout, no GRF or checkpoints. Threads are pinned one per
core, packed, so 64 threads fill one socket.

```text
scaling/
  cpu-512-scaling-128t-v2/
    results.json, summary.csv, provenance.txt, sacct.txt, src.tar.gz
    run_001/   run.log, time.txt
    run_002/   run.log, time.txt
  cpu-512-scaling-064t-v2/
  cpu-512-scaling-032t-v2/
  cpu-512-scaling-016t-v2/
  cpu-512-scaling-008t-v2/
  cpu-512-scaling-004t-v2/
  cpu-512-scaling-001t-v2/     (each laid out as 128t)
```

### Smoke test

Three N=128 runs made before the campaign to check reproducibility: `a`
generates a field from seed `12345`, `b` repeats that seed, and `c` replays
`a`'s saved field. Only the run logs are in Git.

### Outside Git

Each run's `out/obs_grids.hdf5` and `pk_arrays.hdf5`, plus `grf.hdf5` and
`checkpoints.hdf5` where listed above; each case's `ksz_2lpt.x`; the smoke
test's HDF5 files; and one metadata bundle per job, whose contents are
unpacked here.
