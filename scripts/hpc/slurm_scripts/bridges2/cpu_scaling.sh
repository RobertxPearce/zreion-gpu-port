#!/bin/bash
# -----------------------------------------------------------------------------
# Thread-scaling sweep on one Bridges-2 RM node.
#
# One build per thread count at N=512, same seed at every point, timing only.
# The result is a parallel-efficiency curve for 2 x EPYC 7742 -- the honest
# denominator for a GPU speedup claim, and the one measurement in this project
# that becomes impossible the day the PSC allocation ends.
#
# The 1-thread point is most of the ~4 hour cost, and runs last. Edit SCALING
# in run_baseline.py to drop it if that is not worth the node hours.
#
# Both modes rebuild in the one CPU source tree, so this must not overlap the
# ensemble job. Submit it with --dependency=afterany on that job's ID.
# -----------------------------------------------------------------------------
#SBATCH -J zreion_scaling
#SBATCH -p RM
#SBATCH -t 08:00:00
#SBATCH -N 1
#SBATCH --ntasks-per-node 128
#SBATCH -o scaling-%j.log
#SBATCH -A ast180004p
#SBATCH --mail-type ALL
#SBATCH --mail-user robertbdpearce@gmail.com

set -euo pipefail

# Intel
module unload intel
module load intel-icc
module load intel-mkl
which ifort

export KMP_LIBRARY=turnaround
export OMP_SCHEDULE=static
export KMP_STACKSIZE=256m

# Pin one thread per core, packed. Unpinned, 64 threads may straddle both
# sockets or migrate mid-run, and the curve would measure the scheduler. Packed,
# 64 threads fill exactly one EPYC 7742, so the 64 -> 128 step isolates the
# cost of crossing the socket boundary. The ensemble stays unpinned so it
# remains comparable with cpu-1024-baseline-v1.
export OMP_PLACES=cores
export OMP_PROC_BIND=close

SIM_DIR="/jet/home/rpearce/software/zreion-gpu-port/zreion/ksz_2lpt_cpu/src"
# sbatch runs a spooled copy of this file, so BASH_SOURCE points into the slurmd
# spool directory, not the repo. Resolve from the submit directory instead, which
# means submitting from slurm_scripts/bridges2/.
SCRIPT_DIR="$(cd "${SLURM_SUBMIT_DIR:-$(dirname "${BASH_SOURCE[0]}")}/../.." && pwd)"
BASELINE_DIR="$HOME/ocean/baseline"
MAMBA="/jet/home/rpearce/miniforge3/bin/mamba"

# Must match RUN_VERSION in run_baseline.py. Scopes the globs below to this
# campaign, so older result sets on Ocean are neither overwritten nor bundled.
RUN_VERSION="v2"

if [ ! -f "$SCRIPT_DIR/run_baseline.py" ]; then
    echo "run_baseline.py not found in $SCRIPT_DIR; sbatch from slurm_scripts/bridges2/" >&2
    exit 1
fi

if [ ! -f "$SIM_DIR/planck_2018_transfer_z000.dat" ]; then
    echo "planck_2018_transfer_z000.dat not found in $SIM_DIR" >&2
    exit 1
fi

cd "$SCRIPT_DIR"
ln -sf "$SIM_DIR/planck_2018_transfer_z000.dat" "$SCRIPT_DIR/"

# See cpu_baseline.sh: -u for a live log, status kept so sacct still runs.
status=0
"$MAMBA" run -n simenv python -u "$SCRIPT_DIR/run_baseline.py" scaling || status=$?

# Partial while the job is running -- rerun after it ends, as for the ensemble.
for dir in "$BASELINE_DIR"/cpu-*-scaling-*-${RUN_VERSION}/; do
    [ -d "$dir" ] || continue
    sacct -j "${SLURM_JOB_ID:-0}" --units=G \
        --format=JobID,JobName,Partition,NodeList,Elapsed,TotalCPU,CPUTime,MaxRSS,AllocCPUS,ConsumedEnergy,State,ExitCode \
        > "$dir/sacct.txt" 2>&1 || true
done

# No GRF or checkpoints, only the small science products, so the whole sweep is
# small; the HDF5 is still left on Ocean to keep the bundle metadata-only.
BUNDLE="$BASELINE_DIR/scaling-metadata_${SLURM_JOB_ID:-local}.tar.gz"
if tar -czf "$BUNDLE" -C "$BASELINE_DIR" \
    --exclude='*.hdf5' --exclude='ksz_2lpt.x' \
    $(cd "$BASELINE_DIR" && ls -d cpu-*-scaling-*-${RUN_VERSION}/); then
    echo "Metadata bundle: $BUNDLE"
    ls -lh "$BUNDLE"
else
    echo "No metadata bundle written" >&2
fi

echo "run_baseline.py exit status: $status"
exit "$status"
