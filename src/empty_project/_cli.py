"""A minimal command-line interface for the greeting helper."""

import argparse

from empty_project.hello import hello_world


def main() -> None:
    """Parse command-line arguments and print a greeting."""
    parser = argparse.ArgumentParser(description="Print a greeting.")
    parser.add_argument("--name", default="World", help="Name to greet (default: World)")
    args = parser.parse_args()

    # invoke the greeting helper with the provided name
    hello_world(args.name)


if __name__ == "__main__":
    main()
