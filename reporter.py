import pandas as pd
from pathlib import Path
from omegaconf import OmegaConf
from flatten_dict import flatten
from argparse import ArgumentParser

from rich.console import Console
from rich.table import Table


def gather_inference_report(
    folder: Path,
) -> pd.DataFrame:
    """
    Gather all results and configs from the given folder.

    Parameters
    ----------
    folder : Path
        The folder containing the results of the benchmark.

    Returns
    -------
    pd.DataFrame
        The results of the benchmark with their corresponding parameters.
    """

    # List all csv stats
    stats_files = [
        stats_file for stats_file in folder.glob(f"**/inference_results.csv")
    ]
    configs_files = [
        config_file for config_file in folder.glob(f"**/hydra_config.yaml")
    ]

    stats_dfs = {i: pd.read_csv(f, index_col=0) for i, f in enumerate(stats_files)}
    configs_dfs = {
        i: pd.DataFrame(flatten(OmegaConf.load(f), reducer="dot"), index=[0])
        for i, f in enumerate(configs_files)
    }

    if len(stats_dfs) == 0 or len(configs_dfs) == 0:
        raise ValueError(f"No results found in {folder}")

    # Merge perfs dataframes with configs
    inference_reports = {
        name: configs_dfs[name].merge(
            stats_dfs[name], left_index=True, right_index=True
        )
        for name in stats_dfs.keys()
    }
    # Concatenate all reports
    inference_report = pd.concat(inference_reports.values(), axis=0, ignore_index=True)
    # set experiment_id as index
    inference_report.set_index("experiment_hash", inplace=True, drop=True)
    # sort by throughput
    inference_report.sort_values(by=["throughput(s^-1)"], ascending=False, inplace=True)

    return inference_report


def show_inference_report(report, with_baseline=False):
    """
    Display the results in the console.

    Parameters
    ----------
    static_params : dict
        The unchanging parameters of the benchmark.
    bench_results : pd.DataFrame
        The results of the benchmark with their corresponding changing parameters.
    """

    # columns to display
    show_report = report[
        ["latency.median(s)", "memory.peak(MB)", "throughput(s^-1)"]
        + (["baseline", "speedup"] if with_baseline else [])
    ]

    table = Table(
        show_header=True,
        title="Inference Benchmark Report",
    )

    show_report.columns = pd.MultiIndex.from_tuples(
        [tuple(col.split(".")) for col in show_report.columns.to_list()]
    )

    table.add_column("experiment_hash", justify="left")
    for level in range(show_report.columns.nlevels):
        columns = show_report.columns.get_level_values(level).to_list()
        for i in range(len(columns)):
            if columns[i] != columns[i]:  # nan
                columns[i] = ""

        if level < show_report.columns.nlevels - 1:
            for col in columns:
                table.add_column(col)
            pass
        else:
            table.add_row("", *columns, end_section=True)

    for row in show_report.itertuples(index=True):
        table_row = []
        for elm in row:
            if type(elm) == float:
                # round to 2 decimals if bigger than 1
                if elm >= 1:
                    table_row.append(f"{elm:.2f}")
                else:
                    table_row.append(f"{elm:.2e}")
            elif type(elm) == bool:
                if elm:
                    table_row.append("[green]✔[/green]")
                else:
                    table_row.append("[red]✘[/red]")
            elif elm is None:
                table_row.append(None)
            else:
                table_row.append(str(elm))

        table.add_row(*table_row, end_section=False)

    console = Console(record=True)
    console.print(table)


def main(args):
    experiments_report = gather_inference_report(args.experiments_folder)
    if args.baseline_folder is not None:
        print("Using the provided baseline")
        baseline_report = gather_inference_report(args.baseline_folder)
        assert len(baseline_report) == 1, "There should be only one baseline"
        experiments_report["baseline"] = [False] * len(experiments_report)
        experiments_report["speedup"] = (
            experiments_report["throughput(s^-1)"]
            / baseline_report["throughput(s^-1)"].iloc[0]
        )
        baseline_report["baseline"] = True
        baseline_report["speedup"] = 1.0

        report = pd.concat(
            [experiments_report, baseline_report], axis=0, ignore_index=False
        )
    else:
        print("No baseline provided")
        report = experiments_report

    report.to_csv(f"{args.experiments_folder}/inference_report.csv", index=True)
    show_inference_report(report, with_baseline=args.baseline_folder is not None)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--experiments-folder",
        "-f",
        type=Path,
        default="sweeps/",
        help="The folder containing the results of the benchmark.",
    )
    parser.add_argument(
        "--baseline-folder",
        "-b",
        type=Path,
        help="The folder containing the results of the baseline.",
    )
    args = parser.parse_args()
    main(args)