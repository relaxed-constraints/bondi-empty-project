"""Test the greeting printed by the reusable helper."""

from empty_project.hello import hello_world


def test_hello_world(capsys):
    hello_world("Student")
    assert capsys.readouterr().out == "Hello, Student\n"
