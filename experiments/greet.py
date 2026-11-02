"""Greet someone and record a simple Yanex metric."""

import yanex

from empty_project.hello import hello_world

if __name__ == "__main__":
    # read the name parameter from Yanex
    name = yanex.get_param("name", default="World")

    # greet the person using the hello_world function
    hello_world(name)

    # log a dummy metric, here recording the length of the name
    yanex.log_metrics({"name_length": len(name)})
