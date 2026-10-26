"""The look of the view is one set of tokens: the custom properties of the `:root` rule of
`page.html`. Every colour there has a light and a dark value. Every other rule of the
stylesheet, and every `style` attribute the page writes, takes its colours, its type sizes,
its spacing and its corner radii from those tokens (`--text-`, `--space-`, where
`--space-n` is 2n px, and `--radius-`), so a later change moves one token and
not forty literals.

The browser tests beside these (`page/test_view_page_look.py`) keep a shot of each route, and
axe checks each route against WCAG 2.2 AA (`page/test_view_page_keys.py`)."""

import re

from testing.paths import REPO

PAGE = REPO / "features" / "jbus" / "src" / "jbus" / "view" / "page.html"


STYLE = re.search(r"<style>(.*?)</style>", PAGE.read_text(), re.S)[1]


SPACING = re.compile(r"^(margin|padding|gap|row-gap|column-gap)(-[a-z-]+)?$")


COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(")


LENGTH = re.compile(r"(?<![\w-])-?\d*\.?\d+(px|rem|em)\b")


def rules(css):
    """Each innermost rule of the stylesheet: its selector and its declarations, with the
    comments taken out. An `@media` block's own prelude is not a selector, and stays out."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for found in re.finditer(r"([^{}]*)\{([^{}]*)\}", css):
        selector = found[1].strip()
        selector = selector.split("{")[-1].strip()
        if selector.startswith("@media"):
            selector = ""
        declarations = []
        for one in found[2].split(";"):
            if ":" in one:
                prop, value = one.split(":", 1)
                declarations.append((prop.strip(), value.strip()))
        yield selector, declarations


def root():
    """The tokens: each custom property of the `:root` rule, and its value."""
    ((tokens),) = [d for s, d in rules(STYLE) if s == ":root"]
    return dict(tokens)


def offences(where, declarations):
    """What a rule's declarations hold that is not a token: a colour, a font size, a space
    or a radius written as a literal."""
    for prop, value in declarations:
        if prop.startswith("--"):
            continue
        if COLOUR.search(value):
            yield f"{where}: {prop}: {value} (a colour that is not a token)"
        if prop == "font-size" and value != "inherit" and not value.startswith("var(--text-"):
            yield f"{where}: {prop}: {value} (a type size that is not a --text- token)"
        if (SPACING.match(prop) or prop == "border-radius") and LENGTH.search(
            re.sub(r"var\([^)]*\)", "", value)
        ):
            yield f"{where}: {prop}: {value} (a length that is not a token)"


def test_every_colour_token_has_a_light_and_a_dark_value():
    tokens = root()
    colours = {name: value for name, value in tokens.items() if COLOUR.search(value)}
    assert len(colours) >= 15
    one = [n for n, v in colours.items() if not re.fullmatch(r"light-dark\(.+,.+\)", v)]
    assert one == [], "a colour token with one value looks the same in light and in dark"


def test_the_scales_are_tokens_and_each_rule_uses_them():
    tokens = root()
    assert {"--text-sm", "--text-base", "--space-4", "--radius-pill"} <= set(tokens)
    found = []
    for selector, declarations in rules(STYLE):
        if selector.startswith(":root"):
            continue
        assert selector, f"a rule with no selector: {declarations}"
        found += offences(selector, declarations)
    assert found == []


def test_every_style_the_page_writes_inline_uses_the_tokens():
    script = re.sub(r"<style>.*?</style>", "", PAGE.read_text(), flags=re.S)
    inline = re.findall(r'style="([^"]*)"', script)
    assert inline, "the page writes some style inline"
    found = []
    for style in inline:
        declarations = [
            tuple(map(str.strip, d.split(":", 1))) for d in style.split(";") if ":" in d
        ]
        found += offences(f'style="{style}"', declarations)
    assert found == []


def test_every_token_a_rule_names_is_defined():
    tokens = set(root())
    named = set(re.findall(r"var\((--[\w-]+)", PAGE.read_text()))
    assert named - tokens == set()


GROUP = re.compile(r"@(media|supports|container|layer|scope|keyframes)\b")


def stray(css):
    """What the stylesheet holds outside every rule: a closing brace with no rule to close,
    or a declaration between two rules. A browser drops such text together with the rule
    after it, so that rule silently stops applying. Rules sit at the top of the sheet and
    directly inside a grouping at-rule such as `@media` (not `@font-face`, which holds
    declarations), so text is looked at in both places."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    opened, between, found = [], "", []
    for char in css:
        among_rules = not opened or opened[-1]
        if char == "{":
            if among_rules and ";" in between:
                found.append(between.strip())
            opened, between = [*opened, bool(GROUP.match(between.strip()))], ""
        elif char == "}":
            if not opened:
                found.append(f"{between.strip()} }}".strip())
            elif among_rules and between.strip():
                found.append(between.strip())
            opened, between = opened[:-1], ""
        else:
            between += char
    if between.strip():
        found.append(between.strip())
    return found


def test_the_stylesheet_holds_nothing_outside_a_rule():
    assert stray(STYLE) == []


def test_stray_finds_a_declaration_outside_a_rule_at_any_depth():
    media = "@media (max-width: 640px)"
    assert stray(f"a {{ x: 1px; }} {media} {{ b {{ x: 1px; }} c {{ y: 2px; }} }}") == []
    assert stray(f"a {{ x: 1px; }} {media} {{ b {{ x: 1px; }} color: red; c {{ y: 2px; }} }}") == [
        "color: red; c"
    ]
    assert stray(f"a {{ x: 1px; }} {media} {{ b {{ x: 1px; }} color: red; }}") == ["color: red;"]
    assert stray("a { x: 1px; } color: red;") == ["color: red;"]
    assert stray("a { x: 1px; } color: red; b { y: 2px; }") == ["color: red; b"]
    assert stray("a { x: 1px; } }") == ["}"]
    assert stray('@font-face { font-family: "x"; src: url("y"); } a { x: 1px; }') == []
