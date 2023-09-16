from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING, Sequence

import libcst as cst
from griffe.enumerations import DocstringSectionKind
from libcst import matchers

if TYPE_CHECKING:
    from griffe import Docstring


def _metadata_node(name: str, *args: cst.BaseExpression) -> cst.SubscriptElement:
    return cst.SubscriptElement(
        cst.Index(
            cst.Call(
                func=cst.Name(value=name),
                args=[cst.Arg(arg) for arg in args],
            ),
        ),
    )


def _doc_node(value: str) -> cst.SubscriptElement:
    return _metadata_node("Doc", cst.SimpleString(value=repr(value)))


def _name_node(value: str) -> cst.SubscriptElement:
    return _metadata_node("Name", cst.SimpleString(value=repr(value)))


def _raises_node(exception: str, description: str) -> cst.SubscriptElement:
    return _metadata_node("Raises", cst.Name(exception), cst.SimpleString(value=repr(description)))


def _warns_node(warning: str, description: str) -> cst.SubscriptElement:
    return _metadata_node("Warns", cst.Name(warning), cst.SimpleString(value=repr(description)))


def _annotated(
    annotation: cst.BaseExpression,
    *,
    doc: str | None = None,
    name: str | None = None,
    raises: Sequence[tuple[type, str]] | None = None,
    warns: Sequence[tuple[type, str]] | None = None,
) -> cst.Annotation:
    slice_elements: list[cst.SubscriptElement] = []
    if name:
        slice_elements.append(_name_node(name))
    if doc:
        slice_elements.append(_doc_node(doc))
    if raises:
        for exception, description in raises:
            slice_elements.append(_raises_node(str(exception), description))
    if warns:
        for warning, description in warns:
            slice_elements.append(_warns_node(str(warning), description))
    return cst.Annotation(
        annotation=cst.Subscript(
            value=cst.Name(value="Annotated"),
            slice=[
                cst.SubscriptElement(cst.Index(annotation)),
                *slice_elements,
            ],
        ),
    )


def _update_slice(node, get_element, docstrings):
    for index in range(len(docstrings)):
        element = get_element(node, index)
        item = docstrings[index]
        node = node.with_deep_changes(
            element.slice,
            value=_annotated(element.slice.value, name=item[0], doc=item[1]).annotation,
        )
    return node


def _matches_generator(annotation: cst.CSTNode) -> bool:
    return matchers.matches(annotation, matchers.Subscript(value=matchers.Name("Generator")))


def _matches_iterator(annotation: cst.CSTNode) -> bool:
    return matchers.matches(annotation, matchers.Subscript(value=matchers.Name("Iterator")))


def _matches_tuple(annotation: cst.CSTNode) -> bool:
    return matchers.matches(annotation, matchers.Subscript(value=matchers.Name("tuple") | matchers.Name("Tuple")))


class PEP727Transformer(cst.CSTTransformer):
    def __init__(self, cst_module: cst.Module, module_path: str, docstrings: dict[str, Docstring]) -> None:
        self.cst_module: cst.Module = cst_module
        self.module_path: str = module_path
        self.docstrings: dict[str, Docstring] = docstrings
        self.stack: list[str] = [module_path]

    @property
    def current_path(self) -> str:
        return ".".join(self.stack)

    def visit_ClassDef(self, node: cst.ClassDef) -> bool | None:
        self.stack.append(node.name.value)

    def leave_ClassDef(
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,
    ) -> cst.CSTNode:
        self.stack.pop()
        return updated_node

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        self.stack.append(node.name.value)

    def leave_FunctionDef(
        self,
        original_node: cst.FunctionDef,
        updated_node: cst.FunctionDef,
    ) -> cst.CSTNode:
        current_path = self.current_path
        self.stack.pop()

        if current_path in self.docstrings:
            docstring = self.docstrings[current_path]
            param_docstrings = []
            return_docstrings = []
            yield_docstrings = []
            receive_docstrings = []
            exception_docstrings = []
            warning_docstrings = []

            for _section_index, section in enumerate(docstring.parsed):
                if section.kind is DocstringSectionKind.parameters:
                    param_docstrings = {param.name: param.description for param in section.value}
                elif section.kind is DocstringSectionKind.returns:
                    return_docstrings = [(returned.name, returned.description) for returned in section.value]
                elif section.kind is DocstringSectionKind.yields:
                    yield_docstrings = [(yielded.name, yielded.description) for yielded in section.value]
                elif section.kind is DocstringSectionKind.receives:
                    receive_docstrings = [(received.name, received.description) for received in section.value]
                elif section.kind is DocstringSectionKind.raises:
                    exception_docstrings = [(exc.annotation.canonical_name, exc.description) for exc in section.value]
                elif section.kind is DocstringSectionKind.warns:
                    warning_docstrings = [(warning.annotation, warning.description) for warning in section.value]

            if param_docstrings:
                for param in chain(
                    updated_node.params.posonly_params, updated_node.params.params, updated_node.params.kwonly_params
                ):
                    if param.name.value in param_docstrings:
                        updated_node = updated_node.with_deep_changes(
                            param,
                            annotation=_annotated(
                                param.annotation.annotation,
                                doc=param_docstrings[param.name.value],
                            ),
                        )

            if yield_docstrings:
                returns = updated_node.returns
                if _matches_generator(returns.annotation) or _matches_iterator(returns.annotation):
                    if isinstance(returns.annotation.slice[0].slice.value, cst.Subscript):
                        updated_node = _update_slice(
                            updated_node,
                            lambda node, index: node.returns.annotation.slice[0].slice.value.slice[index],
                            yield_docstrings,
                        )
                    else:
                        updated_node = updated_node.with_deep_changes(
                            returns.annotation.slice[0].slice,
                            value=_annotated(
                                returns.annotation.slice[0].slice.value,
                                name=yield_docstrings[0][0],
                                doc=yield_docstrings[0][1],
                            ).annotation,
                        )

            if receive_docstrings:
                returns = updated_node.returns
                if _matches_generator(returns.annotation):
                    if isinstance(returns.annotation.slice[1].slice.value, cst.Subscript):
                        updated_node = _update_slice(
                            updated_node,
                            lambda node, index: node.returns.annotation.slice[1].slice.value.slice[index],
                            receive_docstrings,
                        )
                    else:
                        updated_node = updated_node.with_deep_changes(
                            returns.annotation.slice[1].slice,
                            value=_annotated(
                                returns.annotation.slice[0].slice.value,
                                name=receive_docstrings[0][0],
                                doc=receive_docstrings[0][1],
                            ).annotation,
                        )

            if return_docstrings or exception_docstrings or warning_docstrings:
                returns = updated_node.returns
                kwargs = {}
                if return_docstrings:
                    if _matches_generator(returns.annotation):
                        if isinstance(returns.annotation.slice[2].slice.value, cst.Subscript):
                            updated_node = _update_slice(
                                updated_node,
                                lambda node, index: node.returns.annotation.slice[2].slice.value.slice[index],
                                return_docstrings,
                            )
                        else:
                            updated_node = updated_node.with_deep_changes(
                                returns.annotation.slice[2].slice,
                                value=_annotated(
                                    returns.annotation.slice[0].slice.value,
                                    name=return_docstrings[0][0],
                                    doc=return_docstrings[0][1],
                                ).annotation,
                            )
                    elif _matches_tuple(returns.annotation):
                        updated_node = _update_slice(
                            updated_node,
                            lambda node, index: node.returns.annotation.slice[index],
                            return_docstrings,
                        )
                    else:
                        kwargs["name"] = return_docstrings[0][0]
                        kwargs["doc"] = return_docstrings[0][1]

                if exception_docstrings or warning_docstrings or kwargs:
                    updated_node = updated_node.with_changes(
                        returns=_annotated(
                            returns.annotation,
                            raises=exception_docstrings,
                            warns=warning_docstrings,
                            **kwargs,
                        ),
                    )

        return updated_node

    def visit_Assign(self, node: cst.Assign) -> bool | None:
        if len(node.targets) > 1:
            return None
        self.stack.append(node.targets[0])

    def leave_Assign(self, original_node: cst.Assign, updated_node: cst.Assign) -> cst.CSTNode:
        self.stack.pop()
        return updated_node

    def visit_AnnAssign(self, node: cst.AnnAssign) -> bool | None:
        self.stack.append(node.target.value)

    def leave_AnnAssign(self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign) -> cst.CSTNode:
        current_path = self.current_path
        self.stack.pop()
        if current_path in self.docstrings:
            return updated_node.with_changes(
                annotation=_annotated(
                    updated_node.annotation.annotation,
                    doc=self.docstrings[current_path].parsed[0].value,
                ),
            )
        return updated_node
