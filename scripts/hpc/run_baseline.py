# -----------------------------------------------------------------------------
# Build and run the CPU reference (zreion/ksz_2lpt) on Bridges-2, and record
# everything the GPU port will need.
#
# Two modes:
#
#   ensemble   For each grid size in CASES: rebuild, run REPEATS independent
#              realizations, save the initial field and routine-boundary
#              checkpoints for as many of them as the size affords.
#
#   scaling    One grid size, one fixed seed, one build per thread count. This
#              is the measurement that cannot be repeated later: it needs the
#              128-core EPYC 7742 node.
#
# Grid size AND thread count are compile-time in the reference, so every case
# starts with a rebuild. OMP_NUM_THREADS does nothing -- ksz_2lpt.f90 calls
# OMP_SET_NUM_THREADS(N_cpu) with N_cpu baked in at compile time.
#
# Writes, per case directory:
#   results.json          every field below, structured
#   summary.csv           one row per run, for the notebook
#   provenance.txt        host, CPU, memory, OS, compiler, modules, libs, quota
#   src.tar.gz            the exact source that produced the binary
#   src.diff              uncommitted changes at build time, if any
#   ksz_2lpt.x            the binary itself -- -ipo builds are not reproducible
#   run_NNN/run.log       stdout, including per-routine timings and the seed
#   run_NNN/time.txt      /usr/bin/time -v
#   run_NNN/out/          grf.hdf5, checkpoints.hdf5, obs_grids.hdf5, pk_arrays.hdf5
#
# Robert Pearce
# -----------------------------------------------------------------------------

from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import platform
import random
import re
import shutil
import subprocess as sp
import time


RUN_VERSION = "v2"

# Paths on the Bridges-2 supercomputer
SIM_SRC = Path("/jet/home/rpearce/software/zreion-gpu-port/zreion/ksz_2lpt_cpu/src")
EXEC = SIM_SRC / "ksz_2lpt.x"
RUNNER_DIR = Path(__file__).resolve().parent
BASE_OUT = Path("~/ocean/baseline").expanduser()

# zreion parameter values set at the midpoint of the bounds from reionemu
PARAMS = {
    "zmean_zre": 8.0,
    "alpha_zre": 0.5,
    "kb_zre": 1.05,
    "b0_zre": 0.45,
}

# Products ksz_2lpt.x may write into a run's out/ directory.
PRODUCTS = ["grf.hdf5", "checkpoints.hdf5", "obs_grids.hdf5", "pk_arrays.hdf5"]

# The validation ensembles.
#
# repeats    independent realizations; the run-to-run spread is the acceptance
#            envelope the GPU port has to land inside, and 10 is what the N=1024
#            baseline already used
# grf_runs   leading repeats that write grf.hdf5 -- the field the GPU loads so
#            it starts from the CPU's exact initial conditions
# ckpt_runs  leading repeats that write checkpoints.hdf5 -- full routine-boundary
#            arrays, the unit-test fixtures for porting one routine at a time
#
# grf_runs and ckpt_runs taper with grid size because the files do not: one
# 3D field is 16 MiB at N=128 and 8 GiB at N=1024. The tapering costs nothing
# scientifically -- you need many realizations for statistics and only one or
# two replayable ones for debugging.
#
# N=1024 keeps one checkpointed run despite the ~104 GiB file. It is the only
# way to localize a failure that appears at full scale and not at 512 -- e.g.
# int32 index overflow, since gradphi is ~3.2e9 elements -- and it cannot be
# regenerated once the 251 GiB nodes are gone. Run 1 also saves its GRF, so
# the GPU can start from the same field and diff every routine boundary.
CASES = [
    {"grid": 128, "repeats": 10, "grf_runs": 10, "ckpt_runs": 10},
    {"grid": 256, "repeats": 10, "grf_runs": 10, "ckpt_runs": 3},
    {"grid": 512, "repeats": 10, "grf_runs": 10, "ckpt_runs": 1},
    {"grid": 1024, "repeats": 10, "grf_runs": 3, "ckpt_runs": 1},
]

# Threads used for the ensemble. One full RM node.
ENSEMBLE_THREADS = 128

# The thread-scaling sweep. Fixed seed on purpose: every point has to be the
# same realization, or the curve measures cosmic variance as well as speedup.
#
# N=512 rather than 1024 so the serial point is hours, not days; it is still
# large enough that each thread has real work. The 1-thread point dominates the
# cost -- roughly 75 min per run against 50 s at 128 threads, so about 4 node
# hours for the whole sweep. Drop 1 from the list if that is not worth it: the
# existing baseline's `User time (seconds)` is already a serviceable estimate
# of the serial time, just a less honest one.
#
# Descending on purpose. results.json is rewritten after every run, so if the
# serial point overruns the wall limit, every cheaper point is already on disk.
# 64 is one full socket of the 2 x 64-core node, with cpu_scaling.sh pinning
# threads close; 128 crosses the socket boundary.
SCALING = {
    "grid": 512,
    "threads": [128, 64, 32, 16, 8, 4, 1],
    "repeats": 2,
    "seed": 20250915,
}


def sha256_file(path):
    """
    SHA-256 of a file, read in 1 MiB blocks so 8 GiB checkpoints do not
    materialize in memory
    :param path: Path to hash
    :return: Hex digest string
    """
    h = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_time_report(path):
    """
    Pull the metrics we care about out of a /usr/bin/time -v report
    :param path: Path to time.txt
    :return: Dict of metrics, with None for anything absent
    """
    metrics = {
        "user_seconds": None,
        "system_seconds": None,
        "cpu_percent": None,
        "time_wall_clock": None,
        "peak_rss_gb": None,
        "major_page_faults": None,
        "minor_page_faults": None,
        "voluntary_context_switches": None,
        "involuntary_context_switches": None,
        "file_system_inputs": None,
        "file_system_outputs": None,
    }

    for line in path.read_text(errors="replace").splitlines():
        if "User time (seconds):" in line:
            metrics["user_seconds"] = float(line.split(":", 1)[1])
        elif "System time (seconds):" in line:
            metrics["system_seconds"] = float(line.split(":", 1)[1])
        elif "Percent of CPU this job got:" in line:
            metrics["cpu_percent"] = float(line.split(":", 1)[1].strip().rstrip("%"))
        elif "Elapsed (wall clock) time" in line:
            metrics["time_wall_clock"] = line.split("):", 1)[1].strip()
        elif "Maximum resident set size" in line:
            kb = int(line.split(":", 1)[1])
            metrics["peak_rss_gb"] = round(kb / 1024**2, 2)
        elif "Major (requiring I/O) page faults:" in line:
            metrics["major_page_faults"] = int(line.split(":", 1)[1])
        elif "Minor (reclaiming a frame) page faults:" in line:
            metrics["minor_page_faults"] = int(line.split(":", 1)[1])
        elif "Voluntary context switches:" in line:
            metrics["voluntary_context_switches"] = int(line.split(":", 1)[1])
        elif "Involuntary context switches:" in line:
            metrics["involuntary_context_switches"] = int(line.split(":", 1)[1])
        elif "File system inputs:" in line:
            metrics["file_system_inputs"] = int(line.split(":", 1)[1])
        elif "File system outputs:" in line:
            metrics["file_system_outputs"] = int(line.split(":", 1)[1])

    return metrics


SEED_RE = re.compile(r"^\s*GRF seed:\s+(-?\d+)\s*$")


def parse_seed(path):
    """
    Recover the RNG seed the run actually used.

    Four bytes that regenerate the initial conditions exactly. The runner now
    always passes an explicit seed, so this is a cross-check that the binary
    used the seed it was given; with a seed of 0 the code draws its own and
    this is the only place that one is recorded.

    :param path: Path to run.log
    :return: Seed as an int, or None if the line is missing
    """
    for line in path.read_text(errors="replace").splitlines():
        m = SEED_RE.match(line)
        if m:
            return int(m.group(1))
    return None


def run_command_text(args):
    """
    Helper function to run a command and return the output as a string
    :param args: Command line argument
    :return: String containing stdout and stderr
    """
    try:
        result = sp.run(args, capture_output=True, text=True, timeout=60)
        return result.stdout + result.stderr
    except Exception as exc:
        return f"Error: {exc}\n"


def run_shell_text(command):
    """
    Helper function to run a shell command and return the output as a string
    :param command: Command line argument
    :return: String containing stdout and stderr
    """
    try:
        result = sp.run(
            ["bash", "-lc", command],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout + result.stderr
    except Exception as exc:
        return f"Error: {exc}\n"


def reference_state(src=SIM_SRC):
    """
    Record which commit a source tree was at.

    Called for the CPU fork, which the outer zreion-gpu-port repo ignores, so
    nothing else ties a result set to the source that produced it; and for the
    outer repo itself, so the result set also names the runner that drove it.
    Read from the Bridges-2 trees, not from a laptop checkout -- the two drift,
    and the wrong SHA is worse than none.

    :param src: Directory inside the Git work tree to describe
    :return: Dict with the commit, branch, and dirty flag
    """
    git = ["git", "-C", str(src)]
    commit = run_command_text(git + ["rev-parse", "HEAD"]).strip()

    if len(commit) != 40:
        return {"source_dir": str(src), "commit": None, "note": commit}

    diff = run_command_text(git + ["diff", "HEAD"])
    return {
        "source_dir": str(src),
        "commit": commit,
        "branch": run_command_text(git + ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
        # A bare SHA lies when the tree was dirty at build time, which it will be
        # while the fork's fix branches are in progress.
        "dirty": bool(diff.strip()),
    }


def archive_source(out):
    """
    Freeze the source next to its results.

    results.json names a commit in a private repo. That repo is one lost laptop
    away from making every number here unattributable, and an -ipo build cannot
    be reproduced bit-for-bit from source anyway, so the binary comes too. About
    20 MB per case, against a dataset measured in tens of GB.

    :param out: Case output directory
    """
    sp.run(
        ["bash", "-lc", f"git -C {SIM_SRC} archive --format=tar HEAD | gzip > {out/'src.tar.gz'}"],
        check=False,
    )
    diff = run_command_text(["git", "-C", str(SIM_SRC), "diff", "HEAD"])
    if diff.strip():
        (out / "src.diff").write_text(diff)
    if EXEC.is_file():
        shutil.copy2(EXEC, out / EXEC.name)


def write_provenance(out):
    """
    Dump the machine and toolchain this result set came from
    :param out: Case output directory
    """
    commands = {
        "host": ["hostname"],
        "cpu": ["lscpu"],
        "numa": ["numactl", "--hardware"],
        "memory": ["head", "-5", "/proc/meminfo"],
        "os": ["uname", "-a"],
        "os_release": ["cat", "/etc/os-release"],
        "linked_libraries": ["ldd", str(EXEC)],
    }
    shell_commands = {
        "loaded_modules": "module list 2>&1",
        "compiler": "which ifort && ifort --version",
        "mkl_version": "echo ${MKLROOT:-unset}",
        "hdf5_version": "/jet/home/rpearce/local/hdf5-1.14.6/bin/h5dump --version 2>&1",
        "quota_or_projects": "my_quotas 2>&1 || projects 2>&1",
    }
    env_vars = [
        "OMP_NUM_THREADS",
        "OMP_SCHEDULE",
        "MKL_NUM_THREADS",
        "KMP_LIBRARY",
        "KMP_SCHEDULE",
        "KMP_STACKSIZE",
        "KMP_AFFINITY",
        "OMP_PLACES",
        "OMP_PROC_BIND",
        "SLURM_JOB_ID",
        "SLURM_JOB_NAME",
        "SLURM_NTASKS",
        "SLURM_NTASKS_PER_NODE",
        "SLURM_CPUS_PER_TASK",
        "SLURM_JOB_NODELIST",
    ]

    with (out / "provenance.txt").open("w") as file:
        for name, args in commands.items():
            file.write(f"### {name}\n")
            file.write(run_command_text(args))
            file.write("\n")
        for name, command in shell_commands.items():
            file.write(f"### {name}\n")
            file.write(run_shell_text(command))
            file.write("\n")
        file.write("### environment\n")
        for name in env_vars:
            file.write(f"{name}={os.environ.get(name, 'unset')}\n")
        file.write("\n")
        # OMP_NUM_THREADS above is noise: N_cpu is compile-time and the program
        # overrides the environment. The build flag is the real thread count.
        file.write("### note\n")
        file.write("Thread count comes from -DNCPU_VALUE at build time, not from\n")
        file.write("OMP_NUM_THREADS. See results.json -> threads.\n")


def build(grid, threads):
    """
    Rebuild ksz_2lpt.x for one grid size and thread count.

    Both are compile-time parameters in global.f90, so there is no way to sweep
    either one without a full rebuild. make clean is not optional: the .mod
    files carry the old values.

    :param grid: N_grid = Ndm
    :param threads: N_cpu
    :return: Dict with the build flags and the resulting binary hash
    """
    print(f"  building NGRID={grid} NCPU={threads}")
    sp.run(["make", "clean"], cwd=SIM_SRC, check=True)
    sp.run(
        ["make", f"NGRID={grid}", f"NDM={grid}", f"NCPU={threads}", "ksz_2lpt.x"],
        cwd=SIM_SRC,
        check=True,
    )
    if not EXEC.is_file():
        raise FileNotFoundError(f"build produced no {EXEC}")
    return {
        "grid": grid,
        "threads": threads,
        "binary": str(EXEC),
        "binary_sha256": sha256_file(EXEC),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def collect_products(outdir):
    """
    Hash and size every product a run wrote
    :param outdir: The run's out/ directory
    :return: Dict keyed by filename
    """
    products = {}
    for name in PRODUCTS:
        path = outdir / name
        if path.exists():
            products[name] = {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
    return products


def run_one(case_out, index, seed, save_grf, ckpt_level):
    """
    Run the simulation once and record what it did
    :param case_out: Case output directory
    :param index: Repeat number, 1-based
    :param seed: RNG seed; 0 would let the binary draw one from the clock
    :param save_grf: Whether to write grf.hdf5
    :param ckpt_level: 0 for none, 1 for routine-boundary arrays
    :return: Dict of run metadata
    """
    run_dir = case_out / f"run_{index:03d}"
    outdir = run_dir / "out"
    if run_dir.exists():
        raise FileExistsError(
            f"{run_dir} already exists. Change RUN_VERSION or remove the old run."
        )
    outdir.mkdir(parents=True)

    args = [
        str(EXEC),
        str(outdir) + "/",
        str(PARAMS["zmean_zre"]),
        str(PARAMS["alpha_zre"]),
        str(PARAMS["kb_zre"]),
        str(PARAMS["b0_zre"]),
        str(seed),
        "1" if save_grf else "0",
        "0",  # read_grf; the ensemble always generates its own field
        str(ckpt_level),
    ]
    timed_args = ["/usr/bin/time", "-v"] + args
    time_report = run_dir / "time.txt"
    run_log = run_dir / "run.log"

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    t0 = time.perf_counter()

    with run_log.open("w") as stdout, time_report.open("w") as stderr:
        result = sp.run(timed_args, stdout=stdout, stderr=stderr)

    wall_seconds = round(time.perf_counter() - t0, 2)
    ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    return {
        "run": index,
        "returncode": result.returncode,
        "seed": parse_seed(run_log),
        "seed_requested": seed,
        "save_grf": save_grf,
        "checkpoint_level": ckpt_level,
        "wall_seconds": wall_seconds,
        "started_at": started_at,
        "ended_at": ended_at,
        "output_dir": str(outdir),
        "products": collect_products(outdir),
        **parse_time_report(time_report),
    }


SUMMARY_COLUMNS = [
    "case",
    "run",
    "grid",
    "threads",
    "seed",
    "returncode",
    "wall_seconds",
    "peak_rss_gb",
    "cpu_percent",
    "user_seconds",
    "system_seconds",
    "save_grf",
    "checkpoint_level",
    "grf_sha256",
    "checkpoints_sha256",
    "obs_grids_sha256",
    "pk_arrays_sha256",
    "grf_bytes",
    "checkpoints_bytes",
]


def write_summary(case_out, name, build_info, runs):
    """
    Write the flat per-run table the analysis notebook reads
    :param case_out: Case output directory
    :param name: Case name
    :param build_info: Dict from build()
    :param runs: List of dicts from run_one()
    """
    with (case_out / "summary.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for r in runs:
            products = r["products"]
            writer.writerow(
                {
                    "case": name,
                    "run": r["run"],
                    "grid": build_info["grid"],
                    "threads": build_info["threads"],
                    "seed": r["seed"],
                    "returncode": r["returncode"],
                    "wall_seconds": r["wall_seconds"],
                    "peak_rss_gb": r["peak_rss_gb"],
                    "cpu_percent": r["cpu_percent"],
                    "user_seconds": r["user_seconds"],
                    "system_seconds": r["system_seconds"],
                    "save_grf": r["save_grf"],
                    "checkpoint_level": r["checkpoint_level"],
                    "grf_sha256": products.get("grf.hdf5", {}).get("sha256"),
                    "checkpoints_sha256": products.get("checkpoints.hdf5", {}).get("sha256"),
                    "obs_grids_sha256": products.get("obs_grids.hdf5", {}).get("sha256"),
                    "pk_arrays_sha256": products.get("pk_arrays.hdf5", {}).get("sha256"),
                    "grf_bytes": products.get("grf.hdf5", {}).get("bytes"),
                    "checkpoints_bytes": products.get("checkpoints.hdf5", {}).get("bytes"),
                }
            )


def field_bytes(grid):
    """
    One real(8) 3D field at this grid size, in bytes. The unit that all the
    size estimates below are counted in
    :param grid: N_grid
    :return: Bytes
    """
    return 8 * grid**3


def estimate_case_bytes(case):
    """
    Rough disk cost of a case, so a job that will not fit fails on the login
    node instead of three hours in.

    grf.hdf5 is one field. checkpoints.hdf5 is 13: delta1_k, 3+3 gradphi,
    delta2_k, density, 3 velocity, zreion. Science products are ~36 MB at N=1024
    and scale as N^2.

    :param case: One entry from CASES
    :return: Estimated bytes
    """
    fb = field_bytes(case["grid"])
    products = 5 * 8 * case["grid"] ** 2
    return (
        case["grf_runs"] * fb
        + case["ckpt_runs"] * 13 * fb
        + case["repeats"] * products
    )


def human(n):
    """
    Bytes as a short human string
    :param n: Byte count
    :return: String such as '8.6 GB'
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024


def check_space(total):
    """
    Refuse to start a campaign that will not fit on the filesystem.

    Only the filesystem: disk_usage sees Ocean's free space, which is measured
    in petabytes, not the project quota. The quota is what actually binds, and
    the Fortran HDF5 writers ignore write errors, so a full quota means silently
    truncated files and a zero exit code. Check my_quotas before submitting;
    its output is printed here so the job log records what was available.

    :param total: Estimated bytes to be written
    """
    BASE_OUT.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(BASE_OUT).free
    print(f"estimated output {human(total)}, filesystem free at {BASE_OUT} {human(free)}")
    print(run_shell_text("my_quotas 2>&1 || projects 2>&1"))
    if total > 0.9 * free:
        raise SystemExit(
            f"refusing to start: {human(total)} needed, {human(free)} free"
        )


def execute(name, build_info, plan):
    """
    Run one case's repeats and write its metadata
    :param name: Case directory name
    :param build_info: Dict from build()
    :param plan: List of (index, seed, save_grf, ckpt_level) tuples
    :return: The case output directory
    """
    case_out = BASE_OUT / name
    case_out.mkdir(parents=True, exist_ok=True)
    write_provenance(case_out)
    archive_source(case_out)

    runs = []
    for index, seed, save_grf, ckpt_level in plan:
        print(f"  {name} run {index}/{len(plan)}")
        runs.append(run_one(case_out, index, seed, save_grf, ckpt_level))

        # Rewritten after every run: a job that hits its wall limit halfway
        # still leaves a valid results.json for what finished.
        (case_out / "results.json").write_text(
            json.dumps(
                {
                    "case": name,
                    "host": platform.node(),
                    "run_version": RUN_VERSION,
                    "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
                    "build": build_info,
                    "reference": reference_state(),
                    "runner": reference_state(RUNNER_DIR),
                    "params": PARAMS,
                    "runs": runs,
                },
                indent=2,
            )
        )
        write_summary(case_out, name, build_info, runs)

    failed = [r["run"] for r in runs if r["returncode"] != 0]
    if failed:
        print(f"  WARNING: nonzero exit in runs {failed}")
    mismatched = [
        r["run"] for r in runs if r["seed_requested"] and r["seed"] != r["seed_requested"]
    ]
    if mismatched:
        print(f"  WARNING: logged seed differs from requested seed in runs {mismatched}")
    return case_out


def mode_ensemble():
    """
    Build and run every grid size in CASES
    """
    check_space(sum(estimate_case_bytes(c) for c in CASES))

    for case in CASES:
        grid = case["grid"]
        name = f"cpu-{grid}-baseline-{RUN_VERSION}"
        print(f"\n=== {name}  ({human(estimate_case_bytes(case))})")
        build_info = build(grid, ENSEMBLE_THREADS)

        # Seeds drawn here, not by the binary. Given 0, ksz_2lpt.x seeds from
        # the clock via random_seed(), and N=128 runs are seconds apart -- two
        # could share a seed and duplicate a realization inside the ensemble
        # whose spread is the GPU's acceptance envelope. sample() guarantees
        # distinct seeds, and each one is recorded before its run starts.
        seeds = random.SystemRandom().sample(range(1, 2**31), case["repeats"])
        plan = [
            (
                i,
                seeds[i - 1],
                i <= case["grf_runs"],
                1 if i <= case["ckpt_runs"] else 0,
            )
            for i in range(1, case["repeats"] + 1)
        ]
        out = execute(name, build_info, plan)
        print(f"  wrote {out}")


def mode_scaling():
    """
    Sweep thread count at one grid size, holding the realization fixed.

    One build per point, because N_cpu is compile-time. Timing only: no GRF, no
    checkpoints. The output is a parallel-efficiency curve for the exact node
    the reference numbers came from, which is the honest denominator for any
    GPU speedup and is unobtainable once the allocation ends.
    """
    grid = SCALING["grid"]
    for threads in SCALING["threads"]:
        name = f"cpu-{grid}-scaling-{threads:03d}t-{RUN_VERSION}"
        print(f"\n=== {name}")
        build_info = build(grid, threads)
        plan = [
            (i, SCALING["seed"], False, 0)
            for i in range(1, SCALING["repeats"] + 1)
        ]
        out = execute(name, build_info, plan)
        print(f"  wrote {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "mode",
        nargs="?",
        default="ensemble",
        choices=["ensemble", "scaling"],
        help="ensemble: validation runs at every grid size. "
        "scaling: thread sweep at one grid size, fixed seed",
    )
    args = ap.parse_args()

    if not SIM_SRC.is_dir():
        raise FileNotFoundError(f"Could not find source tree: {SIM_SRC}")

    if args.mode == "ensemble":
        mode_ensemble()
    else:
        mode_scaling()


if __name__ == "__main__":
    main()
