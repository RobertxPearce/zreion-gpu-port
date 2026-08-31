# -----------------------------------------------------------------------------
# Run repeated CPU baseline simulations with the original zreion/ksz_2lpt code
# on Bridges-2 and write timing, output locations, and run-environment metadata.
#
# Write:
#   OUT/provenance.txt       : Host, CPU, memory, OS, compiler, module, library,
#                              quota/project, and selected environment details
#   OUT/results.json         : Executable path, parameter values, OMP thread
#                              setting, start/end timestamps, elapsed wall time,
#                              return code, and output directory for each repeat
#   OUT/run_<n>/stdout.txt   : Standard output from ksz_2lpt.x
#   OUT/run_<n>/stderr.log   : Standard error from ksz_2lpt.x
#   OUT/run_<n>/out/         : HDF5 products written by ksz_2lpt.x
#
# Robert Pearce
# -----------------------------------------------------------------------------

from pathlib import Path
import json
import platform
import subprocess as sp
import time
import os

RUN_VERSION = "v2"

# Paths on the Bridges-2 supercomputer
EXEC = Path("/jet/home/rpearce/software/ksz_2lpt/ksz_2lpt.x")
OUT = Path(f"~/ocean/baseline/zreion_cpu_baseline_{RUN_VERSION}").expanduser()

# zreion Parameter values set at the midpoint of the bounds from reionemu
PARAMS = {
    "zmean_zre": 8.0,
    "alpha_zre": 0.5,
    "kb_zre": 1.05,
    "b0_zre": 0.45,
}

# Number of times to run the simulation
REPEATS = 10


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


def write_provenance():
    commands = {
        "host": ["hostname"],
        "cpu": ["lscpu"],
        "memory": ["head", "-5", "/proc/meminfo"],
        "os": ["uname", "-a"],
        "os_release": ["cat", "/etc/os-release"],
        "linked_libraries": ["ldd", str(EXEC)],
    }
    shell_commands = {
        "loaded_modules": "module list 2>&1",
        "compiler": "which ifort && ifort --version",
        "quota_or_projects": "my_quotas 2>&1 || projects 2>&1",
    }
    env_vars = [
        "OMP_NUM_THREADS",
        "OMP_SCHEDULE",
        "MKL_NUM_THREADS",
        "KMP_LIBRARY",
        "KMP_SCHEDULE",
        "KMP_STACKSIZE",
        "SLURM_JOB_ID",
        "SLURM_JOB_NAME",
        "SLURM_NTASKS",
        "SLURM_NTASKS_PER_NODE",
        "SLURM_CPUS_PER_TASK",
        "SLURM_JOB_NODELIST",
    ]

    with (OUT / "provenance.txt").open("w") as file:
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


def run_case(i):
    """
    Function to run one simulation
    :param i: Run number
    :return: Dict containing run metadata
    """
    case = OUT / f"run_{i:03d}"
    outdir = case / "out"
    if case.exists():
        raise FileExistsError(
            f"{case} already exists. Change RUN_VERSION or remove the old run directory."
        )
    outdir.mkdir(parents=True)
    
    # Build command line arguments for ksz_2lpt.x
    args = [
        str(EXEC),
        str(outdir) + "/",
        str(PARAMS["zmean_zre"]),
        str(PARAMS["alpha_zre"]),
        str(PARAMS["kb_zre"]),
        str(PARAMS["b0_zre"]),
    ]
    
    # Start the timer for elapsed time
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    t0 = time.perf_counter()
    
    with (case / "stdout.txt").open("w") as stdout, (case / "stderr.log").open("w") as stderr:
        result_out = sp.run(args, stdout=stdout, stderr=stderr)
        
    wall_seconds = round(time.perf_counter() - t0, 2)
    ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    
    return {
        "run": i,
        "returncode": result_out.returncode,
        "wall_seconds": wall_seconds,
        "started_at": started_at,
        "ended_at": ended_at,
        "output_dir": str(outdir),
    }


def main():
    if not EXEC.is_file():
        raise FileNotFoundError(f"Could not find executable: {EXEC}")

    OUT.mkdir(parents=True, exist_ok=True)
    write_provenance()

    results = []

    for i in range(1, REPEATS + 1):
        print(f"Running case {i}/{REPEATS}")
        record = run_case(i)
        results.append(record)

        summary = {
            "host": platform.node(),
            "executable": str(EXEC),
            "params": PARAMS,
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
            "runs": results,
        }

        (OUT / "results.json").write_text(json.dumps(summary, indent=2))

    print(f"Wrote {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
