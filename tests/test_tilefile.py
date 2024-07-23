import pathlib

import pytest

from tilefx.file import tilefile, build


def test_empty_file():
    assert tilefile.parse("") == tilefile.ModuleNode([])
    assert tilefile.parse("""
    # Hello there
    # This file is empty
    
    """) == tilefile.ModuleNode([])


def test_parse_literals():
    assert tilefile.parse("100") == tilefile.Literal(100)
    assert tilefile.parse("  -12.455\n\n  ") == tilefile.Literal(-12.455)
    assert tilefile.parse("true") == tilefile.Literal(True)
    assert tilefile.parse("\n false \n ") == tilefile.Literal(False)
    assert tilefile.parse(" null") == tilefile.Literal(None)


def test_empty_dict():
    assert tilefile.parse("{}") == tilefile.DictNode({})
    assert tilefile.parse("\n\n{   \n}\n\n\n") == tilefile.DictNode({})
    assert tilefile.parse("{            }") == tilefile.DictNode({})


def test_json_dict():
    p = tilefile.parse(
        ' { "alfa": "bravo", "charlie": "delta", "echo": "foxtrot" }'
    )
    assert p == tilefile.DictNode({
        "alfa": tilefile.Literal("bravo"),
        "charlie": tilefile.Literal("delta"),
        "echo": tilefile.Literal("foxtrot"),
    })

    p = tilefile.parse("""
    {
        "alfa": "bravo",
        "charlie": "delta",
        "echo": "foxtrot"
    }
    """)
    assert p == tilefile.DictNode({
        "alfa": tilefile.Literal("bravo"),
        "charlie": tilefile.Literal("delta"),
        "echo": tilefile.Literal("foxtrot"),
    })


def test_json_dict_trailing_comma():
    p = tilefile.parse("""
    {
        "alfa": "bravo",
        "charlie": "delta",
        "echo": "foxtrot",
    }
    """)
    assert p == tilefile.DictNode({
        "alfa": tilefile.Literal("bravo"),
        "charlie": tilefile.Literal("delta"),
        "echo": tilefile.Literal("foxtrot"),
    })

    with pytest.raises(tilefile.ParserError):
        tilefile.parse("""
        {
            "alfa": "bravo",
            "charlie": "delta",
            "echo": "foxtrot",,
        }
        """)


def test_dict_no_commas():
    p = tilefile.parse("""
    {
        "alfa": "bravo"
        "charlie": "delta"
        "echo": "foxtrot"
        "golf": "hotel"}
    """)
    assert p == tilefile.DictNode({
        "alfa": tilefile.Literal("bravo"),
        "charlie": tilefile.Literal("delta"),
        "echo": tilefile.Literal("foxtrot"),
        "golf": tilefile.Literal("hotel"),
    })


def test_dict_of_dicts():
    p = tilefile.parse("""
    {
        foo: {alfa: "bravo", charlie: "delta"}
        bar: {echo: "foxtrot", golf: "hotel"}
    }
    """)
    assert p == tilefile.DictNode({
        "foo": tilefile.DictNode({
            "alfa": tilefile.Literal("bravo"),
            "charlie": tilefile.Literal("delta")
        }),
        "bar": tilefile.DictNode({
            "echo": tilefile.Literal("foxtrot"),
            "golf": tilefile.Literal("hotel")
        }),
    })


def test_parse_list():
    p = tilefile.parse("""
    [ "foo", 20, obj hello {}, true]
    """)
    assert p == tilefile.ListNode([
        tilefile.Literal("foo"),
        tilefile.Literal(20),
        tilefile.ObjectNode("hello", None, {}),
        tilefile.Literal(True)
    ])

    p = tilefile.parse("""
    [
        "foo",
        20,
        foo.bar,
        true,
    ]
    """)
    assert p == tilefile.ListNode([
        tilefile.Literal("foo"),
        tilefile.Literal(20),
        tilefile.StaticPythonExpr("foo.bar"),
        tilefile.Literal(True)
    ])


def test_value_expr():
    p = tilefile.parse("""
    {
        foo: x + 5
        bar: (y / 2)
    }
    """)
    assert p == tilefile.DictNode({
        "foo": tilefile.StaticPythonExpr("x + 5"),
        "bar": tilefile.StaticPythonExpr("y / 2")
    })

    with pytest.raises(tilefile.ParserError):
        tilefile.parse("""
        {
            foo: 20 100
        }
        """)


def test_multiline_value_expr():
    p = tilefile.parse("""
    {
        foo: (
            "real" if is_real
            else "unreal"
        )
        comma: x + 10,
        bar: "hello"
    }
    """)
    assert p == tilefile.DictNode({
        "foo": tilefile.StaticPythonExpr('"real" if is_real\n'
                               '            else "unreal"'),
        "comma": tilefile.StaticPythonExpr("x + 10"),
        "bar": tilefile.Literal("hello")
    })


def test_value_expr_as_key():
    p = tilefile.parse("""
    {
        (DataID(0, "display")): "Hello"
    }
    """)
    assert p == tilefile.DictNode({
        tilefile.ComputedKey('DataID(0, "display")'):
            tilefile.Literal("Hello")
    })


def test_deferred_line_expr():
    p = tilefile.parse("""
    {
        foo: `node.path() + node.name()`,
        bar: `self.count()`
    }
    """)
    assert p == tilefile.DictNode({
        "foo": tilefile.PythonExpr("node.path() + node.name()"),
        "bar": tilefile.PythonExpr("self.count()"),
    })


def test_deferred_block_expr():
    p = tilefile.parse("""
    {
        foo: ```
        x = 10
        self.text = {"x": x}
        ```
    }
    """)
    assert p == tilefile.DictNode({
        "foo": tilefile.PythonBlock('x = 10\nself.text = {"x": x}'),
    })


def test_parse_jsonpath():
    p = tilefile.parse("""
    {
        foo: $.foo.bar
        bar: $.alfa.bravo
        not_a_path: "$.alfa.bravo"
        robotron: 2000
    }
    """)
    assert p == tilefile.DictNode({
        "robotron": tilefile.Literal(2000),
        "not_a_path": tilefile.Literal("$.alfa.bravo"),
        "foo": tilefile.JsonpathNode("$.foo.bar"),
        "bar": tilefile.JsonpathNode("$.alfa.bravo"),
    })


def test_parse_object():
    p = tilefile.parse("""
    obj surface {
        foo: 100
        bar: "baz"
    }
    """)
    assert p == tilefile.ObjectNode("surface", None, {
        "foo": tilefile.Literal(100),
        "bar": tilefile.Literal("baz")
    })

    p = tilefile.parse("""
    obj surface "root" {
        foo: 100
        bar: "baz"
    }
    """)
    assert p == tilefile.ObjectNode("surface", "root", {
        "foo": tilefile.Literal(100),
        "bar": tilefile.Literal("baz")
    })


def test_parse_models():
    p = tilefile.parse("""
        model {
            rows: $.rows.items()
        }
        """)
    assert p == tilefile.ModelNode(None, {
        "rows": tilefile.JsonpathNode("$.rows.items()")
    })

    p = tilefile.parse("""
        model "attrs" {
            rows: `attrs`
        }
        """)
    assert p == tilefile.ModelNode("attrs", {
        "rows": tilefile.PythonExpr("attrs")
    })


def test_parse_template():
    p = tilefile.parse("""
    template anchors {
        x: 10
        y: "why"
    }
    """)
    assert p == tilefile.ObjectNode("anchors", None, {
        "x": tilefile.Literal(10),
        "y": tilefile.Literal("why")
    }, is_template=True)

    p = tilefile.parse("""
    template rectangle "count" {
        x: 10
        y: "why"
    }
    """)
    assert p == tilefile.ObjectNode("rectangle", "count", {
        "x": tilefile.Literal(10),
        "y": tilefile.Literal("why")
    }, is_template=True)

    with pytest.raises(tilefile.ParserError):
        tilefile.parse("""
        template {
            x: 10
            y: "why"
        }
        """)


def test_object_values():
    p = tilefile.parse("""
    obj surface "root" {
        foo: 100
        title_item: obj text {
            x: 10
            y: 20
        }
        bar: "baz"
    }
    """)
    assert p == tilefile.ObjectNode("surface", "root", {
        "foo": tilefile.Literal(100),
        "title_item": tilefile.ObjectNode("text", None, {
            "x": tilefile.Literal(10),
            "y": tilefile.Literal(20)
        }),
        "bar": tilefile.Literal("baz")
    })


def test_parse_module():
    p = tilefile.parse("""
    ```
    import m
    ```
    
    obj surface "root" {
        foo: m.xy
    }
    """)
    assert p == tilefile.ModuleNode([
        tilefile.PythonBlock("import m"),
        tilefile.ObjectNode("surface", "root", {
            "foo": tilefile.StaticPythonExpr("m.xy")
        })
    ])


def test_env_var():
    assert tilefile.parse("$HOUDINI_TEST") == \
           tilefile.EnvVarNode("HOUDINI_TEST")

    p = tilefile.parse("""
    {
        text: $JOB
        bold: true
    }
    """)
    assert p == tilefile.DictNode({
        "text": tilefile.EnvVarNode("JOB"),
        "bold": tilefile.Literal(True)
    })

    with pytest.raises(tilefile.ParserError):
        tilefile.parse("""
        {
            text: $JOB + 20
            bold: true
        }
        """)


def test_object_items():
    p = tilefile.parse("""
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
    assert p == tilefile.ObjectNode("surface", "root", {
        "x": tilefile.Literal(10),
        "y": tilefile.Literal("why"),
    }, [
        tilefile.ObjectNode("text", None, {
            "html": tilefile.Literal("Hello")
        }),
        tilefile.ObjectNode("foo", None, {}, is_template=True),
        tilefile.ModelNode(None, {
            "rows": tilefile.JsonpathNode("$.attrs")
        })
    ])


def test_combined():
    text = pathlib.Path("../files/nodeinfo.tilefile").read_text()
    p = tilefile.parse(text)
    assert p == tilefile.ObjectNode("surface", "root", {
        "spacing": tilefile.Literal(10),
        "margins": tilefile.Literal(5),
        "title_target": tilefile.Literal("node_header"),
        "cutoff_item": tilefile.Literal("comment_layout"),
        "label": tilefile.PythonExpr("node.name()"),
        "memory": tilefile.JsonpathNode("$.memory.total"),
        "title_item": tilefile.ObjectNode("anchors", None, {
            "spacing": tilefile.Literal(5),
            "fixed_height": tilefile.Literal(28),
            "fill_color": tilefile.StaticPythonExpr("ThemeColor.bg"),
            "on_update": tilefile.PythonBlock(
                'titlebar_icon.icon_name = icon\n'
                'titlebar_path.html = f"{parent_path}/<b>{node_name}</b>"'
            ),
        }, [
            tilefile.ObjectNode("houdini_icon", "titlebar_icon", {
                "fixed_size": tilefile.ListNode([
                    tilefile.Literal(28),
                    tilefile.Literal(28)]
                ),
                "anchor.left": tilefile.DictNode({
                    "to": tilefile.Literal("parent.left"),
                    "spacing": tilefile.Literal(10)
                }),
                "anchor.vcenter": tilefile.Literal("parent.v_center"),
                "icon_name": tilefile.PythonExpr("icon"),
            }),
            tilefile.ObjectNode("controls.text", "titlebar_path", {
                "text_color": tilefile.StaticPythonExpr("ThemeColor.primary"),
                "text_size": tilefile.StaticPythonExpr("TextSize.small"),
                "text_align": tilefile.StaticPythonExpr(
                    "Qt.Align.vcenter | Qt.Align.left"),
                "html": tilefile.PythonExpr(
                    'f"{parent_path}/<b>{node_name}</b>"',
                )
            })
        ])
    }, [
        tilefile.ObjectNode("row", "node_header", {
            "bg_visible": tilefile.Literal(False),
            "margins": tilefile.Literal(0),
            "spacing": tilefile.Literal(5)
        })
    ])


def test_generation():
    text = pathlib.Path("../files/nodeinfo.tilefile").read_text()
    p = tilefile.parse(text)
    assert isinstance(p, tilefile.ModuleNode)
    ctx = build.BuildContext(p, "", "")
    lines = build.moduleSetup(p, ctx)
    print("\n".join(lines))
    assert False
