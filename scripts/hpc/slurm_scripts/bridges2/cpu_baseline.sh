#!/bin/bash
# -----------------------------------------------------------------------------
# CPU reference ensemble on one Bridges-2 RM node.
#
# Runs run_baseline.py in ensemble mode: N=128, 256, 512 and 1024, ten
# realizations each, saved initial fields and routine-boundary checkpoints
# tapering with grid size. About 2 hours and ~160 GB on Ocean, ~104 GiB of it
# the single N=1024 checkpoint file.
#
# The build is not done here any more -- grid size and thread count are
# compile-time, so the runner rebuilds per case.
# -----------------------------------------------------------------------------
#SBATCH -J zreion_baseline
#SBATCH -p RM
#SBATCH -t 08:00:00
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

# Set environment variables.
# KMP_SCHEDULE is deliberately absent: the Intel runtime rejects the bare
# "static" this used to set, logs OMP: Warning #50, and falls back silently.
export KMP_LIBRARY=turnaround
export OMP_SCHEDULE=static
export KMP_STACKSIZE=256m

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

# ln -sf succeeds on a missing target and leaves a dangling link, so every run
# would fail at startup instead. Check the file itself.
if [ ! -f "$SIM_DIR/planck_2018_transfer_z000.dat" ]; then
    echo "planck_2018_transfer_z000.dat not found in $SIM_DIR" >&2
    exit 1
fi

cd "$SCRIPT_DIR"

# ksz_2lpt.x opens planck_2018_transfer_z000.dat by relative path, so it has to
# run from a directory holding it or a link to it.
ln -sf "$SIM_DIR/planck_2018_transfer_z000.dat" "$SCRIPT_DIR/"

# -u so progress reaches this log as it happens rather than at exit. The status
# is kept rather than tripping set -e, so a failed case still gets its sacct
# and bundle below; the job exits with it at the end.
status=0
"$MAMBA" run -n simenv python -u "$SCRIPT_DIR/run_baseline.py" ensemble || status=$?

# Accounting. Node-hours and energy exist only in the SLURM database, and that
# goes away with the allocation. Written per case so each result set carries it.
#
# This runs inside the job, so the batch step is still RUNNING and TotalCPU,
# MaxRSS and ConsumedEnergy are partial. Rerun the same sacct once the job has
# ended and overwrite these files with the final numbers.
for dir in "$BASELINE_DIR"/cpu-*-baseline-${RUN_VERSION}/; do
    [ -d "$dir" ] || continue
    sacct -j "${SLURM_JOB_ID:-0}" --units=G \
        --format=JobID,JobName,Partition,NodeList,Elapsed,TotalCPU,CPUTime,MaxRSS,AllocCPUS,ConsumedEnergy,State,ExitCode \
        > "$dir/sacct.txt" 2>&1 || true
done

du -sh "$BASELINE_DIR"/cpu-*-baseline-${RUN_VERSION}/ || true
df -h "$BASELINE_DIR" | tail -1

# Bundle only the lightweight metadata for pulling back into the Git repo. The
# HDF5 stays on Ocean; tarring 160 GB that is already on Ocean just doubles it.
BUNDLE="$BASELINE_DIR/baseline-metadata_${SLURM_JOB_ID:-local}.tar.gz"
if tar -czf "$BUNDLE" -C "$BASELINE_DIR" \
    --exclude='*.hdf5' --exclude='ksz_2lpt.x' \
    $(cd "$BASELINE_DIR" && ls -d cpu-*-baseline-${RUN_VERSION}/); then
    echo "Metadata bundle: $BUNDLE"
    ls -lh "$BUNDLE"
else
    echo "No metadata bundle written" >&2
fi

echo "run_baseline.py exit status: $status"
exit "$status"
