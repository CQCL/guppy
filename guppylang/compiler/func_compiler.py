from typing import TYPE_CHECKING

from guppylang.compiler.cfg_compiler import compile_cfg
from guppylang.compiler.core import CompiledGlobals, DFContainer
from guppylang.hugr_builder.hugr import DFContainingVNode, Hugr, OutPortV
from guppylang.nodes import CheckedNestedFunctionDef
from guppylang.tys.ty import FunctionType, type_to_row

if TYPE_CHECKING:
    from guppylang.definition.function import CheckedFunctionDef


def compile_global_func_def(
    func: "CheckedFunctionDef",
    def_node: DFContainingVNode,
    graph: Hugr,
    globals: CompiledGlobals,
) -> None:
    """Compiles a top-level function definition to Hugr."""
    _, ports = graph.add_input_with_ports(list(func.ty.inputs), def_node)
    cfg_node = graph.add_cfg(def_node, ports)
    compile_cfg(func.cfg, graph, cfg_node, globals)

    # Add output node for the cfg
    graph.add_output(
        inputs=[cfg_node.add_out_port(ty) for ty in type_to_row(func.cfg.output_ty)],
        parent=def_node,
    )


def compile_local_func_def(
    func: CheckedNestedFunctionDef,
    dfg: DFContainer,
    graph: Hugr,
    globals: CompiledGlobals,
) -> OutPortV:
    """Compiles a local (nested) function definition to Hugr."""
    assert func.ty.input_names is not None

    # Pick an order for the captured variables
    captured = list(func.captured.values())

    # Prepend captured variables to the function arguments
    closure_ty = FunctionType(
        [v.ty for v, _ in captured] + list(func.ty.inputs),
        func.ty.output,
        [v.name for v, _ in captured] + list(func.ty.input_names),
    )

    def_node = graph.add_def(closure_ty, dfg.node, func.name, func)
    def_input, input_ports = graph.add_input_with_ports(
        list(closure_ty.inputs), def_node
    )

    # If we have captured variables and the body contains a recursive occurrence of
    # the function itself, then we provide the partially applied function as a local
    # variable
    if len(captured) > 0 and func.name in func.cfg.live_before[func.cfg.entry_bb]:
        loaded = graph.add_load_function(def_node.out_port(0), [], def_node).out_port(0)
        partial = graph.add_partial(
            loaded, [def_input.out_port(i) for i in range(len(captured))], def_node
        )
        input_ports.append(partial.out_port(0))
        func.cfg.input_tys.append(func.ty)
    else:
        # Otherwise, we treat the function like a normal global variable
        from guppylang.definition.function import CompiledFunctionDef

        globals = globals | {
            func.def_id: CompiledFunctionDef(
                func.def_id,
                func.name,
                func,
                func.ty,
                {},
                None,
                func.cfg,
                def_node,
            )
        }

    # Compile the CFG
    cfg_node = graph.add_cfg(def_node, inputs=input_ports)
    compile_cfg(func.cfg, graph, cfg_node, globals)

    # Add output node for the cfg
    graph.add_output(
        inputs=[cfg_node.add_out_port(ty) for ty in type_to_row(func.cfg.output_ty)],
        parent=def_node,
    )

    # Finally, load the function into the local data-flow graph
    loaded = graph.add_load_function(def_node.out_port(0), [], dfg.node).out_port(0)
    if len(captured) > 0:
        loaded = graph.add_partial(
            loaded, [dfg[v] for v, _ in captured], dfg.node
        ).out_port(0)

    return loaded
