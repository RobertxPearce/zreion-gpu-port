# kSZ 2LPT GPU Port

CUDA/GPU port of the kSZ 2LPT reionization simulation code for accelerating reionization research. The original kSZ 2LPT simulation code, developed by [Dr. Paul La Plante](https://plaplant.github.io/), computes a redshift-of-reionization field using the semi-numeric method introduced in [Battaglia et al. (2013)](https://ui.adsabs.harvard.edu/abs/2013ApJ...776...81B/abstract). Originally built for CPU-based execution on the Bridges-2 supercomputer at the Pittsburgh Supercomputing Center (PSC), this project aims to develop a GPU-compatible version to improve performance, scalability, and accessibility for larger simulation sweeps.

## Target System
The GPU cluster that this port is targeting was provided by the University of Nevada, Las Vegas [Computer Science Department](https://www.unlv.edu/cs).