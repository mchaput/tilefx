import pytest

from tilefx.file.tilefile import (parse, ParserError, DictNode, ListNode,
                                  LiteralValueNode, StaticPythonExpr, EnvVarNode,
                                  DynamicPython, JsonpathNode, ComputedKey,
                                  ObjectNode, ModelNode, ModuleNode)


def test_empty_file():
    assert parse("") == ModuleNode([])
    assert parse("""
    # Hello there
    # This file is empty
    
    """) == ModuleNode([])


def test_parse_literals():
    assert parse("100") == LiteralValueNode(100)
    assert parse("  -12.455\n\n  ") == LiteralValueNode(-12.455)
    assert parse("true") == LiteralValueNode(True)
    assert parse("\n false \n ") == LiteralValueNode(False)
    assert parse(" null") == LiteralValueNode(None)


def test_empty_dict():
    assert parse("{}") == DictNode({})
    assert parse("\n\n{   \n}\n\n\n") == DictNode({})
    assert parse("{            }") == DictNode({})


def test_json_dict():
    p = parse(' { "alfa": "bravo", "charlie": "delta", "echo": "foxtrot" }')
    assert p == DictNode({
        "alfa": LiteralValueNode("bravo"),
        "charlie": LiteralValueNode("delta"),
        "echo": LiteralValueNode("foxtrot"),
    })

    p = parse("""
    {
        "alfa": "bravo",
        "charlie": "delta",
        "echo": "foxtrot"
    }
    """)
    assert p == DictNode({
        "alfa": LiteralValueNode("bravo"),
        "charlie": LiteralValueNode("delta"),
        "echo": LiteralValueNode("foxtrot"),
    })


def test_json_dict_trailing_comma():
    p = parse("""
    {
        "alfa": "bravo",
        "charlie": "delta",
        "echo": "foxtrot",
    }
    """)
    assert p == DictNode({
        "alfa": LiteralValueNode("bravo"),
        "charlie": LiteralValueNode("delta"),
        "echo": LiteralValueNode("foxtrot"),
    })

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
    assert p == DictNode({
        "alfa": LiteralValueNode("bravo"),
        "charlie": LiteralValueNode("delta"),
        "echo": LiteralValueNode("foxtrot"),
        "golf": LiteralValueNode("hotel"),
    })


def test_dict_of_dicts():
    p = parse("""
    {
        foo: {alfa: "bravo", charlie: "delta"}
        bar: {echo: "foxtrot", golf: "hotel"}
    }
    """)
    assert p == DictNode({
        "foo": DictNode({
            "alfa": LiteralValueNode("bravo"),
            "charlie": LiteralValueNode("delta")
        }),
        "bar": DictNode({
            "echo": LiteralValueNode("foxtrot"),
            "golf": LiteralValueNode("hotel")
        }),
    })


def test_parse_list():
    p = parse("""
    [ "foo", 20, obj hello {}, true]
    """)
    assert p == ListNode([
        LiteralValueNode("foo"),
        LiteralValueNode(20),
        ObjectNode("hello", None, {}),
        LiteralValueNode(True)
    ])

    p = parse("""
    [
        "foo",
        20,
        foo.bar,
        true,
    ]
    """)
    assert p == ListNode([
        LiteralValueNode("foo"),
        LiteralValueNode(20),
        StaticPythonExpr("foo.bar"),
        LiteralValueNode(True)
    ])


def test_value_expr():
    p = parse("""
    {
        foo: x + 5
        bar: (y / 2)
    }
    """)
    assert p == DictNode({
        "foo": StaticPythonExpr("x + 5"),
        "bar": StaticPythonExpr("y / 2")
    })

    with pytest.raises(ParserError):
        parse("""
        {
            foo: 20 100
        }
        """)


def test_multiline_value_expr():
    p = parse("""
    {
        foo: (
            "real" if is_real
            else "unreal"
        )
        comma: x + 10,
        bar: "hello"
    }
    """)
    assert p == DictNode({
        "foo": StaticPythonExpr('"real" if is_real\n'
                               '            else "unreal"'),
        "comma": StaticPythonExpr("x + 10"),
        "bar": LiteralValueNode("hello")
    })


def test_value_expr_as_key():
    p = parse("""
    {
        (DataID(0, "display")): "Hello"
    }
    """)
    assert p == DictNode({
        ComputedKey('DataID(0, "display")'): LiteralValueNode("Hello")
    })


def test_deferred_line_expr():
    p = parse("""
    {
        foo: `node.path() + node.name()`,
        bar: `self.count()`
    }
    """)
    assert p == DictNode({
        "foo": DynamicPython("node.path() + node.name()", "eval"),
        "bar": DynamicPython("self.count()", "eval"),
    })


def test_deferred_block_expr():
    p = parse("""
    {
        foo: ```
        x = 10
        self.text = {"x": x}
        ```
    }
    """)
    assert p == DictNode({
        "foo": DynamicPython(
            '\n        x = 10\n        self.text = {"x": x}\n        ',
            "exec"
        ),
    })


def test_parse_jsonpath():
    p = parse("""
    {
        foo: $.foo.bar
        bar: $.alfa.bravo
        not_a_path: "$.alfa.bravo"
        robotron: 2000
    }
    """)
    assert p == DictNode({
        "robotron": LiteralValueNode(2000),
        "not_a_path": LiteralValueNode("$.alfa.bravo"),
        "foo": JsonpathNode("$.foo.bar"),
        "bar": JsonpathNode("$.alfa.bravo"),
    })


def test_parse_object():
    p = parse("""
    obj surface {
        foo: 100
        bar: "baz"
    }
    """)
    assert p == ObjectNode("surface", None, {
        "foo": LiteralValueNode(100),
        "bar": LiteralValueNode("baz")
    })

    p = parse("""
    obj surface "root" {
        foo: 100
        bar: "baz"
    }
    """)
    assert p == ObjectNode("surface", "root", {
        "foo": LiteralValueNode(100),
        "bar": LiteralValueNode("baz")
    })


def test_parse_models():
    p = parse("""
        model {
            rows: $.rows.items()
        }
        """)
    assert p == ModelNode(None, {
        "rows": JsonpathNode("$.rows.items()")
    })

    p = parse("""
        model "attrs" {
            rows: `attrs`
        }
        """)
    assert p == ModelNode("attrs", {
        "rows": DynamicPython("attrs", "eval")
    })


def test_parse_template():
    p = parse("""
    template anchors {
        x: 10
        y: "why"
    }
    """)
    assert p == ObjectNode("anchors", None, {
        "x": LiteralValueNode(10), "y": LiteralValueNode("why")
    }, is_template=True)

    p = parse("""
    template rectangle "count" {
        x: 10
        y: "why"
    }
    """)
    assert p == ObjectNode("rectangle", "count", {
        "x": LiteralValueNode(10), "y": LiteralValueNode("why")
    }, is_template=True)

    with pytest.raises(ParserError):
        parse("""
        template {
            x: 10
            y: "why"
        }
        """)


def test_object_values():
    p = parse("""
    obj surface "root" {
        foo: 100
        title_item: obj text {
            x: 10
            y: 20
        }
        bar: "baz"
    }
    """)
    assert p == ObjectNode("surface", "root", {
        "foo": LiteralValueNode(100),
        "title_item": ObjectNode("text", None, {
            "x": LiteralValueNode(10),
            "y": LiteralValueNode(20)
        }),
        "bar": LiteralValueNode("baz")
    })


def test_parse_module():
    p = parse("""
    ```
    import m
    ```
    
    obj surface "root" {
        foo: m.xy
    }
    """)
    assert p == ModuleNode([
        DynamicPython("\n    import m\n    ", "exec"),
        ObjectNode("surface", "root", {
            "foo": StaticPythonExpr("m.xy")
        })
    ])


def test_env_var():
    assert parse("$HOUDINI_TEST") == EnvVarNode("HOUDINI_TEST")

    p = parse("""
    {
        text: $JOB
        bold: true
    }
    """)
    assert p == DictNode({
        "text": EnvVarNode("JOB"),
        "bold": LiteralValueNode(True)
    })

    with pytest.raises(ParserError):
        parse("""
        {
            text: $JOB + 20
            bold: true
        }
        """)


def test_object_items():
    p = parse("""
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
    assert p == ObjectNode("surface", "root", {
        "x": LiteralValueNode(10), "y": LiteralValueNode("why"),
    }, [
        ObjectNode("text", None, {
            "html": LiteralValueNode("Hello")
        }),
        ObjectNode("foo", None, {}, is_template=True),
        ModelNode(None, {
            "rows": JsonpathNode("$.attrs")
        })
    ])


def test_combined():
    p = parse("""
    obj Surface "root" {
        spacing: 10
        margins: 5
        # This item sticks to the top of the viewport when the "title_target"
        # item is scrolled offscreen
        title_item: obj Anchors "titlebar" {
            spacing: 8
            fixed_height: 28
            fill_color: ThemeColor.bg
            
            obj Icon "titlebar_icon" {
                fixed_size: [28, 28]
                anchor.left: {to: "parent.left", spacing: 10}
                anchor.vcenter: "parent.v_center"
                icon_name: `icon`
            }
            obj controls.Text "titlebar_path" {
                text_color: ThemeColor.primary
                text_size: TextSize.small
                text_align: Qt.Align.vcenter | Qt.Align.left
                html: `f"{parent_path}/<b>{node_name}</b>"`
            }
                
            on_update: ```
                x = 1
                y = 2
            ```
        }
        title_target: "node_header"
        # When the viewer tries to resize to show everything, it considers all
        # the items *above* this one
        cutoff_item: "comment_layout"
        
        obj Row "node_header" {
            bg_visible: False
            margins: 0
            spacing: 5
            
        }
    }
    """)
    assert p == ObjectNode("Surface", "root", {
        "spacing": LiteralValueNode(10),
        "margins": LiteralValueNode(5),
        "title_target": LiteralValueNode("node_header"),
        "cutoff_item": LiteralValueNode("comment_layout"),
        "title_item": ObjectNode("Anchors", "titlebar", {
            "spacing": LiteralValueNode(8),
            "fixed_height": LiteralValueNode(28),
            "fill_color": StaticPythonExpr("ThemeColor.bg"),
            "on_update": DynamicPython(
                '\n                x = 1\n                y = 2\n            ',
                "exec"
            ),
        }, [
            ObjectNode("Icon", "titlebar_icon", {
                "fixed_size": ListNode([LiteralValueNode(28),
                                        LiteralValueNode(28)]),
                "anchor.left": DictNode({
                    "to": LiteralValueNode("parent.left"),
                    "spacing": LiteralValueNode(10)
                }),
                "anchor.vcenter": LiteralValueNode("parent.v_center"),
                "icon_name": DynamicPython("icon", "eval"),
            }),
            ObjectNode("controls.Text", "titlebar_path", {
                "text_color": StaticPythonExpr("ThemeColor.primary"),
                "text_size": StaticPythonExpr("TextSize.small"),
                "text_align": StaticPythonExpr(
                    "Qt.Align.vcenter | Qt.Align.left"),
                "html": DynamicPython('f"{parent_path}/<b>{node_name}</b>"',
                                   "eval")
            })
        ])

    }, [
        ObjectNode("Row", "node_header", {
            "bg_visible": LiteralValueNode(False),
            "margins": LiteralValueNode(0),
            "spacing": LiteralValueNode(5)
        })
    ])


def test_generation():
    p = parse("""
    obj Surface "root" {
        spacing: 10
        margins: 5
        # This item sticks to the top of the viewport when the "title_target"
        # item is scrolled offscreen
        title_item: obj Anchors "titlebar" {
            spacing: 8
            fixed_height: 28
            fill_color: ThemeColor.bg

            obj Icon "titlebar_icon" {
                fixed_size: [28, 28]
                anchor.left: {to: "parent.left", spacing: 10}
                anchor.vcenter: "parent.v_center"
                icon_name: `icon`
            }
            obj controls.Text "titlebar_path" {
                text_color: ThemeColor.primary
                text_size: TextSize.small
                text_align: Qt.Align.vcenter | Qt.Align.left
                html: `f"{parent_path}/<b>{node_name}</b>"`
            }

            on_update: ```
                x = 1
                y = 2
            ```
        }
        title_target: "node_header"
        # When the viewer tries to resize to show everything, it considers all
        # the items *above* this one
        cutoff_item: "comment_layout"

        obj Row "node_header" {
            bg_visible: False
            margins: 0
            spacing: 5

        }
    }
    """)



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
