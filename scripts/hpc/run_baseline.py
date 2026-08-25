# -----------------------------------------------------------------------------
# CPU Baseline Runs of the zreion (ksz_2lpt) Simulation
# Robert Pearce
# -----------------------------------------------------------------------------

import hashlib
import json
import os
import platform
import subprocess as sp
import sys
import time
from pathlib import Path

# Path to simulation executable and output directory
EXEC = Path("/jet/home/rpearce/software/ksz_2lpt/ksz_2lpt.x")
OUT = Path("~/ocean/baseline/zreion_cpu_baseline").expanduser()

# Parameters: zmean, alpha, kb, b0 (centroid of the LHS sampling bounds)
PARAMS = (8.0, 0.5, 1.05, 0.45)

# Identical runs, for reproducibility and run to run timing spread.
REPEATS = 10


def sh(cmd):
    """
    Run a shell command and return its combined stdout and stderr
    cmd: Command string to run
    """
    try:
        p = sp.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return p.stdout + p.stderr
    except Exception as exc:
        return f"<failed: {exc}>\n"


def gnu_time():
    """Return the time -v prefix if GNU time is present, else an empty string"""
    if "Maximum resident set size" in sh("/usr/bin/time -v true"):
        return "/usr/bin/time -v "
    print("warning: GNU time -v unavailable, peak memory will not be recorded")
    return ""


def sha256(path):
    """
    Return the SHA-256 of a file, read in 1 MB chunks
    path: Path to the file to hash
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def capture_provenance(dest):
    """
    Write machine, module, and compiler details to a file
    dest: Path of the file to write
    """
    cmds = {
        "lscpu": "lscpu",
        "memory": "head -5 /proc/meminfo",
        "os": "uname -a; cat /etc/os-release",
        "modules": "module list 2>&1",
        "ifort": "which ifort && ifort --version",
        "linked_libs": f"ldd {EXEC}",
        "quota": "my_quotas 2>&1 || projects 2>&1",
    }
    with dest.open("w") as fh:
        for name, cmd in cmds.items():
            fh.write(f"### {name}\n{sh(cmd)}\n")


def run_case(tag, root):
    """
    Run the simulation once and record timing, memory, and output checksums
    tag: Name of this run; results are written to root/tag
    root: Path to the base output directory
    """
    # Make a new folder for this run
    case = root / tag
    outdir = case / "out"
    outdir.mkdir(parents=True, exist_ok=True)

    # ksz_2lpt expects: dir_out zmean_zre alpha_zre kb_zre b0_zre
    args = " ".join(str(v) for v in PARAMS)
    cmd = f"{gnu_time()}{EXEC} {outdir}/ {args}"

    # Run the executable, keeping stdout and the time -v report separate
    print(f"\n=== {tag}")
    t0 = time.perf_counter()
    with (case / "run.log").open("w") as out, (case / "time.txt").open("w") as err:
        rc = sp.run(cmd, shell=True, stdout=out, stderr=err).returncode
    wall = round(time.perf_counter() - t0, 2)

    # Pull peak memory out of the time -v report
    rss = None
    for line in (case / "time.txt").read_text(errors="replace").splitlines():
        if "Maximum resident set size" in line:
            rss = round(int(line.split(":")[1]) / 1024**2, 2)

    # Hash the outputs so a GPU run can be compared against them later
    products = {p.name: sha256(p) for p in sorted(outdir.glob("*.hdf5"))}
    print(f"  rc={rc} wall={wall}s peak_rss={rss}GB outputs={len(products)}")

    return {
        "tag": tag,
        "omp_threads_env": os.environ.get("OMP_NUM_THREADS", "unset"),
        "returncode": rc,
        "wall_seconds": wall,
        "peak_rss_gb": rss,
        "products": products,
    }


def write_results(root, results):
    """
    Write the run records to JSON and a summary table
    root: Path to the base output directory
    results: List of run record dicts
    """
    (root / "results.json").write_text(
        json.dumps(
            {
                "host": platform.node(),
                "binary": str(EXEC),
                "binary_sha256": sha256(EXEC),
                "params": PARAMS,
                "cases": results,
            },
            indent=2,
        )
    )
    with (root / "summary.csv").open("w") as fh:
        fh.write("tag,omp_threads_env,rc,wall_seconds,peak_rss_gb\n")
        for r in results:
            fh.write(
                f"{r['tag']},{r['omp_threads_env']},{r['returncode']},"
                f"{r['wall_seconds']},{r['peak_rss_gb']}\n"
            )


def main() -> int:
    # Check the executable exists
    if not EXEC.is_file():
        print(f"error: {EXEC} not found")
        return 2

    # Check output root exists / create it
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"baseline: {OUT}")
    capture_provenance(OUT / "provenance.txt")

    # Run the simulation, writing results after each one
    results = []
    for i in range(REPEATS):
        results.append(run_case(f"run_{i + 1}", OUT))
        write_results(OUT, results)

    ok = [r for r in results if r["returncode"] == 0]

    # Do identical runs give identical output
    sigs = [r["products"] for r in ok if r["products"]]
    if len(sigs) >= 2:
        print(f"\nreproducible: {all(s == sigs[0] for s in sigs)}")

    # Spread in wall time, to judge a future GPU speedup against
    walls = [r["wall_seconds"] for r in ok]
    if len(walls) >= 2:
        lo, hi = min(walls), max(walls)
        spread = (hi - lo) / hi if hi else 0.0
        print(f"wall time: {lo}-{hi}s, spread {spread:.1%} over {len(walls)} runs")

    print(f"\nwrote {OUT}/results.json, summary.csv, provenance.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
