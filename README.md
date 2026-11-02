# BONDI empty project

A minimal starting point for students building their own BONDI research project.
It uses the same dependencies as [bondi-demo-project](https://github.com/relaxed-constraints/bondi-demo-project), 
but starts with a barebones setup with one reusable function and examples of calling it from an experiment, a notebook and a test.


## Repository structure

| Directory | Purpose |
| --- | --- |
| `docs/` | Space for project notes and instructions. |
| `experiments/` | Yanex scripts; `greet.py` calls the greeting helper and logs a metric. |
| `experiments/configs/` | YAML parameters; `config.yaml` contains `name`. |
| `notebooks/` | Examples calling the helper and plotting a small table with pandas and Matplotlib. |
| `results/` | Use this directory to store experiment results and create progress update slides. |
| `src/empty_project/` | Reusable Python code goes here, starting with `hello.py`. |
| `tests/` | A unit test checking the greeting printed by `hello_world()`. |


## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
these commands from this directory:

```sh
uv sync --locked     # installs dependencies
uv run pytest        # runs the unit tests
uv run ruff check    # runs the linter to check code style
uv run ruff format   # formats the code according to the linter rules
```


## Run the experiment

Activate the virtual environment and change into the experiment directory.

```sh
source .venv/bin/activate
cd experiments
```

Then run the experiment with
```sh
yanex run greet.py -c configs/config.yaml
```

You can also override the default name with the `-p` (short for `--param`) flag, for example:

```sh
yanex run greet.py -c configs/config.yaml -p name=Student
```

The experiment prints a greeting and records the `name_length` metric. Yanex
prints the experiment ID; inspect it with `yanex show <experiment-id>`.
Without a config file, the name defaults to `World`.

## Use the notebook

Open `notebooks/hello.ipynb` in VS Code with its Jupyter extension and select
this project's `.venv/bin/python` as the kernel. Run the greeting cell, then the small pandas/Matplotlib plotting example.

## Run the CLI

This project includes a stub command-line interface that you can extend for your own purposes.
Rename it in `pyproject.toml` under the `[project.scripts]` section to match your desired CLI command.

```sh
uv run empty-cli
uv run empty-cli --name Student
uv run empty-cli --help
```

The CLI prints `Hello, World` by default, or greets the supplied name. Extend
`src/empty_project/_cli.py` to add arguments using Python's `argparse` module.


## Progress updates

Start with [the example slide deck](results/week-1/presentation.md). Install
[Marp for VS Code](https://marketplace.visualstudio.com/items?itemName=marp-team.marp-vscode)
to preview and export it. Replace the demo title and examples with your own work.

## License

[MIT](LICENSE).
