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

from __future__ import annotations

import ast
import inspect
import re
from itertools import chain
from typing import TYPE_CHECKING

import griffe
import libcst as cst
from libcst.codemod import CodemodContext
from libcst.codemod.visitors import AddImportsVisitor

if TYPE_CHECKING:
    from collections.abc import Sequence


_SECTION_NAMES = {
    "args": griffe.DocstringSectionKind.parameters,
    "arguments": griffe.DocstringSectionKind.parameters,
    "parameters": griffe.DocstringSectionKind.parameters,
    "keyword args": griffe.DocstringSectionKind.other_parameters,
    "keyword arguments": griffe.DocstringSectionKind.other_parameters,
    "other parameters": griffe.DocstringSectionKind.other_parameters,
    "params": griffe.DocstringSectionKind.parameters,
    "returns": griffe.DocstringSectionKind.returns,
    "yields": griffe.DocstringSectionKind.yields,
    "receives": griffe.DocstringSectionKind.receives,
}
_GOOGLE_HEADING = re.compile(r"^([A-Za-z][A-Za-z0-9 _-]*):[ \t]*$")
_NUMPY_UNDERLINE = re.compile(r"^[-=]{3,}[ \t]*$")
_SPHINX_FIELD = re.compile(r"^:([a-zA-Z]+)(?:\s+[^:]*)?:")


def _string_value(node: cst.SimpleString) -> str | None:
    try:
        value = ast.literal_eval(node.value)
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, str) else None


def _doc_expression(statement: cst.BaseStatement) -> cst.SimpleString | None:
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return None
    expression = statement.body[0]
    if isinstance(expression, cst.Expr) and isinstance(expression.value, cst.SimpleString):
        return expression.value
    return None


def _function_doc_expression(body: cst.BaseSuite) -> cst.SimpleString | None:
    if isinstance(body, cst.IndentedBlock) and body.body:
        return _doc_expression(body.body[0])
    if isinstance(body, cst.SimpleStatementSuite) and len(body.body) == 1:
        expression = body.body[0]
        if isinstance(expression, cst.Expr) and isinstance(expression.value, cst.SimpleString):
            return expression.value
    return None


def _style_for(value: str, requested: str) -> str:
    if requested != "auto":
        return requested
    if re.search(r"(?im)^:(?:param|parameter|arg|type|return|returns|rtype|raise|raises)\b", value):
        return "sphinx"
    lines = value.splitlines()
    if any(
        _NUMPY_UNDERLINE.fullmatch(lines[index + 1]) for index in range(len(lines) - 1) if _section_kind(lines[index])
    ):
        return "numpy"
    return "google"


def _clean_docstring(value: str) -> str:
    lines = value.splitlines()
    if lines and _GOOGLE_HEADING.fullmatch(lines[0]):
        later_headings = [
            line[: len(line) - len(line.lstrip())] for line in lines[1:] if _GOOGLE_HEADING.fullmatch(line.strip())
        ]
        indent = min(later_headings, key=len) if later_headings else ""
        return "\n".join([lines[0], *(line.removeprefix(indent) for line in lines[1:])]).strip()
    return inspect.cleandoc(value)


def _doc_node(value: str) -> cst.SubscriptElement:
    return cst.SubscriptElement(
        cst.Index(cst.Call(func=cst.Name("Doc"), args=[cst.Arg(cst.SimpleString(repr(value)))])),
    )


def _expression_name(expression: cst.BaseExpression) -> str | None:
    if isinstance(expression, cst.Name):
        return expression.value
    if isinstance(expression, cst.Attribute):
        return expression.attr.value
    return None


def _with_doc(annotation: cst.BaseExpression, description: str) -> cst.BaseExpression | None:
    description = description.strip()
    if not description:
        return None
    if isinstance(annotation, cst.Subscript) and _expression_name(annotation.value) == "Annotated":
        for element in annotation.slice[1:]:
            if (
                isinstance(element.slice, cst.Index)
                and isinstance(element.slice.value, cst.Call)
                and _expression_name(element.slice.value.func) == "Doc"
            ):
                return None
        return annotation.with_changes(slice=[*annotation.slice, _doc_node(description)])
    return cst.Subscript(
        value=cst.Name("Annotated"),
        slice=[cst.SubscriptElement(cst.Index(annotation)), _doc_node(description)],
    )


def _with_tuple_items(annotation: cst.BaseExpression, descriptions: Sequence[str]) -> cst.BaseExpression | None:
    if not isinstance(annotation, cst.Subscript) or _expression_name(annotation.value) not in {"tuple", "Tuple"}:
        return None
    if len(annotation.slice) != len(descriptions):
        return None
    elements = []
    for element, description in zip(annotation.slice, descriptions, strict=False):
        if not isinstance(element.slice, cst.Index):
            return None
        value = _with_doc(element.slice.value, description)
        if value is None:
            return None
        elements.append(element.with_changes(slice=element.slice.with_changes(value=value)))
    return annotation.with_changes(slice=elements)


def _with_component(
    annotation: cst.BaseExpression,
    index: int,
    descriptions: Sequence[str],
) -> cst.BaseExpression | None:
    if not isinstance(annotation, cst.Subscript) or index >= len(annotation.slice):
        return None
    element = annotation.slice[index]
    if not isinstance(element.slice, cst.Index):
        return None
    value = element.slice.value
    updated = _with_doc(value, descriptions[0]) if len(descriptions) == 1 else _with_tuple_items(value, descriptions)
    if updated is None:
        return None
    elements = list(annotation.slice)
    elements[index] = element.with_changes(slice=element.slice.with_changes(value=updated))
    return annotation.with_changes(slice=elements)


def _with_parameters(node: cst.FunctionDef, section: griffe.DocstringSection) -> cst.FunctionDef | None:
    parameter_docs = {item.name.lstrip("*"): item.description for item in section.value}
    if not parameter_docs or len(parameter_docs) != len(section.value):
        return None
    parameters = node.params
    all_parameters = list(chain(parameters.posonly_params, parameters.params, parameters.kwonly_params))
    if isinstance(parameters.star_arg, cst.Param):
        all_parameters.append(parameters.star_arg)
    if parameters.star_kwarg is not None:
        all_parameters.append(parameters.star_kwarg)
    by_name = {parameter.name.value: parameter for parameter in all_parameters}
    replacements: dict[str, cst.Param] = {}
    for name, description in parameter_docs.items():
        parameter = by_name.get(name)
        if parameter is None or parameter.annotation is None:
            return None
        annotation = _with_doc(parameter.annotation.annotation, description)
        if annotation is None:
            return None
        replacements[name] = parameter.with_changes(annotation=parameter.annotation.with_changes(annotation=annotation))

    def replace(items: Sequence[cst.Param]) -> list[cst.Param]:
        return [replacements.get(item.name.value, item) for item in items]

    star_arg = parameters.star_arg
    if isinstance(star_arg, cst.Param):
        star_arg = replacements.get(star_arg.name.value, star_arg)
    star_kwarg = parameters.star_kwarg
    if star_kwarg is not None:
        star_kwarg = replacements.get(star_kwarg.name.value, star_kwarg)
    return node.with_changes(
        params=parameters.with_changes(
            posonly_params=replace(parameters.posonly_params),
            params=replace(parameters.params),
            kwonly_params=replace(parameters.kwonly_params),
            star_arg=star_arg,
            star_kwarg=star_kwarg,
        ),
    )


def _with_result(node: cst.FunctionDef, section: griffe.DocstringSection) -> cst.FunctionDef | None:
    if node.returns is None:
        return None
    descriptions = [item.description for item in section.value]
    if not descriptions or any(not description.strip() for description in descriptions):
        return None
    annotation = node.returns.annotation
    kind = section.kind
    name = _expression_name(annotation.value) if isinstance(annotation, cst.Subscript) else None

    if kind is griffe.DocstringSectionKind.yields:
        updated = (
            _with_component(annotation, 0, descriptions)
            if name in {"Generator", "Iterator", "AsyncGenerator", "AsyncIterator", "Iterable", "AsyncIterable"}
            else None
        )
    elif kind is griffe.DocstringSectionKind.receives:
        updated = _with_component(annotation, 1, descriptions) if name == "Generator" else None
    elif name == "Generator":
        updated = _with_component(annotation, 2, descriptions)
    elif len(descriptions) > 1:
        updated = _with_tuple_items(annotation, descriptions)
    else:
        updated = _with_doc(annotation, descriptions[0])
    if updated is None:
        return None
    return node.with_changes(returns=node.returns.with_changes(annotation=updated))


def _section_kind(name: str) -> griffe.DocstringSectionKind | None:
    return _SECTION_NAMES.get(name.lower().replace("_", " ").strip())


def _without_sections(value: str, style: str, moved: set[griffe.DocstringSectionKind]) -> str:
    lines = [line if line.strip() else "" for line in value.splitlines()]
    if style == "sphinx":
        kept = []
        index = 0
        while index < len(lines):
            field = _SPHINX_FIELD.match(lines[index])
            field_name = field.group(1).lower() if field else ""
            if field_name in {"param", "parameter", "arg", "argument", "keyword", "key", "type", "vartype"}:
                kind = griffe.DocstringSectionKind.parameters
            elif field_name in {"return", "returns", "rtype"}:
                kind = griffe.DocstringSectionKind.returns
            else:
                kind = None
            if kind in moved:
                index += 1
                while index < len(lines) and (not lines[index].strip() or lines[index][0].isspace()):
                    index += 1
                continue
            kept.append(lines[index])
            index += 1
        return "\n".join(kept).strip("\n")

    headings: list[tuple[int, griffe.DocstringSectionKind | None]] = []
    for index, line in enumerate(lines):
        if style == "numpy" and index + 1 < len(lines) and _NUMPY_UNDERLINE.fullmatch(lines[index + 1]):
            headings.append((index, _section_kind(line)))
        elif style == "google" and (match := _GOOGLE_HEADING.fullmatch(line)):
            headings.append((index, _section_kind(match.group(1))))
    if not headings:
        return value
    parts = []
    preamble = "\n".join(lines[: headings[0][0]]).strip("\n")
    if preamble:
        parts.append(preamble)
    for position, (start, kind) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        if kind not in moved:
            part = "\n".join(lines[start:end]).strip("\n")
            if part:
                parts.append(part)
        elif style == "google":
            prose_start = next(
                (index for index in range(start + 1, end) if lines[index] and not lines[index][0].isspace()),
                None,
            )
            if prose_start is not None:
                parts.append("\n".join(lines[prose_start:end]).strip("\n"))
    return "\n\n".join(parts)


def _new_literal(original: cst.SimpleString, value: str, newline: str) -> cst.SimpleString:
    quote = "'''" if original.value.lstrip("rRuU").startswith("'''") else '"""'
    if quote in value:
        quote = '"""' if quote == "'''" else "'''"
    if quote in value or "\r" in value:
        return cst.SimpleString(repr(value))
    escaped = value.replace("\\", "\\\\")
    if "\n" not in escaped:
        return cst.SimpleString(f"{quote}{escaped}{quote}")
    indents = [line[: len(line) - len(line.lstrip())] for line in original.value.splitlines()[1:] if line.strip()]
    indent = min(indents, key=len) if indents else "    "
    lines = escaped.split("\n")
    body = lines[0] + newline + newline.join(indent + line if line else "" for line in lines[1:]) + newline + indent
    return cst.SimpleString(f"{quote}{body}{quote}")


def _replace_function_docstring(body: cst.BaseSuite, value: str, newline: str) -> cst.BaseSuite:
    if isinstance(body, cst.IndentedBlock):
        statements = list(body.body)
        if not statements:
            return body
        statement = statements[0]
        expression = _doc_expression(statement)
        if (
            expression is None
            or not isinstance(statement, cst.SimpleStatementLine)
            or not isinstance(statement.body[0], cst.Expr)
        ):
            return body
        if value:
            statements[0] = statement.with_changes(
                body=[statement.body[0].with_changes(value=_new_literal(expression, value, newline))],
            )
        else:
            statements.pop(0)
        if not statements:
            statements = [cst.SimpleStatementLine(body=[cst.Pass()])]
        return body.with_changes(body=statements)
    if isinstance(body, cst.SimpleStatementSuite) and len(body.body) == 1:
        expression = body.body[0]
        if isinstance(expression, cst.Expr) and isinstance(expression.value, cst.SimpleString):
            replacement = (
                [expression.with_changes(value=_new_literal(expression.value, value, newline))]
                if value
                else [cst.Pass()]
            )
            return body.with_changes(body=replacement)
    return body


class _PEP727Transformer(cst.CSTTransformer):
    """Move parsed docstring descriptions into annotations."""

    def __init__(
        self,
        cst_module: cst.Module,
        module_path: str,
        docstrings: dict[str, griffe.Docstring] | None = None,
        *,
        style: str = "auto",
    ) -> None:
        self.cst_module = cst_module
        self.docstrings = docstrings or {}
        self.style = style
        self.stack = [module_path]
        self.changed = False

    @property
    def current_path(self) -> str:
        return ".".join(self.stack)

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self.stack.append(node.name.value)

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:  # noqa: ARG002
        self.stack.pop()
        if isinstance(updated_node.body, cst.IndentedBlock):
            updated_node = updated_node.with_changes(
                body=updated_node.body.with_changes(body=self._attributes(updated_node.body.body)),
            )
        return updated_node

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        self.stack.append(node.name.value)

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:  # noqa: ARG002
        path = self.current_path
        self.stack.pop()
        literal = _function_doc_expression(updated_node.body)
        raw_value = _string_value(literal) if literal is not None else None
        value = _clean_docstring(raw_value) if raw_value is not None else None
        style = _style_for(value, self.style) if value is not None else self.style
        docstring = self.docstrings.get(path)
        if docstring is None and value is not None:
            parse_value = (
                "\n" + value
                if value and style == "google" and _GOOGLE_HEADING.fullmatch(value.splitlines()[0])
                else value
            )
            docstring = griffe.Docstring(parse_value, parser=griffe.Parser(style), parser_options={"warnings": False})
        if docstring is None:
            return updated_node

        moved: set[griffe.DocstringSectionKind] = set()
        for kind in (
            griffe.DocstringSectionKind.parameters,
            griffe.DocstringSectionKind.other_parameters,
            griffe.DocstringSectionKind.yields,
            griffe.DocstringSectionKind.receives,
            griffe.DocstringSectionKind.returns,
        ):
            sections = [section for section in docstring.parsed if section.kind is kind]
            if len(sections) != 1:
                continue
            if kind in {griffe.DocstringSectionKind.parameters, griffe.DocstringSectionKind.other_parameters}:
                candidate = _with_parameters(updated_node, sections[0])
            else:
                candidate = _with_result(updated_node, sections[0])
            if candidate is not None:
                updated_node = candidate
                moved.add(kind)
                self.changed = True

        if moved and value is not None and literal is not None:
            remaining = _without_sections(value, style, moved)
            updated_node = updated_node.with_changes(
                body=_replace_function_docstring(updated_node.body, remaining, self.cst_module.default_newline),
            )
        return updated_node

    def visit_AnnAssign(self, node: cst.AnnAssign) -> None:
        if isinstance(node.target, cst.Name):
            self.stack.append(node.target.value)

    def leave_AnnAssign(self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign) -> cst.AnnAssign:
        if not isinstance(original_node.target, cst.Name):
            return updated_node
        path = self.current_path
        self.stack.pop()
        docstring = self.docstrings.get(path)
        if docstring is not None and docstring.parsed and docstring.parsed[0].kind is griffe.DocstringSectionKind.text:
            annotation = _with_doc(updated_node.annotation.annotation, str(docstring.parsed[0].value))
            if annotation is not None:
                self.changed = True
                return updated_node.with_changes(annotation=updated_node.annotation.with_changes(annotation=annotation))
        return updated_node

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:  # noqa: ARG002
        return updated_node.with_changes(body=self._attributes(updated_node.body))

    def _attributes(self, statements: Sequence[cst.BaseStatement]) -> list[cst.BaseStatement]:
        result = []
        index = 0
        while index < len(statements):
            statement = statements[index]
            next_statement = statements[index + 1] if index + 1 < len(statements) else None
            assignment = (
                statement.body[0]
                if isinstance(statement, cst.SimpleStatementLine) and len(statement.body) == 1
                else None
            )
            literal = _doc_expression(next_statement) if next_statement is not None else None
            description = _string_value(literal) if literal is not None else None
            if isinstance(assignment, cst.AnnAssign) and isinstance(assignment.target, cst.Name) and description:
                annotation = _with_doc(assignment.annotation.annotation, inspect.cleandoc(description))
                if annotation is not None:
                    assignment = assignment.with_changes(
                        annotation=assignment.annotation.with_changes(annotation=annotation),
                    )
                    result.append(statement.with_changes(body=[assignment]))
                    self.changed = True
                    index += 2
                    continue
            result.append(statement)
            index += 1
        return result


def _transform_source(source: str, *, style: str = "auto") -> str:
    module = cst.parse_module(source)
    transformer = _PEP727Transformer(module, "module", style=style)
    transformed = module.visit(transformer)
    if transformer.changed:
        context = CodemodContext()
        AddImportsVisitor.add_needed_import(context, "typing", "Annotated")
        AddImportsVisitor.add_needed_import(context, "typing_extensions", "Doc")
        transformed = transformed.visit(AddImportsVisitor(context))
    return transformed.code
