from __future__ import annotations

from itertools import chain

import libcst as cst
from libcst import matchers
from griffe import Docstring
from griffe.enumerations import DocstringSectionKind


def _metadata_node(name: str, *args: cst.BaseExpression) -> cst.SubscriptElement:
    return cst.SubscriptElement(
        cst.Index(
            cst.Call(
                func=cst.Name(value=name),
                args=[cst.Arg(arg) for arg in args],
            )
        )
    )


def _doc_node(value: str) -> cst.SubscriptElement:
    return _metadata_node("doc", cst.SimpleString(value=repr(value)))


def _name_node(value: str) -> cst.SubscriptElement:
    return _metadata_node("name", cst.SimpleString(value=repr(value)))


def _annotated(annotation: cst.BaseExpression, doc: str, name: str | None = None) -> cst.Annotation:
    slice_elements: list[cst.SubscriptElement] = [_doc_node(doc)]
    if name:
        slice_elements.insert(0, _name_node(name))
    return cst.Annotation(
        annotation=cst.Subscript(
            value=cst.Name(value="Annotated"),
            slice=[
                cst.SubscriptElement(cst.Index(annotation)),
                *slice_elements,
            ],
        )
    )


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
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.CSTNode:
        self.stack.pop()
        return updated_node

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        self.stack.append(node.name.value)

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.CSTNode:
        current_path = self.current_path
        self.stack.pop()
        if current_path in self.docstrings:
            docstring = self.docstrings[current_path]
            param_docstrings = []
            return_docstrings = []
            exception_docstrings = []
            warning_docstrings = []
            for section_index, section in enumerate(docstring.parsed):
                if section.kind is DocstringSectionKind.parameters:
                    param_docstrings = {param.name: param.description for param in section.value}
                elif section.kind is DocstringSectionKind.returns:
                    return_docstrings = [{"name": retval.name, "doc": retval.description} for retval in section.value]
                elif section.kind is DocstringSectionKind.raises:
                    exception_docstrings = {exc.annotation.canonical_name: exc.description for exc in section.value}
                elif section.kind is DocstringSectionKind.warns:
                    warning_docstrings = {warning.annotation: warning.description for warning in section.value}
            if param_docstrings:
                for param in chain(updated_node.params.posonly_params, updated_node.params.params, updated_node.params.kwonly_params):
                    if param.name.value in param_docstrings:
                        updated_node = updated_node.with_deep_changes(
                            param,
                            annotation=_annotated(
                                param.annotation.annotation,
                                param_docstrings[param.name.value],
                            ),
                        )
            if return_docstrings:
                returns = updated_node.returns
                if _matches_generator(returns.annotation):
                    pass
                elif _matches_iterator(returns.annotation):
                    pass
                elif _matches_tuple(returns.annotation):
                    pass
                else:
                    updated_node = updated_node.with_changes(
                        returns=_annotated(
                            returns.annotation,
                            doc=return_docstrings[0]["doc"],
                            name=return_docstrings[0]["name"],
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
                    self.docstrings[current_path].parsed[0].value,
                )
            )
        return updated_node
