# ksz_2lpt (CPU Reference)

The original CPU implementation by [Dr. Paul La Plante](https://plaplant.github.io/), kept here as a private fork and used as the reference for the GPU port.

The fork lives in `src/` and is its own Git repository. Source changes are committed inside `src/`; notes about them are committed out here.

| |                                                                                                                                                                                                      |
|---|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Fork | [RobertxPearce/ksz_2lpt](https://github.com/RobertxPearce/ksz_2lpt) (private)                                                                                                                        |
| Upstream | [plaplant/ksz_2lpt](https://github.com/plaplant/ksz_2lpt) (private)                                                                                                                                  |                                                                                                                                 |

## Changes from the Original

Changes from the original are described in [CHANGELOG.md](CHANGELOG.md).


## Building and running

On Bridges-2, from `zreion/ksz_2lpt_cpu/src`:

```bash
module unload intel && module load intel-icc intel-mkl
make clean && make NGRID=512 NDM=512 NCPU=128 ksz_2lpt.x

./ksz_2lpt.x <dir_out>/ <zmean_zre> <alpha_zre> <kb_zre> <b0_zre> \
             <iseed> <save_grf> <read_grf> <ckpt_level>
```

| Argument | Meaning |
|---|---|
| `dir_out` | Output directory. Needs the trailing `/` |
| `zmean_zre` … `b0_zre` | zreion parameters; default to `cosmo_parameters.f90` |
| `iseed` | `0` draws a fresh realization; any other value replays that one |
| `save_grf` / `read_grf` | `1` writes / reads `<dir_out>/grf.hdf5`; not both |
| `ckpt_level` | `1` writes `<dir_out>/checkpoints.hdf5` |

All arguments are optional. Things to know:

- **Grid size and thread count are build flags** (`NGRID`, `NDM`, `NCPU`), and changing them needs `make clean`. `OMP_NUM_THREADS` has no effect.
- **`planck_2018_transfer_z000.dat` is opened by relative path**, so run the binary from `src/` or from a directory with a symlink to the file. The SLURM scripts create that link.
- **HDF5 is a local build** at `/jet/home/rpearce/local/hdf5-1.14.6`, set by `H5HOME` in the `Makefile`.
- **Do not set `KMP_SCHEDULE=static`.** The Intel runtime rejects it with `OMP: Warning #50` and ignores it.

## Configuration

Fixed in `global.f90` unless noted.

| Parameter | Value |
|---|---|
| `Ndm`, `N_grid`, `N_cpu` | 1024, 1024, 128 by default; set at build time |
| `N_dom_seed` | 128: the domain grid does not change with thread count |
| `box` | 2000 Mpc/h at every N; changing N changes resolution, not volume |
| `N_sims` | 1: one realization per run |
| `use_bt` | `.false.`: constant galaxy bias, since `data/bt_bias.txt` is missing |
| `save_t21_lightcone` | `.false.` |

## Baseline measurements

`results/cpu-1024-baseline-v1/`: ten runs at N=1024 on one Bridges-2 RM node, 128 threads.

| | |
|---|---|
| Wall time | mean 371 s, range 340–425 s |
| Peak RSS | 188 GiB |
| CPU utilisation | about 12,000%, i.e. about 120 of 128 cores busy, including threads spinning while they wait |

These runs predate the seed option, so each is an independent realization and they cannot be
compared file by file. They also predate the descriptor-leak and `dtau` fixes, which should not
change results or timing measurably. See [CHANGELOG.md](CHANGELOG.md).

## Runtime breakdown

From `run_1/run.log` (wall time 425 s).

| Routine | Total | Calls | Note |
|---|---:|---:|---|
| `calc_ksz_t21_fields` | 398 s | 1 | Includes 21 of the 22 `calc_density_velocity_fields` calls; about 81 s is its own sightline work |
| `calc_density_velocity_fields` | 307 s | 22 | The main port target |
| ├ `calc_gradphi_2` | 118 s | 22 | 10 FFTs per call |
| ├ `calc_gradphi_1` | 42 s | 22 | 3 FFTs per call |
| ├ `link_dm` | 22 s | 22 | Linked list; not needed on GPU |
| ├ `calc_dm` | 10 s | 22 | Fully parallel |
| └ deposition | 115 s | 22 | TSC scatter; hardest to port |
| `calc_rho_ion_fields` | 16 s | 21 | |
| `calc_zreion` | 14 s | 1 | |
| `calc_pspec` | 8 s | 84 | |
