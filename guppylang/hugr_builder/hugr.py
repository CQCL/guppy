import itertools
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

import networkx as nx  # type: ignore[import-untyped]
from hugr import node_port
from hugr.serialization import ops, tys
from hugr.serialization import serial_hugr as raw
from hugr.serialization.ops import OpType

from guppylang.ast_util import AstNode, get_file, get_line_offset, line_col
from guppylang.tys.subst import Inst
from guppylang.tys.ty import (
    FunctionType,
    StructType,
    SumType,
    TupleType,
    Type,
    TypeRow,
    row_to_type,
    rows_to_hugr,
    type_to_row,
)

NodeIdx = int
PortOffset = int


@dataclass(frozen=True)
class Port(ABC):
    """Base class for ports on nodes."""

    node: "Node"
    offset: PortOffset | None


class InPort(Port, ABC):
    """Base class for a port that incoming wires connect to."""


class OutPort(Port, ABC):
    """Base class for a port that outgoing wires come from."""


@dataclass(frozen=True)
class InPortV(InPort):
    """A typed value input port."""

    ty: Type
    offset: PortOffset


@dataclass(frozen=True)
class OutPortV(OutPort):
    """A typed value output port."""

    ty: Type
    offset: PortOffset


@dataclass(frozen=True)
class InPortCF(InPort):
    """A control-flow input port."""

    # Control flow inputs are unordered so no port offset is needed
    offset: None = field(default=None, init=False)


class OutPortCF(OutPort):
    """A control-flow output port."""


class DummyOp(OpType):
    """A dummy Hugr op that is replaced with a call to a dummy function declaration
    during serialisation.

    This is a placeholder for ops that aren't yet available in Hugr.
    """

    root: str  # type: ignore[assignment]

    @property
    def name(self) -> str:
        """The name of the dummy op."""
        return self.root


Edge = tuple[OutPort, InPort]

TypeList = list[Type]


@dataclass
class Node(ABC):
    """Base class for a node in the graph.

    Has a number of input and output ports and an associated op type.
    """

    idx: NodeIdx
    op: ops.OpType
    parent: Optional["Node"]
    meta_data: dict[str, Any]

    @property
    @abstractmethod
    def num_in_ports(self) -> int:
        """The number of input ports on this node."""

    @property
    @abstractmethod
    def num_out_ports(self) -> int:
        """The number of output ports on this node."""

    @abstractmethod
    def in_port(self, offset: PortOffset | None) -> InPort:
        """Returns the input port at the given offset."""

    @abstractmethod
    def out_port(self, offset: PortOffset | None) -> OutPort:
        """Returns the output port at the given offset."""

    def update_op(self) -> None:  # noqa: B027
        """Updates the op type associated with this node with additional information.

        This should be called before serialisation.
        """

    @property
    def in_ports(self) -> Iterator[InPort]:
        """Returns an iterator over all input ports from left to right."""
        return (self.in_port(i) for i in range(self.num_in_ports))

    @property
    def out_ports(self) -> Iterator[OutPort]:
        """Returns an iterator over all output ports from left to right."""
        return (self.out_port(i) for i in range(self.num_out_ports))


@dataclass
class VNode(Node):
    """A node with typed value ports."""

    in_port_types: TypeList
    out_port_types: TypeList

    @property
    def num_in_ports(self) -> int:
        """The number of input ports on this node."""
        return len(self.in_port_types)

    @property
    def num_out_ports(self) -> int:
        """The number of output ports on this node."""
        return len(self.out_port_types)

    def add_in_port(self, ty: Type) -> InPortV:
        """Adds an input port at the end of the node and returns the port."""
        p = InPortV(self, self.num_in_ports, ty)
        self.in_port_types.append(ty)
        return p

    def add_out_port(self, ty: Type) -> OutPortV:
        """Adds an output port at the end of the node and returns the port."""
        p = OutPortV(self, self.num_out_ports, ty)
        self.out_port_types.append(ty)
        return p

    def in_port(self, offset: PortOffset | None) -> InPortV:
        """Returns the input port at the given offset."""
        assert offset is not None
        assert offset < self.num_in_ports
        assert offset != -1, "Cannot get the port of an order edge"
        return InPortV(self, offset, self.in_port_types[offset])

    def out_port(self, offset: PortOffset | None) -> OutPortV:
        """Returns the output port at the given offset."""
        assert offset is not None
        assert offset < self.num_out_ports
        assert offset != -1, "Cannot get the port of an order edge"
        return OutPortV(self, offset, self.out_port_types[offset])

    @property
    def in_ports(self) -> Iterator[InPortV]:
        """Returns an iterator over all input ports from left to right."""
        return (self.in_port(i) for i in range(self.num_in_ports))

    @property
    def out_ports(self) -> Iterator[OutPortV]:
        """Returns an iterator over all output ports from left to right."""
        return (self.out_port(i) for i in range(self.num_out_ports))

    def update_op(self) -> None:
        """Updates the operation associated with this node with type information.

        Feeds type information from the in- and out-ports to the operation class to
        update signature information. This function must be called before serialisation.
        """
        # We can't call `to_hugr()` on polymorphic function types, so we have to skip
        # ops that have connected `Function` edges.
        has_poly_func_edge = isinstance(
            self.op.root, ops.FuncDecl | ops.FuncDefn | ops.Call | ops.LoadFunction
        )
        if isinstance(self.op.root, ops.BaseOp) and not has_poly_func_edge:
            in_types = [t.to_hugr() for t in self.in_port_types]
            out_types = [t.to_hugr() for t in self.out_port_types]
            self.op.root.insert_port_types(in_types, out_types)
        super().update_op()


class CFNode(Node):
    """A node in a control-flow graph.

    Compared to value nodes, the ports on this node are not typed since they correspond
    to control-flow instead of data-flow.
    """

    _num_out_ports: int = 0

    @property
    def num_in_ports(self) -> int:
        """The number of input ports on this node."""
        return 0

    @property
    def num_out_ports(self) -> int:
        """The number of output ports on this node."""
        return self._num_out_ports

    def add_out_port(self) -> OutPortCF:
        """Adds an output port at the end of the node and returns the port."""
        p = OutPortCF(self, self.num_out_ports)
        self._num_out_ports += 1
        return p

    def in_port(self, offset: PortOffset | None) -> InPortCF:
        assert offset is None
        return InPortCF(self)

    def out_port(self, offset: PortOffset | None) -> OutPortCF:
        """Returns the output port at the given offset."""
        assert offset is not None
        assert offset < self.num_out_ports
        return OutPortCF(self, offset)

    def update_op(self) -> None:
        super().update_op()


class DFContainingNode(Node, ABC):
    """Base class for a node whose children form a dataflow graph.

    Compared to a normal node, this node tracks the `Input` and `Output` nodes of its
    child DFG which is required to compute the operation signature.
    """

    input_child: Optional["VNode"] = None  # Input Node for the child dataflow graph
    output_child: Optional["VNode"] = None  # Output Node for the child dataflow graph

    def update_op(self) -> None:
        """Updates the operation associated with this node with type information.

        Feeds type information from the signature of the contained dataflow graph to
        the operation class to. This function must be called before serialisation.
        """
        assert self.input_child is not None
        assert self.output_child is not None
        assert isinstance(self.op.root, ops.BaseOp)
        # Input and output node may have extra order edges connected, so we filter
        # `None`s here
        ins = [ty.to_hugr() for ty in self.input_child.out_port_types]
        outs = [ty.to_hugr() for ty in self.output_child.in_port_types]
        self.op.root.insert_child_dfg_signature(inputs=ins, outputs=outs)
        super().update_op()


class DFContainingVNode(VNode, DFContainingNode):
    """A value node whose children form a dataflow graph"""


class BlockNode(DFContainingNode, CFNode):
    """A `Block` node representing a basic block."""


OrderEdge = tuple["Node", "Node"]
ORDER_EDGE_KEY = (-1, -1)

UNDEFINED: node_port.NodeIdx = -1


class Hugr:
    """Hierarchical unified graph representation."""

    name: str
    root: VNode
    _graph: nx.MultiDiGraph  # TODO: We probably don't need networkx.
    _children: dict[NodeIdx, list[Node]]
    _default_parent: Node | None

    def __init__(self, name: str | None = None, file: str | None = None) -> None:
        """Creates a new Hugr."""
        self.name = name or "Unnamed"
        self._default_parent = None
        self._graph = nx.MultiDiGraph()
        self._children = {-1: []}
        meta_data: dict[str, Any] = {"name": name}
        if file is not None:
            meta_data["di"] = {"file": file}
        self.root = self.add_node(
            op=ops.OpType(ops.Module(parent=UNDEFINED)),
            meta_data=meta_data,
            parent=None,
        )

    @contextmanager
    def parent(self, parent: Node) -> Iterator[None]:
        """Context manager to set a default parent for adding new nodes."""
        old_default = self._default_parent
        self._default_parent = parent
        yield
        self._default_parent = old_default

    def _insert_node(self, node: Node, inputs: list[OutPortV] | None = None) -> None:
        """Helper method to insert a node into the graph datastructure."""
        self._graph.add_node(node.idx, data=node)
        self._children[node.idx] = []
        self._children[node.parent.idx if node.parent else -1].append(node)
        if inputs is not None:
            for i, port in enumerate(inputs):
                self.add_edge(port, node.in_port(i))

    def add_node(
        self,
        op: ops.OpType,
        input_types: TypeList | None = None,
        output_types: TypeList | None = None,
        parent: Node | None = None,
        inputs: list[OutPortV] | None = None,
        debug: AstNode | None = None,
        meta_data: dict[str, Any] | None = None,
    ) -> VNode:
        """Helper method to add a generic value node to the graph."""
        input_types = input_types or []
        output_types = output_types or []
        parent = parent or self._default_parent
        node = VNode(
            idx=self._graph.number_of_nodes(),
            op=op,
            parent=parent,
            in_port_types=[p.ty for p in inputs] if inputs is not None else input_types,
            out_port_types=output_types,
            meta_data=(meta_data or {}) | debug_metadata(debug),
        )
        self._insert_node(node, inputs)
        return node

    def _add_dfg_node(
        self,
        op: ops.OpType,
        input_types: TypeList | None = None,
        output_types: TypeList | None = None,
        parent: Node | None = None,
        inputs: list[OutPortV] | None = None,
        debug: AstNode | None = None,
        meta_data: dict[str, Any] | None = None,
    ) -> DFContainingVNode:
        """Helper method to add a generic dataflow containing value node to the
        graph."""
        input_types = input_types or []
        output_types = output_types or []
        parent = parent or self._default_parent
        node = DFContainingVNode(
            idx=self._graph.number_of_nodes(),
            op=op,
            parent=parent,
            in_port_types=[p.ty for p in inputs] if inputs is not None else input_types,
            out_port_types=output_types,
            meta_data=(meta_data or {}) | debug_metadata(debug),
        )
        self._insert_node(node, inputs)
        return node

    def set_root_name(self, name: str) -> VNode:
        """Sets the name of the root node."""
        self.root.meta_data["name"] = name
        return self.root

    def add_constant(
        self, value: ops.Value, ty: Type, parent: Node | None = None
    ) -> VNode:
        """Adds a constant node holding a given value to the graph."""
        return self.add_node(
            ops.OpType(ops.Const(v=value, parent=UNDEFINED)), [], [ty], parent, None
        )

    def add_input(
        self, output_tys: TypeList | None = None, parent: Node | None = None
    ) -> VNode:
        """Adds an `Input` node to the graph."""
        parent = parent or self._default_parent
        node = self.add_node(
            ops.OpType(ops.Input(parent=UNDEFINED)), [], output_tys, parent
        )
        if isinstance(parent, DFContainingNode):
            parent.input_child = node
        return node

    def add_input_with_ports(
        self, output_tys: Sequence[Type], parent: Node | None = None
    ) -> tuple[VNode, list[OutPortV]]:
        """Adds an `Input` node to the graph."""
        node = self.add_input(None, parent)
        ports = [node.add_out_port(ty) for ty in output_tys]
        return node, ports

    def add_output(
        self,
        inputs: list[OutPortV] | None = None,
        input_tys: TypeList | None = None,
        parent: Node | None = None,
    ) -> VNode:
        """Adds an `Output` node to the graph."""
        parent = parent or self._default_parent
        node = self.add_node(
            ops.OpType(ops.Output(parent=UNDEFINED)), input_tys, [], parent, inputs
        )
        if isinstance(parent, DFContainingNode):
            parent.output_child = node
        return node

    def add_block(self, parent: Node | None, num_successors: int = 0) -> BlockNode:
        """Adds a `Block` node to the graph."""
        node = BlockNode(
            idx=self._graph.number_of_nodes(),
            op=ops.OpType(ops.DataflowBlock(parent=UNDEFINED, sum_rows=[])),
            parent=parent,
            meta_data={},
        )
        self._insert_node(node)
        for _ in range(num_successors):
            node.add_out_port()
        return node

    def add_exit(self, output_tys: TypeList, parent: Node) -> CFNode:
        """Adds an `Exit` node to the graph."""
        outputs = [ty.to_hugr() for ty in output_tys]
        node = CFNode(
            idx=self._graph.number_of_nodes(),
            op=ops.OpType(ops.ExitBlock(cfg_outputs=outputs, parent=UNDEFINED)),
            parent=parent,
            meta_data={},
        )
        self._insert_node(node)
        return node

    def add_dfg(self, parent: Node) -> DFContainingVNode:
        """Adds a nested dataflow `DFG` node to the graph."""
        return self._add_dfg_node(ops.OpType(ops.DFG(parent=UNDEFINED)), [], [], parent)

    def add_case(self, parent: Node) -> DFContainingVNode:
        """Adds a `Case` node to the graph."""
        return self._add_dfg_node(
            ops.OpType(ops.Case(parent=UNDEFINED)), [], [], parent
        )

    def add_cfg(self, parent: Node, inputs: list[OutPortV]) -> VNode:
        """Adds a nested control-flow `CFG` node to the graph."""
        return self.add_node(
            ops.OpType(ops.CFG(parent=UNDEFINED)), [], [], parent, inputs
        )

    def add_conditional(
        self,
        cond_input: OutPortV,
        inputs: list[OutPortV],
        parent: Node | None = None,
    ) -> VNode:
        """Adds a `Conditional` node to the graph."""
        inputs = [cond_input, *inputs]
        return self.add_node(
            ops.OpType(ops.Conditional(sum_rows=[], parent=UNDEFINED)),
            None,
            None,
            parent,
            inputs,
        )

    def add_tail_loop(
        self, inputs: list[OutPortV], parent: Node | None = None
    ) -> DFContainingVNode:
        """Adds a `TailLoop` node to the graph."""
        return self._add_dfg_node(
            ops.OpType(ops.TailLoop(parent=UNDEFINED)), None, None, parent, inputs
        )

    def add_make_tuple(
        self, inputs: list[OutPortV], parent: Node | None = None
    ) -> VNode:
        """Adds a `MakeTuple` node to the graph."""
        ty = TupleType([port.ty for port in inputs])
        return self.add_node(
            ops.OpType(ops.MakeTuple(parent=UNDEFINED)), None, [ty], parent, inputs
        )

    def add_unpack_tuple(
        self, input_tuple: OutPortV, parent: Node | None = None
    ) -> VNode:
        """Adds an `UnpackTuple` node to the graph."""
        match input_tuple.ty:
            case TupleType(element_types=elems):
                tys = list(elems)
            case StructType(fields=fields):
                tys = [field.ty for field in fields]
            case ty:
                raise AssertionError(f"Cannot unpack `{ty}`")
        return self.add_node(
            ops.OpType(ops.UnpackTuple(parent=UNDEFINED)),
            None,
            tys,
            parent,
            [input_tuple],
        )

    def add_tag(
        self,
        variants: Sequence[TypeRow],
        tag: int,
        inputs: list[OutPortV],
        parent: Node | None = None,
    ) -> VNode:
        """Adds a `Tag` node to the graph."""
        assert all(inp.ty == ty for inp, ty in zip(inputs, variants[tag], strict=True))
        hugr_variants = rows_to_hugr(variants)
        out_ty = SumType([row_to_type(row) for row in variants])
        return self.add_node(
            ops.OpType(ops.Tag(tag=tag, variants=hugr_variants, parent=UNDEFINED)),
            None,
            [out_ty],
            parent,
            inputs,
        )

    def add_load_constant(
        self, const_port: OutPortV, parent: Node | None = None
    ) -> VNode:
        """Adds a `LoadConstant` node to the graph."""
        return self.add_node(
            ops.OpType(
                ops.LoadConstant(datatype=const_port.ty.to_hugr(), parent=UNDEFINED)
            ),
            None,
            [const_port.ty],
            parent,
            [const_port],
        )

    def add_load_function(
        self, def_port: OutPortV, inst: Inst, parent: Node | None = None
    ) -> VNode:
        """Adds a `LoadFunction` node to the graph."""
        assert isinstance(def_port.ty, FunctionType)
        assert len(def_port.ty.params) == len(inst)
        instantiation = def_port.ty.instantiate(inst)
        op = ops.LoadFunction(
            func_sig=def_port.ty.to_hugr_poly(),
            type_args=[arg.to_hugr() for arg in inst],
            signature=tys.FunctionType(input=[], output=[instantiation.to_hugr()]),
            parent=UNDEFINED,
        )
        return self.add_node(ops.OpType(op), None, [instantiation], parent, [def_port])

    def add_call(
        self,
        def_port: OutPortV,
        args: list[OutPortV],
        inst: Inst,
        parent: Node | None = None,
    ) -> VNode:
        """Adds a `Call` node to the graph."""
        assert isinstance(def_port.ty, FunctionType)
        instantiation = def_port.ty.instantiate(inst)
        op = ops.Call(
            func_sig=def_port.ty.to_hugr_poly(),
            type_args=[arg.to_hugr() for arg in inst],
            instantiation=instantiation.to_hugr().root,
            parent=UNDEFINED,
        )
        return self.add_node(
            ops.OpType(op),
            None,
            list(type_to_row(instantiation.output)),
            parent,
            [*args, def_port],
        )

    def add_indirect_call(
        self, fun_port: OutPortV, args: list[OutPortV], parent: Node | None = None
    ) -> VNode:
        """Adds an `IndirectCall` node to the graph."""
        assert isinstance(fun_port.ty, FunctionType)

        return self.add_node(
            ops.OpType(ops.CallIndirect(parent=UNDEFINED)),
            None,
            list(type_to_row(fun_port.ty.output)),
            parent,
            [fun_port, *args],
        )

    def add_partial(
        self, def_port: OutPortV, inputs: list[OutPortV], parent: Node | None = None
    ) -> VNode:
        """Adds a `Partial` evaluation node to the graph."""
        assert isinstance(def_port.ty, FunctionType)
        assert len(def_port.ty.inputs) >= len(inputs)
        assert [p.ty.to_hugr() for p in inputs] == [
            ty.to_hugr() for ty in def_port.ty.inputs[: len(inputs)]
        ]
        new_ty = FunctionType(
            def_port.ty.inputs[len(inputs) :],
            def_port.ty.output,
            def_port.ty.input_names[len(inputs) :]
            if def_port.ty.input_names is not None
            else None,
        )
        return self.add_node(
            DummyOp("partial"), None, [new_ty], parent, [*inputs, def_port]
        )

    def add_def(
        self,
        fun_ty: FunctionType,
        parent: Node | None,
        name: str,
        debug: AstNode | None = None,
    ) -> DFContainingVNode:
        """Adds a `FucnDefn` node to the graph."""
        op = ops.FuncDefn(name=name, signature=fun_ty.to_hugr_poly(), parent=UNDEFINED)
        return self._add_dfg_node(ops.OpType(op), [], [fun_ty], parent, None, debug)

    def add_declare(self, fun_ty: FunctionType, parent: Node, name: str) -> VNode:
        """Adds a `FuncDecl` node to the graph."""
        op = ops.FuncDecl(name=name, signature=fun_ty.to_hugr_poly(), parent=UNDEFINED)
        return self.add_node(ops.OpType(op), [], [fun_ty], parent, None)

    def add_edge(self, src_port: OutPort, tgt_port: InPort) -> None:
        """Adds an edge between two ports."""
        if isinstance(src_port, OutPortV) or isinstance(tgt_port, InPortV):
            assert isinstance(src_port, OutPortV)
            assert isinstance(tgt_port, InPortV)
            assert src_port.ty == tgt_port.ty
        else:
            assert isinstance(src_port, OutPortCF)
            assert isinstance(tgt_port, InPortCF)
        self._graph.add_edge(
            src_port.node.idx, tgt_port.node.idx, key=(src_port.offset, tgt_port.offset)
        )

    def add_order_edge(self, src: Node, tgt: Node) -> None:
        """Adds a order-edge between two nodes."""
        self._graph.add_edge(src.idx, tgt.idx, key=ORDER_EDGE_KEY)

    def nodes(self) -> Iterator[Node]:
        """Returns an iterator over all nodes in the graph."""
        return (n["data"] for n in self._graph.nodes.values())

    def get_node(self, idx: int) -> Node:
        """Returns the node corresponding to given index."""
        return self._graph.nodes[idx]["data"]  # type: ignore[no-any-return]

    def children(self, node: Node) -> list[Node]:
        """Returns list of a node's immediate children in the hierarchy."""
        return self._children[node.idx]

    def top_level_nodes(self) -> list[Node]:
        """Returns list of nodes at the top level of the hierarchy.

        These are nodes that do not have a parent. Usually this will just
        be the `Root` node.
        """
        return self._children[-1]

    def edges(self) -> Iterator[Edge]:
        """Returns an iterator over all edges in the graph."""
        return (
            self._to_edge(*e)
            for e in self._graph.edges(keys=True)
            if e[2] != ORDER_EDGE_KEY
        )

    def order_edges(self) -> Iterator[OrderEdge]:
        """Returns an iterator over all order-edges in the graph."""
        return (
            (self.get_node(e[0]), self.get_node(e[1]))
            for e in self._graph.edges(keys=True)
            if e[2] == ORDER_EDGE_KEY
        )

    def in_edges(self, port: InPort) -> Iterator[Edge]:
        """Returns an iterator over all edges connected to a given in-port."""
        for e in self._graph.in_edges(port.node.idx, keys=True):
            if e[2] == ORDER_EDGE_KEY:
                continue
            src, tgt = self._to_edge(*e)
            if tgt.offset == port.offset:
                yield src, tgt

    def out_edges(self, port: OutPort) -> Iterator[Edge]:
        """Returns an iterator over all edges originating from a given out-port."""
        for e in self._graph.out_edges(port.node.idx, keys=True):
            if e[2] == ORDER_EDGE_KEY:
                continue
            src, tgt = self._to_edge(*e)
            if src.offset == port.offset:
                yield src, tgt

    def order_successors(self, node: Node) -> Iterator[Node]:
        """Returns an iterator over all nodes that this node connects to via an
        order edge."""
        for _src, tgt, key in self._graph.out_edges(node.idx, keys=True):
            if key == ORDER_EDGE_KEY:
                yield tgt

    def order_predecessors(self, node: Node) -> Iterator[Node]:
        """Returns an iterator over all nodes that are connected to this node via an
        order edge."""
        for src, _tgt, key in self._graph.in_edges(node.idx, keys=True):
            if key == ORDER_EDGE_KEY:
                yield src

    def _to_edge(self, src: int, tgt: int, key: tuple[int, int]) -> Edge:
        src_node = self.get_node(src)
        tgt_node = self.get_node(tgt)
        return src_node.out_port(key[0]), tgt_node.in_port(key[1])

    def remove_edge(self, src_port: OutPort, tgt_port: InPort) -> None:
        """Removes an edge from the graph."""
        self._graph.remove_edge(
            src_port.node.idx, tgt_port.node.idx, key=(src_port.offset, tgt_port.offset)
        )

    def remove_dummy_nodes(self) -> "Hugr":
        """Replaces dummy ops with external function calls."""
        if self.root is None:
            raise ValueError("Dummy node removal requires a module root node")
        used_names: dict[str, int] = {}
        for n in list(self.nodes()):
            if isinstance(n, VNode) and isinstance(n.op, DummyOp):
                name = n.op.name
                fun_ty = FunctionType(
                    list(n.in_port_types), row_to_type(n.out_port_types)
                )
                if name in used_names:
                    used_names[name] += 1
                    name = f"{name}${used_names[name]}"
                else:
                    used_names[name] = 0
                decl = self.add_declare(fun_ty, self.root, name)
                n.op = ops.OpType(
                    ops.Call(
                        func_sig=fun_ty.to_hugr_poly(),
                        type_args=[],
                        instantiation=fun_ty.to_hugr().root,
                        parent=UNDEFINED,
                    )
                )
                self.add_edge(decl.out_port(0), n.add_in_port(fun_ty))
        return self

    def insert_order_edges(self) -> "Hugr":
        """Adds order edges to the source and target inter-graph edges.

        This ensures that the source is executed before the target. This action must be
        performed before serialisation.
        """
        for src, tgt in list(self.edges()):
            # Exclude CF and constant edges
            if isinstance(src, OutPortCF) or isinstance(
                src.node.op.root, ops.FuncDecl | ops.FuncDefn | ops.Const
            ):
                continue

            if src.node.parent != tgt.node.parent:
                # Walk up the hierarchy from the tgt until we hit a node at the same
                # level as src
                node = tgt.node
                while node.parent != src.node.parent:
                    if node.parent is None:
                        raise ValueError("Invalid non-local edge!")
                    node = node.parent
                # Add order edge to make sure that the src is executed first
                self.add_order_edge(src.node, node)
        return self

    def to_raw(self) -> raw.SerialHugr:
        """Returns the raw representation of this HUGR for serialisation."""
        if self.root is None:
            raise ValueError("Serial Hugr requires a root node")

        self.remove_dummy_nodes()
        self.insert_order_edges()
        # Hugr requires that Input/Output nodes are the first/second children in a DFG.
        # Furthermore, exit nodes must be the second children of CFGs. We're going to
        # satisfy this trivially by first serialising all inputs, outputs, entry and
        # exit nodes
        input_nodes: list[Node] = []
        output_nodes: list[Node] = []
        entry_nodes: list[Node] = []
        exit_nodes: list[Node] = []
        remaining_nodes: list[Node] = []
        indices = itertools.count()
        raw_index: dict[int, node_port.NodeIdx] = {}
        all_nodes = self.nodes()
        for n in all_nodes:
            if n is self.root:
                continue
            match n.op.root:
                case ops.Input():
                    input_nodes.append(n)
                case ops.Output():
                    output_nodes.append(n)
                # We can detect entry BBs by looking for BBs without incoming edges
                # since Guppy will never generate an edge pointing back to the entry.
                # Also, Guppy errors on unreachable code, so we will never generate
                # interior BBs without incoming edges. Hence, there are also no false
                # positives.
                case ops.DataflowBlock() if next(
                    self.in_edges(n.in_port(None)), None
                ) is None:
                    entry_nodes.append(n)
                case ops.ExitBlock():
                    exit_nodes.append(n)
                case _:
                    remaining_nodes.append(n)
        for n in itertools.chain(
            iter([self.root]),
            iter(entry_nodes),
            iter(exit_nodes),
            iter(input_nodes),
            iter(output_nodes),
            iter(remaining_nodes),
        ):
            raw_index[n.idx] = next(indices)

        nodes: list[ops.OpType] = [
            ops.OpType(ops.Module(parent=UNDEFINED))
        ] * self._graph.number_of_nodes()
        metadata: list[dict[str, Any]] = [
            {} for _ in range(self._graph.number_of_nodes())
        ]
        for n in self.nodes():
            idx = raw_index[n.idx]
            # Nodes without parent have themselves as parent in the serialised format
            parent = n.parent or n
            n.update_op()
            n.op.root.parent = raw_index[parent.idx]
            nodes[idx] = n.op
            metadata[idx] = n.meta_data

        edges: list[raw.Edge] = []
        for src, tgt in self.edges():
            edges.append(
                (
                    (raw_index[src.node.idx], src.offset),
                    (raw_index[tgt.node.idx], tgt.offset),
                )
            )

        for src, tgt in self.order_edges():
            edges.append(((raw_index[src.idx], None), (raw_index[tgt.idx], None)))

        return raw.SerialHugr(nodes=nodes, edges=edges, metadata=metadata)

    def serialize(self) -> str:
        """Serialize this Hugr in JSON format."""
        return self.to_raw().to_json()


def debug_metadata(debug: AstNode | None) -> dict[str, Any]:
    if debug is not None:
        file = get_file(debug)
        line, col = line_col(debug)
        line_offset = get_line_offset(debug)
        if file is not None and line_offset is not None:
            return {
                "di": {
                    "file": get_file(debug),
                    "line": line + line_offset - 1,
                    "col": col,
                }
            }
    return {}
