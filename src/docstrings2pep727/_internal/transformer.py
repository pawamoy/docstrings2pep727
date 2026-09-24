# SPDX-License-Identifier: ISC
#
# ISC License
#
# Copyright (c) 2023, Timothée Mazzucotelli and contributors
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

# The CST transformer module.

from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING, TypeGuard

import libcst as cst
from griffe import Docstring, DocstringSectionKind
from libcst import matchers

if TYPE_CHECKING:
    from collections.abc import Sequence


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
    return _metadata_node("Raises", cst.parse_expression(exception), cst.SimpleString(value=repr(description)))


def _warns_node(warning: str, description: str) -> cst.SubscriptElement:
    return _metadata_node("Warns", cst.parse_expression(warning), cst.SimpleString(value=repr(description)))


def _annotated(
    annotation: cst.BaseExpression,
    *,
    doc: str | None = None,
    name: str | None = None,
    raises: Sequence[tuple[str, str]] | None = None,
    warns: Sequence[tuple[str, str]] | None = None,
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


def _update_slice(node: cst.Subscript, docstrings: list[tuple[str | None, str]]) -> cst.Subscript:
    elements = list(node.slice)
    for index, (name, doc) in enumerate(docstrings):
        if index >= len(elements):
            break
        element = elements[index]
        if isinstance(element.slice, cst.Index):
            elements[index] = element.with_changes(
                slice=element.slice.with_changes(value=_annotated(element.slice.value, name=name, doc=doc).annotation),
            )
    return node.with_changes(slice=elements)


def _matches_generator(annotation: cst.BaseExpression) -> TypeGuard[cst.Subscript]:
    return isinstance(annotation, cst.Subscript) and matchers.matches(
        annotation,
        matchers.Subscript(value=matchers.Name("Generator")),
    )


def _matches_iterator(annotation: cst.BaseExpression) -> TypeGuard[cst.Subscript]:
    return isinstance(annotation, cst.Subscript) and matchers.matches(
        annotation,
        matchers.Subscript(value=matchers.Name("Iterator")),
    )


def _matches_tuple(annotation: cst.BaseExpression) -> TypeGuard[cst.Subscript]:
    return isinstance(annotation, cst.Subscript) and matchers.matches(
        annotation,
        matchers.Subscript(value=matchers.Name("tuple") | matchers.Name("Tuple")),
    )


def _annotate_component(
    annotation: cst.Subscript,
    index: int,
    docstrings: list[tuple[str | None, str]],
) -> cst.Subscript:
    if index >= len(annotation.slice):
        return annotation
    elements = list(annotation.slice)
    element = elements[index]
    if not isinstance(element.slice, cst.Index):
        return annotation
    value = element.slice.value
    if isinstance(value, cst.Subscript):
        value = _update_slice(value, docstrings)
    else:
        name, doc = docstrings[0]
        value = _annotated(value, name=name, doc=doc).annotation
    elements[index] = element.with_changes(slice=element.slice.with_changes(value=value))
    return annotation.with_changes(slice=elements)


class _PEP727Transformer(cst.CSTTransformer):
    """The CST transformer."""

    def __init__(
        self,
        cst_module: cst.Module,
        module_path: str,
        docstrings: dict[str, Docstring],
    ) -> None:
        self.cst_module: cst.Module = cst_module
        self.module_path: str = module_path
        self.docstrings: dict[str, Docstring] = docstrings
        self.stack: list[str] = [module_path]

    @property
    def current_path(self) -> str:
        return ".".join(self.stack)

    def visit_ClassDef(self, node: cst.ClassDef) -> None:  # noqa: N802
        self.stack.append(node.name.value)

    def leave_ClassDef(  # noqa: N802
        self,
        original_node: cst.ClassDef,  # noqa: ARG002
        updated_node: cst.ClassDef,
    ) -> cst.ClassDef:
        self.stack.pop()
        return updated_node

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:  # noqa: N802
        self.stack.append(node.name.value)

    def leave_FunctionDef(  # noqa: N802
        self,
        original_node: cst.FunctionDef,  # noqa: ARG002
        updated_node: cst.FunctionDef,
    ) -> cst.FunctionDef:
        current_path = self.current_path
        self.stack.pop()

        if current_path in self.docstrings:
            docstring = self.docstrings[current_path]
            param_docstrings = {}
            return_docstrings = []
            yield_docstrings = []
            receive_docstrings = []
            exception_docstrings = []
            warning_docstrings = []

            for section in docstring.parsed:
                if section.kind is DocstringSectionKind.parameters:
                    param_docstrings = {param.name: param.description for param in section.value}
                elif section.kind is DocstringSectionKind.returns:
                    return_docstrings = [(returned.name, returned.description) for returned in section.value]
                elif section.kind is DocstringSectionKind.yields:
                    yield_docstrings = [(yielded.name, yielded.description) for yielded in section.value]
                elif section.kind is DocstringSectionKind.receives:
                    receive_docstrings = [(received.name, received.description) for received in section.value]
                elif section.kind is DocstringSectionKind.raises:
                    exception_docstrings = [
                        (str(exc.annotation), exc.description) for exc in section.value if exc.annotation is not None
                    ]
                elif section.kind is DocstringSectionKind.warns:
                    warning_docstrings = [
                        (str(warning.annotation), warning.description)
                        for warning in section.value
                        if warning.annotation is not None
                    ]

            if param_docstrings:
                for param in chain(
                    updated_node.params.posonly_params,
                    updated_node.params.params,
                    updated_node.params.kwonly_params,
                ):
                    if param.name.value in param_docstrings and param.annotation:
                        updated_node = updated_node.with_deep_changes(
                            param,
                            annotation=_annotated(
                                param.annotation.annotation,
                                doc=param_docstrings[param.name.value],
                            ),
                        )

            returns = updated_node.returns
            if returns is not None:
                annotation = returns.annotation
                if yield_docstrings and (_matches_generator(annotation) or _matches_iterator(annotation)):
                    annotation = _annotate_component(annotation, 0, yield_docstrings)

                if receive_docstrings and _matches_generator(annotation):
                    annotation = _annotate_component(annotation, 1, receive_docstrings)

                return_name = None
                return_doc = None
                if return_docstrings:
                    if _matches_generator(annotation):
                        annotation = _annotate_component(annotation, 2, return_docstrings)
                    elif _matches_tuple(annotation):
                        annotation = _update_slice(annotation, return_docstrings)
                    else:
                        return_name, return_doc = return_docstrings[0]

                if return_name or return_doc or exception_docstrings or warning_docstrings:
                    annotation = _annotated(
                        annotation,
                        name=return_name,
                        doc=return_doc,
                        raises=exception_docstrings,
                        warns=warning_docstrings,
                    ).annotation

                updated_node = updated_node.with_changes(returns=returns.with_changes(annotation=annotation))

        return updated_node

    def visit_Assign(self, node: cst.Assign) -> None:  # noqa: N802
        if len(node.targets) == 1 and isinstance(node.targets[0].target, cst.Name):
            self.stack.append(node.targets[0].target.value)

    def leave_Assign(  # noqa: N802
        self,
        original_node: cst.Assign,
        updated_node: cst.Assign,
    ) -> cst.Assign:
        if len(original_node.targets) == 1 and isinstance(original_node.targets[0].target, cst.Name):
            self.stack.pop()
        return updated_node

    def visit_AnnAssign(self, node: cst.AnnAssign) -> None:  # noqa: N802
        if isinstance(node.target, cst.Name):
            self.stack.append(node.target.value)

    def leave_AnnAssign(  # noqa: N802
        self,
        original_node: cst.AnnAssign,
        updated_node: cst.AnnAssign,
    ) -> cst.AnnAssign:
        if not isinstance(original_node.target, cst.Name):
            return updated_node
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
