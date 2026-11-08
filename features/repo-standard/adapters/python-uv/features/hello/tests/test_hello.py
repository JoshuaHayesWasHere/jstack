from hello import greet


def test_greet_names_whom_it_greets():
    assert greet("repo") == "hello, repo"
