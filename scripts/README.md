# Scripts

## `campaign/`

* `run_baseline.py`

    Builds and runs the CPU reference (`reference/ksz_2lpt`) and records each run's seed, both commits, the source, the binary, timings and provenance. Two modes:

    ```bash
    python scripts/campaign/run_baseline.py ensemble   # validation runs at every grid size
    python scripts/campaign/run_baseline.py scaling    # thread sweep, one grid size, fixed seed
    ```

    Grid size and thread count are compile-time in the reference, so every case starts with a rebuild. Configuration (`RUN_VERSION`, `CASES`, `SCALING`) is at the top of the file. Check `my_quotas` before submitting: the HDF5 writers ignore write errors.

* `environment.yml`

    The `simenv` conda environment the SLURM scripts run the runner in.

## `slurm/`

* `bridges2/cpu_baseline.sh`, `bridges2/cpu_scaling.sh`

    RM-partition wrappers for `ensemble` and `scaling` (threads pinned for the sweep). They run the runner, capture `sacct`, and bundle the metadata for pulling back into Git; the HDF5 stays on Ocean. Submit from `scripts/slurm/bridges2/`, and never let the two run at once:

    ```bash
    cd scripts/slurm/bridges2
    jid=$(sbatch --parsable cpu_baseline.sh)
    sbatch --dependency=afterany:$jid cpu_scaling.sh
    ```

* `jhu/`

    Empty; reserved for a JHU cluster's job scripts.
