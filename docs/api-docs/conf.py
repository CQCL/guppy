# Configuration file for the Sphinx documentation builder.
# See https://www.sphinx-doc.org/en/master/usage/configuration.html

import inspect
from types import GenericAlias, UnionType

import guppylang

project = "Guppy Compiler"
copyright = "2024, Quantinuum"
author = "Quantinuum"

extensions = [
    "sphinx.ext.napoleon",
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx.ext.autosummary",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

html_theme = "furo"
html_title = "Guppy compiler development docs"
html_theme_options = {}

html_static_path = ["../_static", "../quantinuum-sphinx/_static"]
templates_path = ["_templates", "../quantinuum-sphinx/_templates"]
html_favicon = "../quantinuum-sphinx/_static/assets/quantinuum_favicon.svg"

autosummary_generate = True

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
}


# add_module_names = False


def _is_type_alias(x):
    """Checks if an object is a type alias.

    Note that this function only catches non-trivial aliases like `IntList = list[int]`
    or `Number = int | float`. Aliases like `MyAlias = int` cannot easily be detected.
    """
    return isinstance(x, GenericAlias | UnionType)


def _find_aliases(module):
    """Finds all type aliases defined in a guppylang module and its submodules.

    Returns a mapping from alias names to the  module in which they are defined.
    """
    aliases = {}
    for name, x in inspect.getmembers(module):
        if _is_type_alias(x):
            aliases[name] = module
        if inspect.ismodule(x) and x.__name__.startswith("guppylang."):
            aliases |= _find_aliases(x)
    return aliases


# Generate a mapping from type aliases to their qualified name to ensure that autodoc
# doesn't unfold them
_aliases = _find_aliases(guppylang)
autodoc_type_aliases = {
    alias: f"~{module.__name__}.{alias}" for alias, module in _aliases.items()
}

# Also create a set of all qualified alias names
_qualified_aliases = {
    f"{module.__name__}.{alias}" for alias, module in _aliases.items()
}


def resolve_type_aliases(app, env, node, contnode):
    """Resolve :class: references to our type aliases as :data: instead.

    When trying to resolve references in type annotations, Sphinx only looks at :class:
    nodes since types are typically classes. However, type aliases are :data: so are
    not found by default. See https://github.com/sphinx-doc/sphinx/issues/10785
    """
    if (
        node["refdomain"] == "py"
        and node["reftype"] == "class"
        and node["reftarget"] in _qualified_aliases
    ):
        ref = app.env.get_domain("py").resolve_xref(
            env, node["refdoc"], app.builder, "data", node["reftarget"], node, contnode
        )
        return ref


def setup(app):
    app.connect("missing-reference", resolve_type_aliases)
