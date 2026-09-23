# Scripts

## `hpc/`

* `run_baseline.py`

    Builds and runs the CPU reference, and records everything the GPU port will
    need once the PSC allocation ends. Two modes:

    ```bash
    python scripts/hpc/run_baseline.py ensemble   # validation runs at every grid size
    python scripts/hpc/run_baseline.py scaling    # thread sweep, one grid size, fixed seed
    ```

    Grid size **and** thread count are compile-time in the reference, so every
    case begins with `make clean` and a rebuild. `OMP_NUM_THREADS` does nothing:
    `ksz_2lpt.f90` calls `OMP_SET_NUM_THREADS(N_cpu)` with `N_cpu` baked in by
    `-DNCPU_VALUE`.

    Per case it writes `results.json`, `summary.csv`, `provenance.txt`,
    `src.tar.gz`, `src.diff`, a copy of `ksz_2lpt.x`, and `run_NNN/{run.log,
    time.txt,out/}`.

    Three things it records that nothing else does:

    * **The RNG seed.** The GRF is a deterministic function of one 32-bit
      integer, so four bytes replay any realization exactly. The runner draws a
      distinct seed per run and passes it in — left to itself, the binary seeds
      from the clock, and back-to-back N=128 runs could collide. `parse_seed`
      lifts the echoed seed out of the log as a cross-check.
    * **Both commits**, read from the Bridges-2 trees rather than a laptop
      checkout: the CPU fork's (`reference`), which this repo ignores, and this
      repo's (`runner`), each with its branch and dirty flag. Together they are
      the only thing tying a result set to the code that produced it.
    * **The source and the binary themselves.** A commit in a private repo is one
      lost laptop from making every number unattributable, and an `-ipo` build
      cannot be reproduced bit-for-bit from source in any case.

    Configuration lives at the top of the file. `CASES` sets grid sizes, repeats,
    and how many leading repeats save a GRF (`grf_runs`) or checkpoints
    (`ckpt_runs`) — one checkpointed run even at N=1024, about 104 GiB, because
    it cannot be regenerated after the allocation ends. `SCALING` sets the thread
    sweep, run in descending order so the long serial point comes last.

    `check_space` only sees the filesystem's free space, not the project quota,
    and the Fortran HDF5 writers ignore write errors. Check `my_quotas` before
    submitting; the runner prints it into the job log as well.

* `slurm_scripts/bridges2/cpu_baseline.sh`

    RM-partition wrapper for `ensemble`. Loads the Intel toolchain, links
    `planck_2018_transfer_z000.dat` next to the runner, runs it in the `simenv`
    environment, then captures `sacct` — node-hours and energy live only in the
    PSC accounting database — and bundles the lightweight metadata for pulling
    back into Git. The HDF5 stays on Ocean.

    No longer builds anything: the runner rebuilds per case. If the runner
    fails, `sacct` and the bundle still run and the job exits with its status.
    The `sacct` captured in the job is partial, because the job is still
    running; rerun it once the job has ended.

    Submit from `slurm_scripts/bridges2/`: sbatch runs a spooled copy of the
    script, so it finds the runner through `SLURM_SUBMIT_DIR`. Both modes rebuild
    in the one CPU source tree, so never let them run at once — chain them:

    ```bash
    cd scripts/hpc/slurm_scripts/bridges2
    jid=$(sbatch --parsable cpu_baseline.sh)
    sbatch --dependency=afterany:$jid cpu_scaling.sh
    ```

* `slurm_scripts/bridges2/cpu_scaling.sh`

    Same, for `scaling`, with threads pinned one per core and packed
    (`OMP_PLACES=cores`, `OMP_PROC_BIND=close`), so 64 threads fill exactly one
    socket. Budget about four node-hours; the 1-thread point is most of it.
