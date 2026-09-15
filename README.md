# zreion: GPU Port

CUDA/GPU port of the kSZ 2LPT reionization simulation code, `zreion`, for accelerating reionization research. The original `zreion` (`ksz_2lpt`) was developed by [Dr. Paul La Plante](https://plaplant.github.io/), computes a redshift-of-reionization field using the semi-numeric method introduced in [Battaglia et al. (2013)](https://ui.adsabs.harvard.edu/abs/2013ApJ...776...81B/abstract). Originally built for CPU-based execution on the [Bridges-2](https://www.psc.edu/resources/bridges-2/) supercomputer at the Pittsburgh Supercomputing Center (PSC), this project aims to develop a GPU-compatible version to improve performance, scalability, and accessibility for larger simulation sweeps.

The CPU reference in `zreion/ksz_2lpt_cpu/src/` is a fork of the `ksz_2lpt` repository and is tracked in its own **private** repository, ignored here.
