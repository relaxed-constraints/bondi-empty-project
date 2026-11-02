# BONDI JSON-Storm

A project for LLM-based query generation and translation for document stores.

It builds on the following dependencies and tools:
- [uv](https://docs.astral.sh/uv/getting-started/installation/) a Python project management tool
- [Docker](https://docs.docker.com/get-started/) a platform for containerized applications
- [BONDI](https://relaxed-constraints.github.io/bondi/) a document database research toolkit
- [Yanex](https://github.com/rueckstiess/yanex) a tool for managing experiments and tracking results
- [Jupyter Notebooks](https://jupyter.org/) an interactive environment for running and visualizing experiments
- [pandas](https://pandas.pydata.org/) a tabular data analysis library for Python
- [Matplotlib](https://matplotlib.org/) a plotting library for Python
- [MARP](https://marp.app) (optional) a tool for rendering Markdown into slides

<details>
  <summary><b>What is all this stuff?</b></summary>

#### uv

If you're unfamiliar with `uv`, it's worth spending some time to understand its
role in managing virtual environments, dependencies, publishing packages and
running scripts. `uv` is a modern tool for Python project management that
simplifies these tasks compared to traditional approaches using `virtualenv`, 
`pip`, and custom shell scripts.

Read about `uv` features in the [official documentation](https://docs.astral.sh/uv/getting-started/features/). 

#### Docker

Docker is a platform for developing, shipping, and running applications in containers.
Containers package an application and its dependencies, ensuring consistent behavior
across different environments. It makes it very easy to start and manage containerized
services, like databases locally for development and experimentation. 

Read more in the [official Docker documentation](https://docs.docker.com/get-started/).

#### BONDI

BONDI is a tooklkit for conducting research with document databases, with a focus on MongoDB. 
It provides tools for deploying databases, generating, running and profiling query workloads, 
analysing the schema of database collections, and estimating cardinalities of queries. 

This repo is an example project demonstrating how to use BONDI for research with MongoDB, 
including dataset preparation, database deployment, and experiment tracking.

More info and the full documentation can be found on the [BONDI documentation site](https://relaxed-constraints.github.io/bondi/).

#### Yanex

Yanex is a generic tool for managing experiments and tracking and analysing their results. 
It allows you to run scripts with specific configurations, record the outputs, and maintain
a history of experiments. This is particularly useful for reproducibility and for 
understanding the impact of different parameters on your results. 

Yanex' documentation can be found on the [Yanex github page](https://github.com/rueckstiess/yanex).

#### Jupyter Notebooks

Jupyter notebooks combine executable code, explanations and plots in one document.
We use them to explore saved experiment results interactively. Open the notebooks
in VS Code with its Jupyter extension and select this project's Python environment
as the kernel that runs the code.

#### pandas

pandas provides DataFrames: tables that you can filter, group and summarise in
Python. In this project, we use them to organise query measurements, compare index
sets and calculate statistics such as median execution times and speedups.

#### Matplotlib

Matplotlib creates plots from Python data. We use it with pandas to turn benchmark
results into charts for analysis and progress updates.

#### Marp (optional)

Marp renders Markdown files as slide decks. We use it to write simple progress
updates with text, tables, equations and images. The Marp for VS Code extension
provides a slide preview and export commands. Start with the example deck in
[results/week-1/presentation.md](results/week-1/presentation.md).

</details>



## Repository structure

| Directory | Purpose |
| --- | --- |
| `docs/` | Space for project notes and instructions. |
| `experiments/` | Yanex scripts |
| `experiments/configs/` | YAML parameters; `config.yaml` contains `name`. |
| `notebooks/` | Interactive Jupyter notebooks for exploring experiment results. |
| `results/` | Use this directory to store experiment results and create progress update slides. |
| `src/json_storm/` | Reusable Python code. |
| `tests/` | Unit tests for the project. |


## Setup

### 1. Clone this repository

Run the following command to clone the project repository to your local machine:

```sh
git clone https://github.com/relaxed-constraints/bondi-json-storm.git
cd bondi-json-storm
```

### 2. Install dependencies and run tests

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
these commands from this directory:

```sh
uv sync --locked     # installs dependencies
uv run pytest        # runs the unit tests
uv run ruff check    # runs the linter to check code style
uv run ruff format   # formats the code according to the linter rules
```

## Run the CLI

```sh
uv run json-storm --help
```

## License

[MIT](LICENSE).
