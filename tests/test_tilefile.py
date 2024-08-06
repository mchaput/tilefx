from typing import Pattern, Match
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


def matches(expr: Pattern, string: str) -> bool:
    m = expr.match(string)
    return m and m.end() == len(string)


def test_parse_numbers():
    nx = tf.number_expr
    assert matches(nx, "100")
    assert matches(nx, "+100")
    assert matches(nx, "-100")
    assert matches(nx, "-100.")
    assert matches(nx, "-100.1")
    assert matches(nx, "+100.1")
    assert matches(nx, ".100")
    assert matches(nx, ".1234")
    assert matches(nx, "-.1234")
    assert matches(nx, "1e6")
    assert matches(nx, "1e0")
    assert matches(nx, "1.2e6")
    assert matches(nx, "1.2e-6")
    assert matches(nx, "1.2e+6")
    assert not matches(nx, "1.2e6.5")
    assert not matches(nx, "e6")
    assert not matches(nx, "1a5")


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
    [ "foo", 20, def hello {}, true]
    """)
    assert p == tf.ListNode([
        tf.Literal("foo"),
        tf.Literal(20),
        tf.ObjectNode("hello", None, []),
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
        tf.PythonExpr("foo.bar"),
        tf.Literal(True)
    ])


def test_value_expr():
    p = tf.parse("""
    def w "z" {
        foo: x + 5
        bar: (y / 2)
    }
    """)
    assert p == tf.ObjectNode("w", "z", [
        tf.Prop("foo", tf.PythonExpr("x + 5")),
        tf.Prop("bar", tf.PythonExpr("(y / 2)")),
    ])

    with pytest.raises(tf.ParserError):
        tf.parse("""
        def w "z" {
            foo: 20 100
        }
        """)


def test_multiline_value_expr():
    p = tf.parse("""
    def w "z" {
        foo: (
            "real" if is_real
            else "unreal"
        )
        comma: x + 10,
        bar: "hello"
    }
    """)
    assert p == tf.ObjectNode("w", "z", [
        tf.Prop("foo", tf.PythonExpr('( "real" if is_real else "unreal" )')),
        tf.Prop("comma", tf.PythonExpr("x + 10")),
        tf.Prop("bar", tf.Literal("hello"))
    ])


# def test_value_expr_as_key():
#     p = tf.parse("""
#     {
#         (DataID(0, "display")): "Hello"
#     }
#     """)
#     assert p == tf.DictNode({
#         tf.ComputedKey('DataID(0, "display")'):
#             tf.Literal("Hello")
#     })


def test_dynamic_property():
    p = tf.parse("""
    def foo "bar" {
        foo: `node.path() + node.name()`,
        dyn bar: `self.count()`
    }
    """)
    assert p == tf.ObjectNode("foo", "bar", [
        tf.Prop("foo", tf.PythonExpr("node.path() + node.name()")),
        tf.Prop("bar", tf.PythonExpr("self.count()"), dyn=True),
    ])


def test_deferred_property_block():
    p = tf.parse("""
    def foo "bar" {
        dyn foo: ```
        x = 10
        self.text = {"x": x}
        ```
        bar: 10
    }
    """)
    assert p == tf.ObjectNode("foo", "bar", [
        tf.Prop("foo", tf.PythonBlock('x = 10\nself.text = {"x": x}'),
                dyn=True),
        tf.Prop("bar", tf.Literal(10)),
    ])


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
    assert p == tf.ModelNode("foo", [
        tf.Prop("rows", tf.JsonpathNode("$.attrs")),
        tf.Prop("name", tf.JsonpathNode("@.name")),
        tf.Prop("type", tf.JsonpathNode("@.type")),
    ])


def test_parse_object():
    p = tf.parse("""
    def surface {
        foo: 100
        bar: "baz"
    }
    """)
    assert p == tf.ObjectNode("surface", None, [
        tf.Prop("foo", tf.Literal(100)),
        tf.Prop("bar", tf.Literal("baz")),
    ])

    p = tf.parse("""
    def surface "root" {
        foo: 100
        bar: "baz"
    }
    """)
    assert p == tf.ObjectNode("surface", "root", [
        tf.Prop("foo", tf.Literal(100)),
        tf.Prop("bar", tf.Literal("baz")),
    ])

    p = tf.parse("""
    def foo "bar" {
        def text "node_name" { x: 0, y: 5 }
    }
    """)
    assert p == tf.ObjectNode("foo", "bar", [
        tf.ObjectNode("text", "node_name", [
            tf.Prop("x", tf.Literal(0)),
            tf.Prop("y", tf.Literal(5)),
        ])
    ])


def test_parse_single_param():
    p = tf.parse('def foo "bar" {x: y}')
    assert p == tf.ObjectNode("foo", "bar", [
        tf.Prop("x", tf.PythonExpr("y"))
    ])


def test_property_expression():
    p = tf.parse("""
        def foo "bar" {
            x: Qt.AlignLeft | Qt.AlignTop
        }
        """)
    assert p == tf.ObjectNode("foo", "bar", [
        tf.Prop("x", tf.PythonExpr("Qt.AlignLeft | Qt.AlignTop")),
    ])


def test_multiline_property_expression():
    p = tf.parse("""
    def foo "bar" {
        x: foo + (
            1, 2
        )
    }
    """)
    assert p == tf.ObjectNode("foo", "bar", [
        tf.Prop("x", tf.PythonExpr(
            "foo + ( 1, 2 )"
        )),
    ])


def test_numberlike_property_expression():
    with pytest.raises(tf.ParserError):
        tf.parse("""
        def foo "bar" {
            x: 100 + q
        }
        """)

    p = tf.parse("""
    def foo "bar" {
        x: `100 + q`
    }
    """)
    assert p == tf.ObjectNode("foo", "bar", [
        tf.Prop("x", tf.PythonExpr("100 + q")),
    ])


def test_keywordlike_property_expression():
    with pytest.raises(tf.ParserError):
        tf.parse("""
        def foo "bar" {
            x: after + 5
        }
        """)

    p = tf.parse("""
    def foo "bar" {
        x: `after + 5`
    }
    """)
    assert p == tf.ObjectNode("foo", "bar", [
        tf.Prop("x", tf.PythonExpr("after + 5")),
    ])

    # p = tf.parse("""
    # def foo "bar" {
    #     x: foo + (
    #         1, 2
    #     )
    #     x: 100 + q
    #     y: Qt.AlignLeft | Qt.AlignTop
    #     z: after + 5
    # }
    # """)
    # assert p == tf.ObjectNode("foo", "bar", [
    #     tf.Prop("x", tf.PythonExpr("100 + 200")),
    #     tf.Prop("y", tf.PythonExpr("Qt.AlignLeft | Qt.AlignTop")),
    #     tf.Prop("z", tf.PythonExpr("baz + (6,\n2)")),
    # ])


def test_parse_over():
    p = tf.parse("""
    over "root" {
        var x = `env.total + 200`
        foo: 100
        bar: "baz"
    }
    """)
    assert p == tf.OverNode("root", [
        tf.Assign("x", tf.PythonExpr("env.total + 200"), dyn=True),
        tf.Prop("foo", tf.Literal(100)),
        tf.Prop("bar", tf.Literal("baz")),
    ])


def test_parse_models():
    p = tf.parse("""
        model {
            rows: $.rows.items()
        }
        """)
    assert p == tf.ModelNode(None, [
        tf.Prop("rows", tf.JsonpathNode("$.rows.items()")),
    ])

    p = tf.parse("""
        model "attrs" {
            rows: `attrs`
        }
        """)
    assert p == tf.ModelNode("attrs", [
        tf.Prop("rows", tf.PythonExpr("attrs")),
    ])


def test_parse_template():
    p = tf.parse("""
    template anchors {
        x: 10
        y: "why"
    }
    """)
    assert p == tf.ObjectNode("anchors", None, [
        tf.Prop("x", tf.Literal(10)),
        tf.Prop("y", tf.Literal("why")),
    ], is_template=True)

    p = tf.parse("""
    template rectangle "count" {
        x: 10
        y: "why"
    }
    """)
    assert p == tf.ObjectNode("rectangle", "count", [
        tf.Prop("x", tf.Literal(10)),
        tf.Prop("y", tf.Literal("why")),
    ], is_template=True)

    with pytest.raises(tf.ParserError):
        tf.parse("""
        template {
            x: 10
            y: "why"
        }
        """)


def test_object_values():
    p = tf.parse("""
    def surface "root" {
        foo: 100
        title_item: def text {
            x: 10
            y: 20
        }
        bar: "baz"
        baz: {
            w: 50
            z: 100
        }
    }
    """)
    assert p == tf.ObjectNode("surface", "root", [
        tf.Prop("foo", tf.Literal(100)),
        tf.Prop("title_item", tf.ObjectNode("text", None, [
            tf.Prop("x", tf.Literal(10)),
            tf.Prop("y", tf.Literal(20)),
        ])),
        tf.Prop("bar", tf.Literal("baz")),
        tf.Prop("baz", tf.DictNode({
            "w": tf.Literal(50),
            "z": tf.Literal(100)
        }))
    ])


def test_object_docstring():
    p = tf.parse('''
    def foo "bar" {
        doc: """
        Hello
        """
        x: 10
    }
    ''')
    assert p == tf.ObjectNode("foo", "bar", [
        tf.Prop("doc", tf.Literal(
            "\n        Hello\n        "
        )),
        tf.Prop("x", tf.Literal(10)),
    ])


def test_parse_module():
    p = tf.parse("""
    ```
    import m
    ```
    
    def surface "root" {
        foo: m.xy
    }
    """)
    assert p == tf.ModuleNode([
        tf.PythonBlock("import m"),
        tf.ObjectNode("surface", "root", [
            tf.Prop("foo", tf.PythonExpr("m.xy"))
        ])
    ])


def test_parse_module_style():
    p = tf.parse("""
    style "foo" {
        x: 10
        y: 20
    }

    def surface "root" {
        x: 20,
        y: 30
    }
    """)
    assert p == tf.ModuleNode([
        tf.StyleNode("foo", [
            tf.Prop("x", tf.Literal(10)),
            tf.Prop("y", tf.Literal(20))
        ]),
        tf.ObjectNode("surface", "root", [
            tf.Prop("x", tf.Literal(20)),
            tf.Prop("y", tf.Literal(30)),
        ])
    ])


def test_parse_style_in_object():
    p = tf.parse("""
    def surface "root" {
        style : "foo"
        style "foo" {
            x: 10
            y: 20
        }
        z: 30
    }
    """)
    assert p == tf.ObjectNode("surface", "root", [
        tf.Prop("style", tf.Literal("foo")),
        tf.StyleNode("foo", [
            tf.Prop("x", tf.Literal(10)),
            tf.Prop("y", tf.Literal(20)),
        ]),
        tf.Prop("z", tf.Literal(30)),
    ])


def test_parse_object_options():
    p = tf.parse("""
    def foo "bar" (style="baz") {
    
    }
    """)
    assert p == tf.ObjectNode(
        "foo", "bar", [], options={"style": tf.Literal("baz")}
    )

    p = tf.parse("""
    def foo "bar" (x=10, y=20) {

    }
    """)
    assert p == tf.ObjectNode(
        "foo", "bar", [], options={
            "x": tf.Literal(10),
            "y": tf.Literal(20)
        }
    )

    p = tf.parse("""
    model (
        rows=$.attrs.items()
    ) {
        id: this[0]
        value: this[1]
    }
    """)
    assert p == tf.ModelNode(None, [
        tf.Prop("id", tf.PythonExpr("this[0]")),
        tf.Prop("value", tf.PythonExpr("this[1]"))
    ], options={
        "rows": tf.JsonpathNode("$.attrs.items()")
    })

    with pytest.raises(tf.ParserError):
        tf.parse("""
        def foo "bar" (style=model {}) {

        }
        """)


def test_empty_style_name():
    p = tf.parse("""
    def foo "bar" () {

    }
    """)
    assert p == tf.ObjectNode("foo", "bar", [], options={})


def test_parse_style_value():
    p = tf.parse("""
    def surface "root" {
        w:  style {
            x: 10
            y: 20
        }
        z: 30
    }
    """)
    assert p == tf.ObjectNode("surface", "root", items=[
        tf.Prop("w", tf.StyleNode(None, items=[
            tf.Prop("x", tf.Literal(10)),
            tf.Prop("y", tf.Literal(20)),
        ])),
        tf.Prop("z", tf.Literal(30))
    ])


def test_parse_assignment():
    p = tf.parse("""
    var foo = `env.x + 10`
    """)
    assert p == tf.Assign("foo", tf.PythonExpr("env.x + 10"))

    p = tf.parse("""
    let foo = `env.x + 10`
    """)
    assert p == tf.Assign("foo", tf.PythonExpr("env.x + 10"), dyn=False)

    p = tf.parse("""
    var foo =
        `env.x + 10`
    """)
    assert p == tf.Assign("foo", tf.PythonExpr("env.x + 10"))


def test_parse_assignment_in_object():
    p = tf.parse("""
    def foo "bar" {
        let x = {
            "a": "b",
            "c": "d"
        }
        var y = `x[z]`
    }
    """)
    assert p == tf.ObjectNode("foo", "bar", [
        tf.Assign("x", tf.DictNode({
            "a": tf.Literal("b"),
            "c": tf.Literal("d"),
        }), dyn=False),
        tf.Assign("y", tf.PythonExpr("x[z]")),
    ])


def test_var_in_object():
    p = tf.parse("""
    def w "x" {
        var foo = `env.y - 2`
        z: `foo * 3`
    }
    """)
    assert p == tf.ObjectNode("w", "x", [
        tf.Assign("foo", tf.PythonExpr("env.y - 2")),
        tf.Prop("z", tf.PythonExpr("foo * 3")),
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
    def surface "root" {
        x: 10
        y: "why"
        
        def text { html: "Hello" }
        template foo {}
        model {
            rows: $.attrs
        }
    }
    """)
    assert p == tf.ObjectNode("surface", "root", [
        tf.Prop("x", tf.Literal(10)),
        tf.Prop("y", tf.Literal("why")),
        tf.ObjectNode("text", None, [
            tf.Prop("html", tf.Literal("Hello")),
        ]),
        tf.ObjectNode("foo", None, is_template=True),
        tf.ModelNode(None, [
            tf.Prop("rows", tf.JsonpathNode("$.attrs")),
        ])
    ])


def test_parse_callback():
    p = tf.parse("""
    def checkbox "show_comment" {
        on_state_change: fn ```
            env.setOutputIndex(self.currentIndex())
        ```
    }
    """)
    assert p == tf.ObjectNode("checkbox", "show_comment", [
        tf.Prop("on_state_change",
                tf.FuncNode(
                    tf.PythonBlock("env.setOutputIndex(self.currentIndex())")
                ))
    ])


def test_take_tuple_aingle_nobrackets():
    assert tf.take_tuple(tf.Parser("foo")) == [
        tf.Token(tf.Kind.name, "foo", 0, 3)
    ]


def test_take_tuple_pair_nobrackets():
    assert tf.take_tuple(tf.Parser("foo, bar")) == [
        tf.Token(tf.Kind.name, "foo", 0, 3),
        tf.Token(tf.Kind.name, "bar", 5, 8)
    ]


def test_take_tuple_single_brackets():
    assert tf.take_tuple(tf.Parser("(foo)")) == [
        tf.Token(tf.Kind.name, "foo", 1, 4)
    ]


def test_take_tuple_pair_brackets():
    assert tf.take_tuple(tf.Parser("(foo, bar)")) == [
        tf.Token(tf.Kind.name, "foo", 1, 4),
        tf.Token(tf.Kind.name, "bar", 6, 9),
    ]


def test_take_tuple_trailing_comma_nobrackets():
    assert tf.take_tuple(tf.Parser("foo, bar,")) == [
        tf.Token(tf.Kind.name, "foo", 0, 3),
        tf.Token(tf.Kind.name, "bar", 5, 8)
    ]


def test_take_tuple_trailing_comma_brackets():
    assert tf.take_tuple(tf.Parser("(foo, bar, )")) == [
        tf.Token(tf.Kind.name, "foo", 1, 4),
        tf.Token(tf.Kind.name, "bar", 6, 9),
    ]


def test_take_tuple_required_end():
    assert tf.take_tuple(tf.Parser("foo, bar in")) == [
        tf.Token(tf.Kind.name, "foo", 0, 3),
        tf.Token(tf.Kind.name, "bar", 5, 8)
    ]


def test_take_tuple_empty_nobrackets():
    with pytest.raises(tf.ParserError):
        tf.take_tuple(tf.Parser(""))

    with pytest.raises(tf.ParserError):
        tf.take_tuple(tf.Parser("in"))


def test_take_tuple_empty_brackets():
    assert tf.take_tuple(tf.Parser("() in"), end_kind=tf.Kind.in_) == []


def test_take_tuple_nested_nobrackets():
    assert tf.take_tuple(tf.Parser("foo, (bar, baz)")) == [
        tf.Token(tf.Kind.name, "foo", 0, 3),
        [
            tf.Token(tf.Kind.name, "bar", 6, 9),
            tf.Token(tf.Kind.name, "baz", 11, 14),
        ]
    ]

    assert tf.take_tuple(tf.Parser("foo, (bar, baz), qux")) == [
        tf.Token(tf.Kind.name, "foo", 0, 3),
        [
            tf.Token(tf.Kind.name, "bar", 6, 9),
            tf.Token(tf.Kind.name, "baz", 11, 14),
        ],
        tf.Token(tf.Kind.name, "qux", 17, 20),
    ]


def test_take_tuple_nested_brackets():
    assert tf.take_tuple(tf.Parser("(foo, (bar, baz))")) == [
        tf.Token(tf.Kind.name, "foo", 1, 4),
        [
            tf.Token(tf.Kind.name, "bar", 7, 10),
            tf.Token(tf.Kind.name, "baz", 12, 15),
        ]
    ]

    assert tf.take_tuple(tf.Parser("(foo, (bar, baz), qux)")) == [
        tf.Token(tf.Kind.name, "foo", 1, 4),
        [
            tf.Token(tf.Kind.name, "bar", 7, 10),
            tf.Token(tf.Kind.name, "baz", 12, 15),
        ],
        tf.Token(tf.Kind.name, "qux", 18, 21),
    ]


def test_for_each_name():
    p = tf.parse("""
    def a {
        for b in c def e {
            x: 10
            label: b
        }
    }
    """)
    assert p == tf.ObjectNode("a", None, [
        tf.ForEachNode("(b)", tf.PythonExpr("c"), tf.ObjectNode("e", None, [
            tf.Prop("x", tf.Literal(10)),
            tf.Prop("label", tf.PythonExpr("b")),
        ], is_template=True))
    ])


def test_for_each_multi():
    p = tf.parse("""
    def a {
        for q, r in c def e {
            x: 10
            label: b
        }
    }
    """)
    assert p == tf.ObjectNode("a", None, [
        tf.ForEachNode("(q, r)", tf.PythonExpr("c"), tf.ObjectNode("e", None, [
            tf.Prop("x", tf.Literal(10)),
            tf.Prop("label", tf.PythonExpr("b")),
        ], is_template=True))
    ])


def test_for_each_dotted_name():
    p = tf.parse("""
    def a {
        for b in c.q.r def e {
            x: 10
            label: b
        }
    }
    """)
    assert p == tf.ObjectNode("a", None, [
        tf.ForEachNode("(b)", tf.PythonExpr("c.q.r"), tf.ObjectNode("e", None, [
            tf.Prop("x", tf.Literal(10)),
            tf.Prop("label", tf.PythonExpr("b")),
        ], is_template=True))
    ])


def test_for_each_expr():
    p = tf.parse("""
    def a {
        for b in `c.items()` def e {
            x: 10
            label: b
        }
    }
    """)
    assert p == tf.ObjectNode("a", None, [
        tf.ForEachNode(
            "(b)", tf.PythonExpr("c.items()"),
            tf.ObjectNode("e", None, [
                tf.Prop("x", tf.Literal(10)),
                tf.Prop("label", tf.PythonExpr("b")),
            ], is_template=True)
        )
    ])


def test_for_each_list():
    p = tf.parse("""
        def a {
            q: 50
            r: 100
            for b in ["aaa", "bbb"] def e {
                x: 10
                label: b
            }
        }
        """)
    assert p == tf.ObjectNode("a", None, [
        tf.Prop("q", tf.Literal(50)),
        tf.Prop("r", tf.Literal(100)),
        tf.ForEachNode(
            "(b)",
            tf.ListNode([tf.Literal("aaa"), tf.Literal("bbb")]),
            tf.ObjectNode("e", None, [
                tf.Prop("x", tf.Literal(10)),
                tf.Prop("label", tf.PythonExpr("b")),
            ], is_template=True)
        )
    ])


def test_parse_object_insertion():
    p = tf.parse("""
    over "root" {
        before "bar" def text "baz" { x: 30 }
    }
    """)
    assert p == tf.OverNode("root", [
        tf.InsertionNode(tf.Kind.before, "bar", tf.ObjectNode("text", "baz", [
            tf.Prop("x", tf.Literal(30))
        ]))
    ])

    p = tf.parse("""
    over "root" {
        after "bar" def text "baz" { x: 30 }
    }
    """)
    assert p == tf.OverNode("root", [
        tf.InsertionNode(tf.Kind.after, "bar", tf.ObjectNode("text", "baz", [
            tf.Prop("x", tf.Literal(30))
        ]))
    ])

    p = tf.parse("""
    over "root" {
        insert 1 def text "baz" { x: 30 }
    }
    """)
    assert p == tf.OverNode("root", [
        tf.InsertionNode(tf.Kind.insert, 1, tf.ObjectNode("text", "baz", [
            tf.Prop("x", tf.Literal(30))
        ]))
    ])

    # Insert must be followed by a number
    with pytest.raises(tf.ParserError):
        tf.parse("""
        over "root" {
            insert "foo" def text "baz" { x: 30 }
        }
        """)

    # Before must be followed by a string
    with pytest.raises(tf.ParserError):
        tf.parse("""
        over "root" {
            before 5 def text "baz" { x: 30 }
        }
        """)


def test_big_file():
    text = pathlib.Path("../files/node_info.tilefile").read_text()
    p = tf.parse(text)


# def test_generation():
#     text = pathlib.Path("../files/nodeinfo.tilefile").read_text()
#     p = tf.parse(text)
#     assert isinstance(p, tf.ModuleNode)
#     ctx = build.BuildContext(p, "", "")
#     lines = build.moduleSetup(p, ctx)
#     print("\n".join(lines))
#     assert False
