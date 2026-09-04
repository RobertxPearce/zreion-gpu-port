# ksz_2lpt (CPU Reference)

The original CPU implementation by [Dr. Paul La Plante](https://plaplant.github.io/), kept here as a private fork and used as the reference for the GPU port.

The fork lives in `src/` and is its own Git repository. Source changes are committed inside `src/`; notes about them are committed out here.

| |                                                                                                                                                                                                      |
|---|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Fork | [RobertxPearce/ksz_2lpt](https://github.com/RobertxPearce/ksz_2lpt) (private)                                                                                                                        |
| Upstream | [plaplant/ksz_2lpt](https://github.com/plaplant/ksz_2lpt) (private)                                                                                                                                  |                                                                                                                                 |

## Changes from the Original

### Set Bridges-2 Run Configuration (`a0e5aad`)

Configuration only. No physics or numerics changed, so baselines from this commit are comparable to upstream at matching settings.

| File | What and Why                                                                                                                |
|---|-----------------------------------------------------------------------------------------------------------------------------|
| `Makefile` | `H5HOME` points at a local HDF5 1.14.6 build rather than plaplant's 1.12.0                                                  |
| `global.f90` | `N_cpu` 8 to 128, for one full RM node. `N_sims` 30 to 1. `save_t21_lightcone` off, to skip writing the full 21cm lightcone |
| `job.sh` | Notification address                                                                                                        |

### Add Compile-Time Grid Size Selection and Guard Domain Subdivision (`fc3ed9b`)

Grid size becomes a build flag. Defaults are unchanged, so results still match `a0e5aad`.

```bash
make clean && make NGRID=128 ksz_2lpt.x
```

| File | What and Why                                                                                                                               |
|---|--------------------------------------------------------------------------------------------------------------------------------------------|
| `global.f90` | `Ndm` and `N_grid` read the `NDM_VALUE` and `NGRID_VALUE` macros, defaulting to 1024                                                       |
| `Makefile` | `NGRID ?= 1024` and `NDM ?= $(NGRID)`, passed to the compiler as `-D` flags through the `-fpp` already in `FFLAGS`                         |
| `domain_tools.f90` | Sentinel in `init_domain`. Its subdivision search could fall through leaving `n1`, `nx` and `Ndomain` undefined, then allocate on garbage  |
