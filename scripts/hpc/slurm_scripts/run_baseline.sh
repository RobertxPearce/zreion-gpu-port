#!/bin/bash
#SBATCH -J zreion_baseline
#SBATCH -p RM
#SBATCH -t 04:00:00
#SBATCH -N 1
#SBATCH --ntasks-per-node 128
#SBATCH -o baseline-%j.log
#SBATCH -A ast180004p
#SBATCH --mail-type ALL
#SBATCH --mail-user robertbdpearce@gmail.com

set -euo pipefail

# Intel
module unload intel
module load intel-icc
module load intel-mkl
which ifort

# Set environment variables
export KMP_LIBRARY=turnaround
export OMP_SCHEDULE=static
export KMP_STACKSIZE=256m

# Define the simulation code directory
RUN_VERSION="v2"
RESULT_NAME="zreion_cpu_baseline_${RUN_VERSION}"
SIM_DIR="/jet/home/rpearce/software/ksz_2lpt/"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KSZ_BIN="$SIM_DIR/ksz_2lpt.x"
MAMBA="/jet/home/rpearce/miniforge3/bin/mamba"

# Go to simulation code directory
echo "Changing directory to $SIM_DIR for compilation"
cd $SIM_DIR

# Clean and compile the simulation code
make clean
make ksz_2lpt.x

# Go to script directory for execution
echo "Changing directory to $SCRIPT_DIR for execution"
cd $SCRIPT_DIR

# The simulation opens planck_2018_transfer_z000.dat by relative path
ln -sf "$SIM_DIR/planck_2018_transfer_z000.dat" "$SCRIPT_DIR/"

# Run Python inside the conda env
"$MAMBA" run -n simenv python "$SCRIPT_DIR/run_baseline.py"

# Tar the results to Ocean, since /jet/home does not have room for the HDF5
BASELINE_DIR="$HOME/ocean/baseline"
TARBALL="$BASELINE_DIR/${RESULT_NAME}_${SLURM_JOB_ID:-local}.tar.gz"

du -sh "$BASELINE_DIR/$RESULT_NAME"
df -h "$BASELINE_DIR" | tail -1

tar -czf "$TARBALL" -C "$BASELINE_DIR" "$RESULT_NAME"

echo "Bundle: $TARBALL"
ls -lh "$TARBALL"
