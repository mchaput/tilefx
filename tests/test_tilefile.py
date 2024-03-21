import pytest

from tilefx.tilefile import (parse, ParserError, JsonPathExpression,
                             PythonExpression)


def test_parse_literals():
    assert parse("100") == 100
    assert parse("  -12.455\n\n  ") == -12.455
    assert parse("true") is True
    assert parse("\n false \n ") is False
    assert parse(" null") is None


def test_empty_dict():
    assert parse("{}") == {}
    assert parse("\n\n{   \n}\n\n\n") == {}
    assert parse("{            }") == {}


def test_json_dict():
    p = parse(' { "alfa": "bravo", "charlie": "delta", "echo": "foxtrot" }')
    assert p == {"alfa": "bravo", "charlie": "delta", "echo": "foxtrot"}

    p = parse("""
    {
        "alfa": "bravo",
        "charlie": "delta",
        "echo": "foxtrot"
    }
    """)
    assert p == {"alfa": "bravo", "charlie": "delta", "echo": "foxtrot"}


def test_json_dict_trailing_comma():
    p = parse("""
    {
        "alfa": "bravo",
        "charlie": "delta",
        "echo": "foxtrot",
    }
    """)
    assert p == {"alfa": "bravo", "charlie": "delta", "echo": "foxtrot"}

    with pytest.raises(ParserError):
        parse("""
        {
            "alfa": "bravo",
            "charlie": "delta",
            "echo": "foxtrot",,
        }
        """)


def test_dict_no_commas():
    p = parse("""
    {
        "alfa": "bravo"
        "charlie": "delta"
        "echo": "foxtrot"
        "golf": "hotel"}
    """)
    assert p == {"alfa": "bravo", "charlie": "delta", "echo": "foxtrot",
                 "golf": "hotel"}


def test_dict_of_dicts():
    p = parse("""
    {
        foo: {alfa: "bravo", charlie: "delta"}
        bar: {echo: "foxtrot", golf: "hotel"}
    }
    """)
    assert p == {
        "foo": {"alfa":"bravo", "charlie": "delta"},
        "bar": {"echo": "foxtrot", "golf": "hotel"},
    }


def test_parse_expr():
    p = parse("""
    root {
        foo: expr x + 5
        bar: (y / 2)
    }
    """)
    assert p == {
        "type": "root",
        "properties": {
            "foo": {"expression": "x + 5"},
            "bar": {"expression": "(y / 2)"}
        }
    }


def test_parse_multiline_expr():
    p = parse("""
    root {
        foo: expr (
            "real" if is_real
            else "unreal"
        )
        bar: "hello"
    }
    """)
    assert p == {
        "type": "root",
        "bar": "hello",
        "properties": {
            "foo": {"expression": '( "real" if is_real else "unreal" )'}
        }
    }


def test_parse_jsonpath():
    p = parse("""
    root {
        foo: path $.foo.bar
        bar: $.alfa.bravo
        not_a_path: "$.alfa.bravo"
        robotron: 2000
    }
    """)
    assert p == {
        "type": "root",
        "robotron": 2000,
        "not_a_path": "$.alfa.bravo",
        "properties": {
            "foo": {"path": "$.foo.bar"},
            "bar": {"path": "$.alfa.bravo"}
        }
    }


def test_object_modifiers():
    p = parse("""
    root {
        row_path: path $.foo.bar
        {
            all: True
            value_map: {
                "foo": "bar"
                "baz": "quux"
            }
        }
    }
    """)


def test_parse_variable_assignments():
    p = parse("""
    root {
        let x = expr (
            "real" if is_real
            else "unreal"
        )
        let jp = path $.foo.bar
        let z = 500
        foo: 20
    }
    """)
    assert p == {
        "type": "root",
        "foo": 20,
        "variables": {
            "x": {"expression": '( "real" if is_real else "unreal" )'},
            "jp": {"path": "$.foo.bar"},
            "z": 500
        }
    }


def test_dict_variable():
    p = parse("""
    root {
        let d = {
            foo: "bar"
            baz: "quux"
        }
    }
    """)
    assert p == {
        "type": "root",
        "variables": {
            "d": {
                "foo": "bar",
                "baz": "quux",
            }
        }
    }


def test_parse_imports():
    p = parse("""
    root {
        import m
        import q, r, s
        from a import (
            b, c
        )
        import foo as bar
        let y = expr 10 + bar
        let z = 500
        foo: 20
    }
    """)
    assert p == {
        "type": "root",
        "foo": 20,
        "variables": {
            "y": {"expression": "10 + bar"},
            "z": 500,
        },
        "imports": {
            'from': {
                'a': {'imports': ['b', 'c']}
            },
            'import_as': {'foo': 'bar'},
            'imports': ['m', 'q', 'r', 's']
        },
    }


def test_parse_object_value():
    p = parse("""
    root {
        title_item: text {
            text: expr f"hello {name}"
        }
    }
    """)
    assert p == {
        "type": "root",
        "title_item": {
            "type": "text",
            "properties": {
                "text": {"expression": 'f"hello {name}"'}
            }
        }
    }


# def test_parse_function_def():
#     p = parse("""
#     root {
#         def hello(name):
#             return f"Hello {name}"
#
#         let n = "Matt"
#         title_item: text {
#             text: expr hello(n)
#         }
#     }
#     """)
#     assert p == {
#         "type": "root",
#         "title_item": {
#             "type": "text",
#             "variables": {
#                 "n": "Matt",
#             },
#             "functions": [
#                 '        def hello(name):\n            return f"Hello {name}\n"'
#             ],
#             "properties": {
#                 "text": {"expression": "hello(n)"}
#             }
#         }
#     }
