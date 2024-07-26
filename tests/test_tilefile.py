import pathlib

import pytest

from tilefx.file import build
from tilefx.file import tilefile as tf


def test_empty_file():
    assert tf.parse("") == tf.ModuleNode([])
    assert tf.parse("""
    # Hello there
    # This file is empty
    
    """) == tf.ModuleNode([])


def test_parse_literals():
    assert tf.parse("100") == tf.Literal(100)
    assert tf.parse("  -12.455\n\n  ") == tf.Literal(-12.455)
    assert tf.parse("true") == tf.Literal(True)
    assert tf.parse("\n false \n ") == tf.Literal(False)
    assert tf.parse(" null") == tf.Literal(None)


def test_empty_dict():
    assert tf.parse("{}") == tf.DictNode({})
    assert tf.parse("\n\n{   \n}\n\n\n") == tf.DictNode({})
    assert tf.parse("{            }") == tf.DictNode({})


def test_json_dict():
    p = tf.parse(
        ' { "alfa": "bravo", "charlie": "delta", "echo": "foxtrot" }'
    )
    assert p == tf.DictNode({
        "alfa": tf.Literal("bravo"),
        "charlie": tf.Literal("delta"),
        "echo": tf.Literal("foxtrot"),
    })

    p = tf.parse("""
    {
        "alfa": "bravo",
        "charlie": "delta",
        "echo": "foxtrot"
    }
    """)
    assert p == tf.DictNode({
        "alfa": tf.Literal("bravo"),
        "charlie": tf.Literal("delta"),
        "echo": tf.Literal("foxtrot"),
    })


def test_json_dict_trailing_comma():
    p = tf.parse("""
    {
        "alfa": "bravo",
        "charlie": "delta",
        "echo": "foxtrot",
    }
    """)
    assert p == tf.DictNode({
        "alfa": tf.Literal("bravo"),
        "charlie": tf.Literal("delta"),
        "echo": tf.Literal("foxtrot"),
    })

    with pytest.raises(tf.ParserError):
        tf.parse("""
        {
            "alfa": "bravo",
            "charlie": "delta",
            "echo": "foxtrot",,
        }
        """)


def test_dict_no_commas():
    p = tf.parse("""
    {
        "alfa": "bravo"
        "charlie": "delta"
        "echo": "foxtrot"
        "golf": "hotel"}
    """)
    assert p == tf.DictNode({
        "alfa": tf.Literal("bravo"),
        "charlie": tf.Literal("delta"),
        "echo": tf.Literal("foxtrot"),
        "golf": tf.Literal("hotel"),
    })


def test_dict_of_dicts():
    p = tf.parse("""
    {
        foo: {alfa: "bravo", charlie: "delta"}
        bar: {echo: "foxtrot", golf: "hotel"}
    }
    """)
    assert p == tf.DictNode({
        "foo": tf.DictNode({
            "alfa": tf.Literal("bravo"),
            "charlie": tf.Literal("delta")
        }),
        "bar": tf.DictNode({
            "echo": tf.Literal("foxtrot"),
            "golf": tf.Literal("hotel")
        }),
    })


def test_parse_list():
    p = tf.parse("""
    [ "foo", 20, obj hello {}, true]
    """)
    assert p == tf.ListNode([
        tf.Literal("foo"),
        tf.Literal(20),
        tf.ObjectNode("hello", None, {}),
        tf.Literal(True)
    ])

    p = tf.parse("""
    [
        "foo",
        20,
        foo.bar,
        true,
    ]
    """)
    assert p == tf.ListNode([
        tf.Literal("foo"),
        tf.Literal(20),
        tf.StaticPythonExpr("foo.bar"),
        tf.Literal(True)
    ])


def test_value_expr():
    p = tf.parse("""
    {
        foo: x + 5
        bar: (y / 2)
    }
    """)
    assert p == tf.DictNode({
        "foo": tf.StaticPythonExpr("x + 5"),
        "bar": tf.StaticPythonExpr("y / 2")
    })

    with pytest.raises(tf.ParserError):
        tf.parse("""
        {
            foo: 20 100
        }
        """)


def test_multiline_value_expr():
    p = tf.parse("""
    {
        foo: (
            "real" if is_real
            else "unreal"
        )
        comma: x + 10,
        bar: "hello"
    }
    """)
    assert p == tf.DictNode({
        "foo": tf.StaticPythonExpr('"real" if is_real\n'
                               '            else "unreal"'),
        "comma": tf.StaticPythonExpr("x + 10"),
        "bar": tf.Literal("hello")
    })


def test_value_expr_as_key():
    p = tf.parse("""
    {
        (DataID(0, "display")): "Hello"
    }
    """)
    assert p == tf.DictNode({
        tf.ComputedKey('DataID(0, "display")'):
            tf.Literal("Hello")
    })


def test_deferred_line_expr():
    p = tf.parse("""
    {
        foo: `node.path() + node.name()`,
        bar: `self.count()`
    }
    """)
    assert p == tf.DictNode({
        "foo": tf.PythonExpr("node.path() + node.name()"),
        "bar": tf.PythonExpr("self.count()"),
    })


def test_deferred_block_expr():
    p = tf.parse("""
    {
        foo: ```
        x = 10
        self.text = {"x": x}
        ```
    }
    """)
    assert p == tf.DictNode({
        "foo": tf.PythonBlock('x = 10\nself.text = {"x": x}'),
    })


def test_parse_jsonpath():
    p = tf.parse("""
    {
        foo: $.foo.bar
        bar: $.alfa.bravo
        not_a_path: "$.alfa.bravo"
        robotron: 2000
    }
    """)
    assert p == tf.DictNode({
        "robotron": tf.Literal(2000),
        "not_a_path": tf.Literal("$.alfa.bravo"),
        "foo": tf.JsonpathNode("$.foo.bar"),
        "bar": tf.JsonpathNode("$.alfa.bravo"),
    })


def test_parse_jsonpath_this():
    p = tf.parse("""
    model "foo" {
        rows: $.attrs
        name: @.name
        type: @.type
    }
    """)
    assert p == tf.ModelNode("foo", {
        "rows": tf.JsonpathNode("$.attrs"),
        "name": tf.JsonpathNode("@.name"),
        "type": tf.JsonpathNode("@.type")
    })


def test_parse_object():
    p = tf.parse("""
    obj surface {
        foo: 100
        bar: "baz"
    }
    """)
    assert p == tf.ObjectNode("surface", None, {
        "foo": tf.Literal(100),
        "bar": tf.Literal("baz")
    })

    p = tf.parse("""
    obj surface "root" {
        foo: 100
        bar: "baz"
    }
    """)
    assert p == tf.ObjectNode("surface", "root", {
        "foo": tf.Literal(100),
        "bar": tf.Literal("baz")
    })


def test_parse_models():
    p = tf.parse("""
        model {
            rows: $.rows.items()
        }
        """)
    assert p == tf.ModelNode(None, {
        "rows": tf.JsonpathNode("$.rows.items()")
    })

    p = tf.parse("""
        model "attrs" {
            rows: `attrs`
        }
        """)
    assert p == tf.ModelNode("attrs", {
        "rows": tf.PythonExpr("attrs")
    })


def test_parse_template():
    p = tf.parse("""
    template anchors {
        x: 10
        y: "why"
    }
    """)
    assert p == tf.ObjectNode("anchors", None, {
        "x": tf.Literal(10),
        "y": tf.Literal("why")
    }, is_template=True)

    p = tf.parse("""
    template rectangle "count" {
        x: 10
        y: "why"
    }
    """)
    assert p == tf.ObjectNode("rectangle", "count", {
        "x": tf.Literal(10),
        "y": tf.Literal("why")
    }, is_template=True)

    with pytest.raises(tf.ParserError):
        tf.parse("""
        template {
            x: 10
            y: "why"
        }
        """)


def test_object_values():
    p = tf.parse("""
    obj surface "root" {
        foo: 100
        title_item: obj text {
            x: 10
            y: 20
        }
        bar: "baz"
    }
    """)
    assert p == tf.ObjectNode("surface", "root", {
        "foo": tf.Literal(100),
        "title_item": tf.ObjectNode("text", None, {
            "x": tf.Literal(10),
            "y": tf.Literal(20)
        }),
        "bar": tf.Literal("baz")
    })


def test_parse_on_update():
    p = tf.parse("""
    obj surface {
        ```
        x = 10
        ```
        
        y: 20
        z: 40
    }
    """)
    assert p == tf.ObjectNode("surface", None, {
        "y": tf.Literal(20),
        "z": tf.Literal(40)
    }, on_update=tf.PythonBlock("x = 10"))

    p = tf.parse("""
    model "foo" {
        ```
        x = 10
        ```

        rows: $.attrs.*
        y: `row.y`
        z: `row.z`
    }
    """)
    assert p == tf.ModelNode("foo", {
        "rows": tf.JsonpathNode("$.attrs.*"),
        "y": tf.PythonExpr("row.y"),
        "z": tf.PythonExpr("row.z")
    }, on_update=tf.PythonBlock("x = 10"))

    with pytest.raises(tf.ParserError):
        tf.parse("""
        obj surface {
            x: 20
            ```
            print('hello')
            ```
        }
        """)

    with pytest.raises(tf.ParserError):
        tf.parse("""
        obj surface {
            ```
            print('hello')
            ```,
            x: 10
        }
        """)


def test_parse_module():
    p = tf.parse("""
    ```
    import m
    ```
    
    obj surface "root" {
        foo: m.xy
    }
    """)
    assert p == tf.ModuleNode([
        tf.PythonBlock("import m"),
        tf.ObjectNode("surface", "root", {
            "foo": tf.StaticPythonExpr("m.xy")
        })
    ])


def test_env_var():
    assert tf.parse("$HOUDINI_TEST") == \
           tf.EnvVarNode("HOUDINI_TEST")

    p = tf.parse("""
    {
        text: $JOB
        bold: true
    }
    """)
    assert p == tf.DictNode({
        "text": tf.EnvVarNode("JOB"),
        "bold": tf.Literal(True)
    })

    with pytest.raises(tf.ParserError):
        tf.parse("""
        {
            text: $JOB + 20
            bold: true
        }
        """)


def test_object_items():
    p = tf.parse("""
    obj surface "root" {
        x: 10
        y: "why"
        
        obj text { html: "Hello" }
        template foo {}
        model {
            rows: $.attrs
        }
    }
    """)
    assert p == tf.ObjectNode("surface", "root", {
        "x": tf.Literal(10),
        "y": tf.Literal("why"),
    }, [
        tf.ObjectNode("text", None, {
            "html": tf.Literal("Hello")
        }),
        tf.ObjectNode("foo", None, {}, is_template=True),
        tf.ModelNode(None, {
            "rows": tf.JsonpathNode("$.attrs")
        })
    ])


def test_combined():
    text = pathlib.Path("../files/nodeinfo.tilefile").read_text()
    p = tf.parse(text)
    assert p == tf.ObjectNode("surface", "root", {
        "spacing": tf.Literal(10),
        "margins": tf.Literal(5),
        "title_target": tf.Literal("node_header"),
        "cutoff_item": tf.Literal("comment_layout"),
        "label": tf.PythonExpr("node.name()"),
        "memory": tf.JsonpathNode("$.memory.total"),
        "title_item": tf.ObjectNode("anchors", None, {
            "spacing": tf.Literal(5),
            "fixed_height": tf.Literal(28),
            "fill_color": tf.StaticPythonExpr("ThemeColor.bg"),
            "on_update": tf.PythonBlock(
                'titlebar_icon.icon_name = icon\n'
                'titlebar_path.html = f"{parent_path}/<b>{node_name}</b>"'
            ),
        }, [
            tf.ObjectNode("houdini_icon", "titlebar_icon", {
                "fixed_size": tf.ListNode([
                    tf.Literal(28),
                    tf.Literal(28)]
                ),
                "anchor.left": tf.DictNode({
                    "to": tf.Literal("parent.left"),
                    "spacing": tf.Literal(10)
                }),
                "anchor.vcenter": tf.Literal("parent.v_center"),
                "icon_name": tf.PythonExpr("icon"),
            }),
            tf.ObjectNode("controls.text", "titlebar_path", {
                "text_color": tf.StaticPythonExpr("ThemeColor.primary"),
                "text_size": tf.StaticPythonExpr("TextSize.small"),
                "text_align": tf.StaticPythonExpr(
                    "Qt.Align.vcenter | Qt.Align.left"),
                "html": tf.PythonExpr(
                    'f"{parent_path}/<b>{node_name}</b>"',
                )
            })
        ])
    }, [
        tf.ObjectNode("row", "node_header", {
            "bg_visible": tf.Literal(False),
            "margins": tf.Literal(0),
            "spacing": tf.Literal(5)
        })
    ])


def test_generation():
    text = pathlib.Path("../files/nodeinfo.tilefile").read_text()
    p = tf.parse(text)
    assert isinstance(p, tf.ModuleNode)
    ctx = build.BuildContext(p, "", "")
    lines = build.moduleSetup(p, ctx)
    print("\n".join(lines))
    assert False
