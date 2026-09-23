# Changelog: ksz_2lpt CPU reference fork

Every change made to the CPU reference in `src/` relative to Paul La Plante's upstream code, one
entry per commit, oldest first. Each entry records **what** changed, **why**, and **what it does
to the outputs**, so a result set can be traced to exactly the code that produced it.

| | |
|---|---|
| Fork | [RobertxPearce/ksz_2lpt](https://github.com/RobertxPearce/ksz_2lpt) (private) |
| Upstream | [plaplant/ksz_2lpt](https://github.com/plaplant/ksz_2lpt) (private) |
| Upstream base | `218f45e` Merge branch 'main' of github.com:plaplant/ksz_2lpt (2025-10-22) |
| Branches | `main` → `a0e5aad`; `feat/selectable-grid-size` → `fc3ed9b`; `feat/baseline-instrumentation` → `b8126cf` |

The history is linear: each branch contains the one before it.

```
218f45e  upstream
a0e5aad  Set Bridges-2 run configuration                        main
fc3ed9b  Add compile-time grid size selection …                 feat/selectable-grid-size
7a41974  Free MKL DFTI descriptors in 3D FFT routines           ┐
428f868  Make dtau private in the sightline loop                │
71448ca  Decouple domain subdivision from N_cpu                 │
282fd20  Select thread count at compile time                    │ feat/baseline-instrumentation
64e9054  Seed the GRF from the command line and record it       │
c870c02  Replace raw-binary GRF reader with HDF5 save/read      │
7433cfe  Add routine-boundary HDF5 checkpoints                  │
b8126cf  Keep the Nyquist plane in Fourier-space checkpoints    ┘
```

## At a glance

| Commit | Kind | Changes simulation results? | Upstream candidate |
|---|---|---|---|
| `a0e5aad` | configuration | **yes**: `gal_map` bias model, thread count, lightcone off | no |
| `fc3ed9b` | feature + guard | no, at the default N=1024 | maybe |
| `7a41974` | bug fix (memory leak) | no | **yes** |
| `428f868` | bug fix (data race) | no, at `-O3` | **yes** |
| `71448ca` | behaviour change | no, at 128 threads | suggest, not a pure fix |
| `282fd20` | feature | no, at the default `NCPU=128` | maybe |
| `64e9054` | feature | no; adds `iseed` to every HDF5 header | no |
| `c870c02` | feature, replaces old reader | no, with flags off | no |
| `7433cfe` | feature | no, with `ckpt_level=0` | no |
| `b8126cf` | bug fix (checkpoint content) | no; checkpoint files only | no |

With every new command-line flag at its default, a build of `b8126cf` computes the same thing as
`fc3ed9b`. The differences are the `iseed` header dataset, a defined (rather than accidental)
`dtau`, and no FFT descriptor leak.

---

## `a0e5aad`: Set Bridges-2 run configuration

2026-08-25 · `Makefile`, `global.f90`, `job.sh` · 8 insertions, 6 deletions

Configuration for running on one Bridges-2 RM node under this account.

| File | Change | Why |
|---|---|---|
| `Makefile` | `H5HOME` from `/jet/home/plaplant/local/hdf5-1.12.0` to `/jet/home/rpearce/local/hdf5-1.14.6` | HDF5 is a local build under this account, reached through its `h5fc` wrapper, not a system module |
| `global.f90` | `N_cpu` 8 → 128 | One full RM node: 2 × AMD EPYC 7742, 128 cores |
| `global.f90` | `N_sims` 30 → 1 | One realization per invocation. `run_baseline.py` handles repeats, and each repeat needs its own output directory, because output filenames are fixed and a later iteration would overwrite an earlier one |
| `global.f90` | `use_bt` `.true.` → `.false.` | `use_bt` reads a redshift-dependent galaxy bias from `data/bt_bias.txt`. That file is not in the repository: the fork's `.gitignore` excludes `*.txt`, and there is no `data/` directory. Setting it `.false.` falls back to the constant `b_gal = 10` |
| `global.f90` | `save_t21_lightcone` `.true.` → `.false.` | The full 21 cm lightcone (`t21_box`, `N_grid² × Nsightpix` reals, about 5.5 GiB at N=1024) is not needed for the port. Skipping it saves memory and I/O. `t21_map` is still computed |
| `job.sh` | notification address; comment before the run line | Personal |

**Effect on results.** This is the one commit that changes physics.
- `use_bt = .false.` changes the galaxy bias model, so **`gal_map` differs** from upstream's default. `ksz_map`, `tau_map` and `t21_map` do not depend on it.
- The thread count changes the domain decomposition and the order of floating-point sums. Results differ at round-off, not in substance.
- The v1 baseline (`results/cpu-1024-baseline-v1/`) was run at this configuration.

---

## `fc3ed9b`: Add compile-time grid size selection and guard domain subdivision

2026-09-03 · `Makefile`, `global.f90`, `domain_tools.f90` · 30 insertions, 2 deletions

**What changed**
- `global.f90`: `Ndm` and `N_grid` are set from the preprocessor macros `NDM_VALUE` and `NGRID_VALUE`, both defaulting to 1024.
- `Makefile`: `NGRID ?= 1024` and `NDM ?= $(NGRID)`, passed to the compiler as `-DNGRID_VALUE` and `-DNDM_VALUE`. This relies on the `-fpp` flag already in `FFLAGS`.
- `domain_tools.f90`: `init_domain` sets `Ndomain = 0` before its subdivision search, and stops with an error message if the search finds nothing.

**Why**
- The validation plan needs the same code at N = 128, 256, 512 and 1024. N=128 is small enough to test routines one at a time on a single GPU; N=512 is the realistic single-GPU production target. Grid size was a hard-coded `parameter`, and it sizes static arrays, so it has to be fixed at build time. A build flag avoids editing source per size and a larger refactor to run-time allocation.
- The guard: `init_domain` searches for the smallest `i ≥ nint(N_cpu^(1/3))` with `mod(N_grid, 2i) == 0`. If none exists (an odd `N_grid`, or a grid too small for the starting `i`), the loop used to fall through and leave `n1`, `nx` and `Ndomain` undefined. The code then allocated arrays from those undefined values. With selectable grid sizes this became reachable, so it now fails with a clear message.

**Effect on results:** none at the default N=1024. Changing grid size requires `make clean`, because the `.mod` files carry the old values.

**Usage**
```bash
make clean && make NGRID=512 NDM=512 ksz_2lpt.x
```

---

## `7a41974`: Free MKL DFTI descriptors in 3D FFT routines

2026-09-22 · `fft_tools.f90` · 4 insertions, 4 deletions

**What changed:** `status = DftiFreeDescriptor(desc)` is uncommented in four places, the forward (`'f'`) and backward (`'b'`) branches of both `fft_3d_s` and `fft_3d_d`.

**Why**
- Every call to either 3D FFT routine creates and commits a new MKL descriptor, runs one transform, and returns. The release call was commented out, and `desc` is a local pointer. The only reference to the descriptor was lost on return, so every call leaked one committed descriptor for the rest of the run.
- The line has been commented out since upstream's initial commit (`db26466`, 2021-04-27). It was copied into both precision variants when `fft_3d` was split (`91f3fde`). The 2D routines, added later, free correctly. It looks like a debugging leftover.

**Scale.** About 352 descriptors per N=1024 run with `calc_pk = .true.`:

| Source | 3D FFTs per call | Calls | Total |
|---|---:|---:|---:|
| `calc_delta_field` | 1 | 1 | 1 |
| `calc_gradphi_1` | 3 | 22 | 66 |
| `calc_gradphi_2` | 10 | 22 | 220 |
| `calc_zreion` smoothing | 2 | 1 | 2 |
| power spectra of `rho`, `ion`, `tbg` | 3 | 21 | 63 |

The leak scales linearly with `N_sims`. Upstream's default of 30 would leak about 10,000 descriptors per invocation.

**Effect on results:** none. The free runs after the transform finishes, and nothing reads the descriptor again.

**Effect on memory and timing:** small.
- The large arrays at N=1024 total 188.08 GiB. The measured v1 peak RSS is at most 188.48 GiB. That leaves about 400 MiB for everything else, leaked descriptors included, so the leak is at most about 0.2% of peak memory.
- Each call still creates and commits (re-plans) a descriptor, before and after this fix. So the fix should not measurably change run time.
- Re-planning on every call is a separate, unmeasured inefficiency. Caching descriptors would be an optimization, not a bug fix.

**Upstream:** a clean, single-purpose candidate.

---

## `428f868`: Make dtau private in the sightline loop

2026-09-22 · `field_tools.f90` · 1 insertion

**What changed:** `!$omp private(dtau)` is added to the parallel loop over sightlines in `calc_ksz_t21_fields`.

**Why**
- The loop is `!$omp parallel do default(shared)`, so any variable not listed as private is one memory location shared by every thread.
- `dtau` is a per-sightline optical-depth total. It is reset (`dtau = 0`), accumulated along the line of sight (`dtau = dtau + sT_cgs*ne*dl`), and stored (`tau_map(j,k) = dtau + tau_lowz`), all inside the loop, and used nowhere else.
- `dtau` was introduced upstream in `a01b124` (2025-03-20) without being added to the `private` list. Its siblings `deltat`, `t21` and `gal` follow the same pattern and were already private.
- As written, all 128 threads reset and add to the same variable. That is a data race and undefined behaviour under OpenMP.
- `private` (not `reduction`, `firstprivate` or `lastprivate`) is the right clause. There is no total across sightlines, no value carried in from before the loop, and no use after it. Each thread writes its own `tau_map(j,k)` pixels, so the stores do not conflict.

**Why the output looked correct anyway.** At `-O3` the compiler keeps `dtau` in a register for each thread, which happens to give every thread its own copy. The v1 run 1 output agrees: the `tau_map` mean is 0.05977, against a header `tau` of 0.05993 that is computed independently. The race would appear at `-O0`, in a debug build, with another compiler, after an unrelated code change, or in a literal GPU translation.

**Effect on results:** none at `-O3`; the behaviour is now defined by the language rather than by the optimizer.

**Upstream:** a clean, single-purpose candidate.

---

## `71448ca`: Decouple domain subdivision from N_cpu

2026-09-22 · `global.f90`, `domain_tools.f90` · 14 insertions, 4 deletions

**What changed**
- `global.f90`: new `integer(4), parameter :: N_dom_seed = 128`.
- `domain_tools.f90`: `init_domain` starts its search from `nint(N_dom_seed**(1./3))` instead of `nint(N_cpu**(1./3))`. The failure message now names `N_dom_seed`.

**Background.** Particle deposition (TSC) adds to a particle's cell and its neighbours, so parallel threads could write the same cell. The code avoids that with domains:
- `init_domain` cuts the grid into `n1³` cubes and records each cube's 26 periodic neighbours.
- `set_domain` hands a thread a cube with no neighbour currently in progress.
- `end_domain` marks the cube done.

`set_domain` runs inside an `!$omp critical` and spins there until a cube is eligible, which blocks every other thread asking for one.

**Why.** The number of cubes came from `N_cpu`, so changing the thread count changed the decomposition. For the planned thread sweep at N=512 the old code gives:

| Threads | `n1` | Domains | Most running at once, `(n1/2)³` |
|---:|---:|---:|---:|
| 1 | 2 | 8 | 1 |
| 4 | 4 | 64 | 8 |
| 16 | 8 | 512 | 64 |
| 64 | 8 | 512 | 64, fully saturated |
| 128 | 16 | 4096 | 512 |

Each point would then measure a different decomposition, a different level of contention and a different summation order, not just a different thread count. Fixing the decomposition at the production setting makes the sweep measure how that configuration scales.

(At `N_cpu = 2` the old code gives 2×2×2 domains, each bordering all the others, so deposition would run one domain at a time. The comment in `global.f90` cites that case, but the planned sweep does not include 2 threads. The stronger reason is keeping the decomposition constant.)

**Effect on results:** none at `N_cpu = 128`. `nint(128^(1/3)) = 5` either way, giving `n1 = 16` (4096 domains) at every grid size from 128 to 1024. Domains are 8, 16, 32 and 64 cells wide at N = 128, 256, 512 and 1024, all above the 2-cell minimum TSC needs.

**Caveats**
- Not measured. The effect on deposition time is argued, not observed. Timing 64 threads with and without this commit would confirm it.
- For upstream this is a behaviour change, not a fix. At its default `N_cpu = 8` and N=1024, upstream uses 64 domains, of which only 8 can run at once. This commit would give it 4096. That likely helps, but it changes results at round-off.

---

## `282fd20`: Select thread count at compile time

2026-09-22 · `Makefile`, `global.f90` · 15 insertions, 4 deletions

**What changed**
- `global.f90`: a new `NCPU_VALUE` macro (default 128), and `N_cpu = NCPU_VALUE`.
- `Makefile`: `NCPU ?= 128`, passed as `-DNCPU_VALUE=$(NCPU)`, with a comment explaining why.

**Why.** The thread sweep needs different thread counts, and `OMP_NUM_THREADS` cannot provide them:
- `N_cpu` sizes the arrays `dm_cpu`, `hoc_cpu` and `sight_cpu`, and sets the range of the `icpu` loops in `field_tools.f90`.
- Every program calls `OMP_SET_NUM_THREADS(N_cpu)` at startup, which overrides the environment. That covers `ksz_2lpt`, `compute_cl`, `cmb_square`, `search_windows` and `coeval_boxes`.

So a sweep needs one build per thread count. The `omp_threads_env` column in the v1 `summary.csv` never had any effect.

**Effect on results:** none at the default of 128.

**Usage**
```bash
make clean && make NGRID=512 NDM=512 NCPU=16 ksz_2lpt.x
```

---

## `64e9054`: Seed the GRF from the command line and record it

2026-09-22 · `rng_tools.f90`, `global.f90`, `ksz_2lpt.f90`, `io_tools.f90` · 37 insertions, 6 deletions

**What changed**
- `global.f90`: new run-time variable `iseed_run = 0`.
- `ksz_2lpt.f90`: positional argument 6 sets `iseed_run`, and its value is printed with the other parameters.
- `rng_tools.f90`, in `make_gaussian_random_field`:
  - If `iseed_run == 0`, it draws a seed from system entropy as before (`random_seed()` → `random_number`). A drawn value of 0 becomes 1, because 0 means "draw one". The result is stored in `iseed_run`.
  - `iseed(1) = iseed_run`. One MT19937 stream then generates the `Ndm` per-slab seeds, and each k-slab draws from its own stream, as before.
  - Prints `GRF seed: <n>`.
- `io_tools.f90`: `write_hdf5_header` adds an integer `iseed` dataset. That routine writes the `/header` group of every HDF5 product, including `obs_grids.hdf5` and `pk_arrays.hdf5`.

**Why**
- Upstream drew the seed from entropy and discarded it, so no run could be repeated. The v1 baseline shows the consequence: ten runs, ten different universes, and a `ksz_map` relative L2 difference of about 1.5 between any two.
- Validating the GPU port routine by routine needs repeatable initial conditions. The random field depends only on `iseed(1)`: each k-slab has its own stream, so thread count and scheduling do not matter. One 32-bit integer therefore regenerates the field bit for bit.
- Recording the seed is the essential part. Every run, including unseeded ones, now logs and stores the one number that regenerates it. `run_baseline.py` reads the `GRF seed:` line into `results.json`.

**Effect on results:** with seed 0, the same statistics as before; each run is still a fresh realization. Every HDF5 product gains `/header/iseed`.

**Usage:** `./ksz_2lpt.x <dir_out>/ <zmean> <alpha> <kb> <b0> <iseed>`

---

## `c870c02`: Replace raw-binary GRF reader with HDF5 save/read

2026-09-22 · `checkpoint_tools.f90` (new), `io_tools.f90`, `field_tools.f90`, `global.f90`, `ksz_2lpt.f90`, `Makefile` · 328 insertions, 95 deletions

**What changed**
- **`checkpoint_tools.f90`, new module, first version.** It holds only the random-field routines:
  - `write_gaussian_random_field`, when `save_grf` is set, writes `<dir_out>/grf.hdf5`:
    - `/header/{Ndm, N_grid, iseed, BoxSize}`;
    - `/data/delta1`, the real-space field before any FFT, shape `(Ndm,Ndm,Ndm)`, without the FFT padding.
  - `read_gaussian_random_field` reads `<dir_out>/grf.hdf5`. It:
    - stops if the file is missing, or its `Ndm` does not match the build;
    - adopts the file's `iseed` into `iseed_run`, so a replay's outputs name their realization;
    - zeroes all of `delta1`, padding included, before reading the field region;
    - prints the same `GRF:` statistics line as the generator, for side-by-side log comparison.
  - Helpers `ckpt_attr_int` and `ckpt_attr_dbl` write scalar header values. Despite the names they create scalar datasets, not HDF5 attributes.
- **`io_tools.f90`:** the old `read_gaussian_random_field` (about 90 lines) is removed. It read a raw Fortran binary, `dir_grf//'grf.<Ndm>'`, holding `delta1` after its forward FFT.
- **`field_tools.f90`:** in `calc_delta_field`, the `if (.not. read_grf)` guard around the forward FFT is removed, so the FFT always runs.
- **`global.f90`:**
  - `read_grf` changes from a `parameter` fixed at `.false.` to a run-time variable.
  - New variable `save_grf`.
  - New constant `fn_grf = 'grf.hdf5'`.
- **`ksz_2lpt.f90`:**
  - Argument 7 sets `save_grf`, argument 8 sets `read_grf`; both are printed.
  - The program stops if both are set, because reading `grf.hdf5` and then saving would overwrite the file just read.
  - It calls `write_gaussian_random_field` right after the field is generated or read, before any FFT.
- **`Makefile`:** `checkpoint_tools.o` is added to `OBJ2`.

**Why**
- The saved random field is the GPU port's anchor for reproducibility. Reproducing MKL's MT19937 streams with cuRAND is impractical, so the GPU port loads the CPU's exact initial field instead.
- The seed from `64e9054` can regenerate the field, but only on a machine with a compatible MKL. The file needs no Intel toolchain, so the two are redundant on purpose.
- The old reader was unusable here:
  - raw Fortran binary is compiler-specific and hard to read from Python;
  - it stored the transformed field, which forced the conditional FFT;
  - there was no matching writer;
  - `read_grf` was a compile-time `.false.`, so the path was dead code.

  The new format stores the field before the FFT, so write and read mirror each other and the FFT runs unconditionally.
- The new routines went into a new module, not `io_tools`, because `checkpoint_tools` depends only on `global`, and `7433cfe` adds the checkpoint writers to it.

**Effect on results:** none with arguments 7 and 8 at 0. `read_grf` looks only in the run's own `dir_out`, so a replay needs `grf.hdf5` copied into the new output directory.

**Leftover:** `dir_grf` in `global.f90` is now unused.

---

## `7433cfe`: Add routine-boundary HDF5 checkpoints

2026-09-22 · `checkpoint_tools.f90`, `field_tools.f90`, `zreion_tools.f90`, `ksz_2lpt.f90`, `global.f90` · 405 insertions, 4 deletions

**What changed**
- **`checkpoint_tools.f90`:**
  - Module state: `ckpt_file_id`, where −1 means "not open", and the first-call counter `ckpt_ndvf`.
  - `ckpt_on` is true when `checkpoint_level ≥ 1` and the file is open.
  - `ckpt_open` truncates or creates `<dir_out>/checkpoints.hdf5` and resets `ckpt_ndvf`.
  - `ckpt_close` writes `/header` and closes the file. The header holds `Ndm`, `N_grid`, `N_cpu`, `Ndomain`, `checkpoint_level`, `iseed`, `BoxSize` and the four zreion parameters. It is written last because `iseed` is not known until the field has been drawn or read.
  - Writers for each array layout:

    | Routine | Layout |
    |---|---|
    | `ckpt_scalar` | padded real-space field `a(nv+2,n2,n3)`; writes `1:nv` |
    | `ckpt_comp_last` | one component of `gradphi(Ndm+2,Ndm,Ndm,3)` |
    | `ckpt_comp_first` | one component of `velocity(3,N,N,N)` |
    | `ckpt_map` | 2D map |

  - `ckpt_group` opens or creates an HDF5 group.
  - The module comment changes from describing the random field to describing checkpoints.
- **`global.f90`:** new constant `fn_ckpt = 'checkpoints.hdf5'` and variable `checkpoint_level = 0`.
- **`ksz_2lpt.f90`:**
  - Argument 9 sets `checkpoint_level`, and it is printed.
  - `ckpt_open` and `ckpt_close` are called around each simulation.
  - Saves `delta1_k` after `calc_delta_field`, and the four output maps after `calc_ksz_t21_fields`.
  - A comment explains why the random field is not duplicated in the checkpoint file.
- **`field_tools.f90`:** `calc_density_velocity_fields` increments `ckpt_ndvf` first. On the first call only, it saves `gradphi` after `calc_gradphi_1`, and `delta2` plus `gradphi` after `calc_gradphi_2`.
- **`zreion_tools.f90`:** saves `density` and `velocity` after the `z = zmean_zre` call, and `zreion` at the end of `calc_zreion`.

**Resulting file:** 13 full 3D arrays plus the 4 maps (dataset names as of `b8126cf`):
```
/header/...
/calc_delta_field/delta1_k
/calc_gradphi_1/gradphi_{x,y,z}
/calc_gradphi_2/{delta2_k,gradphi_x,gradphi_y,gradphi_z}
/calc_density_velocity_fields/{density,velocity_x,velocity_y,velocity_z}
/calc_zreion/zreion
/calc_ksz_t21_fields/{ksz_map,tau_map,t21_map,gal_map}
```

**Why**
- The port is validated one routine at a time: load a routine's input from the file, run the GPU version, and compare with the saved output. That needs the CPU's full arrays at routine boundaries, from a run whose initial field is known.
- Design choices:
  - **Raw arrays, no statistics.** min/max/mean/std/L2/NaN counts are computed only in `scripts/validation/metrics.py`, so the CPU and GPU are never compared through two definitions of "the mean".
  - **First call only.** `calc_density_velocity_fields` runs 22 times per simulation: once in `calc_zreion` at `z = zmean_zre`, then 21 more times at other redshifts. Saving only the first, scientifically central call is the difference between about 14 GB and about 300 GB per run at N=512.
  - **No `dm` particle array.** It is an array of structs, so it would need an HDF5 compound type. Its contents follow from `gradphi` and `delta2`, which are saved, and its effect shows in `density` and `velocity`, which are also saved.
  - **The random field lives only in `grf.hdf5`.** Saving it again in the checkpoint file would duplicate 8 GiB at N=1024.
  - **A single `checkpoint_level`** (0 or 1) replaces the three-level scheme in the early planning docs.

**Effect on results:** none with `ckpt_level = 0`.

**Caveats**
- **Checkpoint runs are not timing runs.** Writes inside `calc_density_velocity_fields` and `calc_zreion` add to those routines' logged times. Each writer except `ckpt_map` also logs its own `Called ckpt …` line.
- **Assumes one simulation per invocation.** `ckpt_open` truncates the file for each `isim`, so `N_sims > 1` would keep only the last. This is fine with `N_sims = 1` (from `a0e5aad`).

---

## `b8126cf`: Keep the Nyquist plane in Fourier-space checkpoints

2026-09-22 · `checkpoint_tools.f90`, `field_tools.f90`, `ksz_2lpt.f90` · 70 insertions, 9 deletions

**What changed**
- `checkpoint_tools.f90`:
  - New `ckpt_kspace`, which writes the full `(nv+2, n2, n3)` array.
  - `ckpt_scalar`'s comment now says it is for real-space fields only; it used to list `delta1` and `delta2`.
  - The module header notes that `*_k` datasets are the full-width exception.
- `ksz_2lpt.f90`: `delta1_k` is written with `ckpt_kspace`.
- `field_tools.f90`: `delta2` is written with `ckpt_kspace`, and renamed `delta2_k`.

**Why**
- The in-place real-to-complex FFT turns `Ndm` reals per row into `Ndm/2 + 1` complex values, stored as `Ndm + 2` interleaved reals. That's why the arrays are declared `(Ndm+2, Ndm, Ndm)`.
  - In real space, the last two slots are scratch.
  - In Fourier space, they hold the Nyquist plane, `kx = Ndm/2`: data, not padding.
- `ckpt_scalar` always writes `1:Ndm`. Two checkpointed arrays are in Fourier space when saved:
  - `delta1`, just after the forward FFT in `calc_delta_field`;
  - `delta2`, which `calc_gradphi_2` forward-transforms (`field_tools.f90:654`) and never transforms back.
- Both lost their Nyquist plane: about 1.6% of values at N=128 and 0.2% at N=1024. The loss breaks the checkpoints' purpose:
  - A GPU test that loads `delta1_k` as input to `calc_gradphi_1` would start without the Nyquist plane, which `calc_delta_field` does not zero. It would then mismatch the saved `gradphi` for reasons unrelated to the port. `delta2` has the same problem as input to the last step of `calc_gradphi_2`.
  - A GPU error confined to that plane would go undetected.
- The rename marks `delta2_k` as Fourier-space. Before, it sat beside real-space fields with nothing to show its interleaved layout.

**Layout.** From Python, the `_k` datasets have shape `(N, N, N+2)`, with real and imaginary parts interleaved along the last axis for `kx = 0 … N/2`:
```python
a = f["calc_delta_field/delta1_k"][...]
delta1_k = a[..., 0::2] + 1j * a[..., 1::2]   # shape (N, N, N/2+1)
```

**Effect on results:** none on the simulation. Checkpoint files grow by two columns on these two arrays.

**Timing:** this has to land before any checkpoints are generated on Bridges-2. Checkpoints written before it cannot be repaired.

---

## Command line after `b8126cf`

```
ksz_2lpt.x <dir_out>/ <zmean_zre> <alpha_zre> <kb_zre> <b0_zre> <iseed> <save_grf> <read_grf> <ckpt_level>
```

All arguments are optional and positional. `dir_out` needs its trailing slash, because output filenames are appended to it directly.

| # | Argument | Values | Added in |
|---:|---|---|---|
| 1 | `dir_out` | output directory, with trailing `/` | upstream |
| 2–5 | `zmean_zre`, `alpha_zre`, `kb_zre`, `b0_zre` | reals; defaults from `cosmo_parameters.f90` | upstream |
| 6 | `iseed` | `0` draws from entropy; any other value replays that realization | `64e9054` |
| 7 | `save_grf` | `1` writes `<dir_out>/grf.hdf5` | `c870c02` |
| 8 | `read_grf` | `1` reads `<dir_out>/grf.hdf5`; cannot be combined with 7 | `c870c02` |
| 9 | `ckpt_level` | `1` writes `<dir_out>/checkpoints.hdf5` | `7433cfe` |

Build flags: `NGRID`, `NDM` (`fc3ed9b`) and `NCPU` (`282fd20`). Any change requires `make clean`.

## Output files after `b8126cf`

| File | Written when | Contents |
|---|---|---|
| `obs_grids.hdf5` | always | maps and header, now including `iseed` |
| `pk_arrays.hdf5` | `calc_pk = .true.` | power spectra and header, now including `iseed` |
| `grf.hdf5` | `save_grf = 1` | initial real-space field and its seed |
| `checkpoints.hdf5` | `ckpt_level = 1` | 13 arrays at routine boundaries, 4 maps, header |

## Reproducibility

| What | Repeatable to |
|---|---|
| `grf.hdf5` at a fixed `iseed` | bit for bit |
| Products from a fixed `iseed` or a replayed `grf.hdf5` | round-off, relative L2 about `1e-12` |
| Products with `iseed = 0` | not at all: each run is an independent realization |

The middle row is not exact because `set_domain` assigns domains inside a critical section, so the
order in which threads add into boundary cells varies from run to run.

## Known issues not addressed by these commits

| Issue | Where | Notes |
|---|---|---|
| `fft_3d_s` builds a `DFTI_DOUBLE` descriptor for a `real(4)` array | `fft_tools.f90:96`, `:116` | Unused today; a trap if the port moves to single precision. Upstream candidate |
| `status` returned by every DFTI call is ignored | `fft_tools.f90` | A failed commit or compute would pass silently |
| `set_domain` spins while holding a critical section | `domain_tools.f90:136` | Mitigated by `71448ca`, not fixed; the GPU port drops this scheme |
| `end_domain` updates the shared status array outside the critical section | `domain_tools.f90:167` | In theory the last two finishers could miss each other's update and skip the reset before the next pass; never observed |
| FFT descriptors are rebuilt on every call | `fft_tools.f90` | Optimization opportunity; unmeasured |
| `dir_grf` is unused | `global.f90` | Left over from the removed binary reader |
| `use_bt = .false.` because `data/bt_bias.txt` is missing | `global.f90`, `a0e5aad` | Changes `gal_map`; restore the file to re-enable |

## Verification status

- **Not compiled yet.** None of `7a41974` … `b8126cf` has been built; the fork needs Intel `ifort` and MKL, which are available only on Bridges-2. Build each commit in turn with:
  ```bash
  git rebase --exec "make clean && make NGRID=128 NDM=128 ksz_2lpt.x" fc3ed9b
  ```
- **Smoke test pending.** See Phase 0 in `docs/cpu_baseline_campaign.md`. In `checkpoints.hdf5` at N=128, the `_k` datasets should be `(128, 128, 130)` and the other fields `(128, 128, 128)`.
- **Upstream candidates:** `7a41974` and `428f868`, cherry-picked onto branches based on `upstream/main`. Offer `71448ca` only as a suggestion.
