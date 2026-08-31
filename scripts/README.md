# Scripts

## `hpc/`

* `run_baseline.py`
    * Runs repeated CPU baseline simulations with the original Bridges-2 `ksz_2lpt.x` executable.
    * Records one entry per repeat in `results.json`, including the run number, return code, start/end timestamps, elapsed wall time, and output directory.
    * Writes `provenance.txt` with host, CPU, memory, OS, compiler, loaded module, linked-library, quota/project, SLURM, OpenMP, and MKL environment details.

* `slurm_scripts/run_baseline.sh`
    * Bridges-2 SLURM wrapper for `run_baseline.py`.
