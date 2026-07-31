import ast
import io
import re
import tokenize

import flare
from flare.context import FlareReturnException


class CallGraphAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.call_graph = {}
        self.current_func = None
        self.exported_funcs = set()
        self.nostack_funcs = set()

    def visit_FunctionDef(self, node):
        is_exported = any(
            isinstance(dec, ast.Name) and dec.id in ("export", "macro", "event", "tick", "load", "tag") or isinstance(
                dec, ast.Call) and getattr(dec.func, "id", "") in ("export", "macro", "event", "tick", "load", "tag")
            for dec in node.decorator_list)
        is_nostack = any(
            isinstance(dec, ast.Name) and dec.id == "nostack" or isinstance(dec, ast.Call) and getattr(dec.func, "id",
                                                                                                       "") == "nostack"
            for dec in node.decorator_list)
        if is_exported:
            self.exported_funcs.add(node.name)
        if is_nostack:
            self.nostack_funcs.add(node.name)

        prev = self.current_func
        self.current_func = node.name
        self.call_graph[node.name] = set()
        self.generic_visit(node)
        self.current_func = prev

    def visit_Call(self, node):
        if self.current_func and isinstance(node.func, ast.Name):
            self.call_graph[self.current_func].add(node.func.id)
        self.generic_visit(node)

    def get_recursive_functions(self):
        recursive = set()
        for func in self.exported_funcs:
            visited = set()
            stack = [func]
            while stack:
                curr = stack.pop()
                if curr in visited:
                    continue
                visited.add(curr)
                if func in self.call_graph.get(curr, set()):
                    recursive.add(func)
                    break
                for neighbor in self.call_graph.get(curr, set()):
                    if neighbor not in visited:
                        stack.append(neighbor)
        return recursive - self.nostack_funcs


class FlareTransformer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.counter = 0
        self.in_flare_func = False

    def gen_name(self):
        self.counter += 1
        return f"__flare_{self.counter}"

    def visit_FunctionDef(self, node):
        is_exported = any(
            isinstance(dec, ast.Name) and dec.id in ("export", "macro", "event", "tick", "load", "tag") or isinstance(
                dec, ast.Call) and getattr(dec.func, "id", "") in ("export", "macro", "event", "tick", "load", "tag")
            for dec in node.decorator_list)

        is_generated = node.name.startswith("__flare_")
        prev_in_flare = self.in_flare_func

        if is_exported or is_generated:
            self.in_flare_func = True
        else:
            self.in_flare_func = False

        self.generic_visit(node)
        self.in_flare_func = prev_in_flare

        if self.in_flare_func or is_exported or is_generated:
            enter_stmt = ast.Expr(
                value=ast.Call(func=ast.Name(id="_flare_enter_scope", ctx=ast.Load()), args=[], keywords=[]))
            ast.copy_location(enter_stmt, node)

            exit_stmt = ast.Expr(
                value=ast.Call(func=ast.Name(id="_flare_exit_scope", ctx=ast.Load()), args=[], keywords=[]))
            ast.copy_location(exit_stmt, node)

            try_node = ast.Try(body=node.body, handlers=[], orelse=[], finalbody=[exit_stmt])
            ast.copy_location(try_node, node)

            node.body = [enter_stmt, try_node]

        return node

    def visit_Expr(self, node):
        self.generic_visit(node)
        wrapper = ast.Call(func=ast.Name(id="_flare_alone", ctx=ast.Load()), args=[node.value], keywords=[])
        ast.copy_location(wrapper, node.value)
        node.value = wrapper
        return node

    def visit_If(self, node):
        funcs = []
        cond_args = []
        body_args = []

        curr = node
        while True:
            name_body = self.gen_name()
            body_func = ast.FunctionDef(name=name_body, body=curr.body if curr.body else [ast.Pass()],
                                        decorator_list=[],
                                        args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[],
                                                           defaults=[]))
            ast.copy_location(body_func, curr)
            self.generic_visit(body_func)
            funcs.append(body_func)

            lambda_cond = ast.Lambda(
                args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]), body=curr.test)
            ast.copy_location(lambda_cond, curr.test)
            self.generic_visit(lambda_cond)
            cond_args.append(lambda_cond)
            body_args.append(ast.Name(id=name_body, ctx=ast.Load()))

            if not curr.orelse:
                break
            elif len(curr.orelse) == 1 and isinstance(curr.orelse[0], ast.If):
                curr = curr.orelse[0]
            else:
                name_orelse = self.gen_name()
                orelse_func = ast.FunctionDef(name=name_orelse,
                                              args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[],
                                                                 defaults=[]), body=curr.orelse, decorator_list=[])
                ast.copy_location(orelse_func, curr)
                self.generic_visit(orelse_func)
                funcs.append(orelse_func)
                cond_args.append(ast.Constant(value=None))
                body_args.append(ast.Name(id=name_orelse, ctx=ast.Load()))
                break

        call_expr = ast.Expr(
            value=ast.Call(func=ast.Name(id="_flare_if", ctx=ast.Load()), args=cond_args + body_args, keywords=[]))
        ast.copy_location(call_expr, node)
        funcs.append(call_expr)

        return funcs

    def visit_Match(self, node):
        subj_name = self.gen_name()
        subj_assign = ast.Assign(targets=[ast.Name(id=subj_name, ctx=ast.Store())], value=node.subject)
        ast.copy_location(subj_assign, node)
        subj_load = lambda: ast.Name(id=subj_name, ctx=ast.Load())

        def _build_pattern_cond(pattern):
            if isinstance(pattern, ast.MatchValue):
                cmp = ast.Compare(left=subj_load(), ops=[ast.Eq()], comparators=[pattern.value])
                ast.copy_location(cmp, pattern)
                return cmp
            elif isinstance(pattern, ast.MatchSingleton):
                cmp = ast.Compare(left=subj_load(), ops=[ast.Eq()], comparators=[ast.Constant(value=pattern.value)])
                ast.copy_location(cmp, pattern)
                return cmp
            elif isinstance(pattern, ast.MatchOr):
                conds = [_build_pattern_cond(p) for p in pattern.patterns]
                conds = [c for c in conds if c is not None]
                if not conds:
                    return None
                if len(conds) == 1:
                    return conds[0]
                res = ast.BoolOp(op=ast.Or(), values=conds)
                ast.copy_location(res, pattern)
                return res
            elif isinstance(pattern, ast.MatchAs):
                sub_cond = _build_pattern_cond(pattern.pattern) if pattern.pattern else None
                return sub_cond
            return None

        first_if = None
        current_if = None

        for case in node.cases:
            body = list(case.body)
            if isinstance(case.pattern, ast.MatchAs) and case.pattern.name:
                bind_assign = ast.Assign(targets=[ast.Name(id=case.pattern.name, ctx=ast.Store())], value=subj_load())
                ast.copy_location(bind_assign, case.pattern)
                body.insert(0, bind_assign)

            cond = _build_pattern_cond(case.pattern)

            if case.guard:
                if cond is None:
                    cond = case.guard
                else:
                    cond = ast.BoolOp(op=ast.And(), values=[cond, case.guard])
                    ast.copy_location(cond, case.guard)

            if cond is None:
                if current_if is not None:
                    current_if.orelse = body
                break
            else:
                if_node = ast.If(test=cond, body=body, orelse=[])
                ast.copy_location(if_node, case)
                if first_if is None:
                    first_if = if_node
                else:
                    current_if.orelse = [if_node]
                current_if = if_node

        if first_if is None:
            return [subj_assign] + (current_if.orelse if current_if else [])

        self.generic_visit(subj_assign)
        transformed_if = self.visit_If(first_if)
        return [subj_assign] + transformed_if

    def visit_Break(self, node):
        call_expr = ast.Expr(value=ast.Call(func=ast.Name(id="_flare_break", ctx=ast.Load()), args=[], keywords=[]))
        ast.copy_location(call_expr, node)
        return call_expr

    def visit_Continue(self, node):
        call_expr = ast.Expr(value=ast.Call(func=ast.Name(id="_flare_continue", ctx=ast.Load()), args=[], keywords=[]))
        ast.copy_location(call_expr, node)
        return call_expr

    def visit_Try(self, node):
        self.generic_visit(node)
        return node

    def visit_While(self, node):
        class BreakContinueVisitor(ast.NodeVisitor):
            def __init__(self):
                self.has_break = False
                self.has_continue = False

            def visit_Break(self, n): self.has_break = True

            def visit_Continue(self, n): self.has_continue = True

            def visit_FunctionDef(self, n): pass

            def visit_ClassDef(self, n): pass

            def visit_While(self, n): pass

            def visit_For(self, n): pass

        visitor = BreakContinueVisitor()
        for stmt in node.body:
            visitor.visit(stmt)
        has_break, has_continue = visitor.has_break, visitor.has_continue

        self.generic_visit(node)

        name_cond = self.gen_name()
        name_body = self.gen_name()

        cond_func = ast.FunctionDef(name=name_cond,
                                    args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[],
                                                       defaults=[]), body=[ast.Return(value=node.test)],
                                    decorator_list=[])
        ast.copy_location(cond_func, node)

        body_func = ast.FunctionDef(name=name_body,
                                    args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[],
                                                       defaults=[]), body=node.body if node.body else [ast.Pass()],
                                    decorator_list=[])
        ast.copy_location(body_func, node)

        funcs = [cond_func, body_func]
        orelse_arg = ast.Constant(value=None)

        if node.orelse:
            name_orelse = self.gen_name()
            orelse_func = ast.FunctionDef(name=name_orelse,
                                          args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[],
                                                             defaults=[]), body=node.orelse, decorator_list=[])
            ast.copy_location(orelse_func, node)
            funcs.append(orelse_func)
            orelse_arg = ast.Name(id=name_orelse, ctx=ast.Load())

        call_expr = ast.Expr(value=ast.Call(func=ast.Name(id="_flare_while", ctx=ast.Load()),
                                            args=[ast.Name(id=name_cond, ctx=ast.Load()),
                                                  ast.Name(id=name_body, ctx=ast.Load())],
                                            keywords=[ast.keyword(arg="orelse_func", value=orelse_arg),
                                                      ast.keyword(arg="has_break", value=ast.Constant(value=has_break)),
                                                      ast.keyword(arg="has_continue",
                                                                  value=ast.Constant(value=has_continue))]))
        ast.copy_location(call_expr, node)
        funcs.append(call_expr)

        return funcs

    def visit_For(self, node):
        class BreakContinueVisitor(ast.NodeVisitor):
            def __init__(self):
                self.has_break = False
                self.has_continue = False

            def visit_Break(self, n): self.has_break = True

            def visit_Continue(self, n): self.has_continue = True

            def visit_FunctionDef(self, n): pass

            def visit_ClassDef(self, n): pass

            def visit_While(self, n): pass

            def visit_For(self, n): pass

        visitor = BreakContinueVisitor()
        for stmt in node.body:
            visitor.visit(stmt)
        has_break, has_continue = visitor.has_break, visitor.has_continue

        self.generic_visit(node)

        name_body = self.gen_name()

        if isinstance(node.target, ast.Name):
            args = [ast.arg(arg=node.target.id)]
        elif isinstance(node.target, ast.Tuple) or isinstance(node.target, ast.List):
            arg_name = self.gen_name()
            args = [ast.arg(arg=arg_name)]
            unpack_stmt = ast.Assign(targets=[node.target], value=ast.Name(id=arg_name, ctx=ast.Load()))
            ast.copy_location(unpack_stmt, node.target)
            node.body.insert(0, unpack_stmt)
        else:
            arg_name = self.gen_name()
            args = [ast.arg(arg=arg_name)]

        body_func = ast.FunctionDef(name=name_body,
                                    args=ast.arguments(posonlyargs=[], args=args, kwonlyargs=[], kw_defaults=[],
                                                       defaults=[]), body=node.body if node.body else [ast.Pass()],
                                    decorator_list=[])
        ast.copy_location(body_func, node)

        funcs = [body_func]
        orelse_arg = ast.Constant(value=None)

        if node.orelse:
            name_orelse = self.gen_name()
            orelse_func = ast.FunctionDef(name=name_orelse,
                                          args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[],
                                                             defaults=[]), body=node.orelse, decorator_list=[])
            ast.copy_location(orelse_func, node)
            funcs.append(orelse_func)
            orelse_arg = ast.Name(id=name_orelse, ctx=ast.Load())

        call_expr = ast.Expr(value=ast.Call(func=ast.Name(id="_flare_for", ctx=ast.Load()),
                                            args=[node.iter, ast.Name(id=name_body, ctx=ast.Load())],
                                            keywords=[ast.keyword(arg="orelse_func", value=orelse_arg),
                                                      ast.keyword(arg="has_break", value=ast.Constant(value=has_break)),
                                                      ast.keyword(arg="has_continue",
                                                                  value=ast.Constant(value=has_continue))]))
        ast.copy_location(call_expr, node)
        funcs.append(call_expr)

        return funcs

    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) > 1:
            comps = []
            curr_left = node.left
            for op, comp in zip(node.ops, node.comparators):
                single_comp = ast.Compare(left=curr_left, ops=[op], comparators=[comp])
                ast.copy_location(single_comp, node)
                comps.append(single_comp)
                curr_left = comp

            bool_op = ast.BoolOp(op=ast.And(), values=comps)
            ast.copy_location(bool_op, node)
            return self.visit(bool_op)

        if len(node.ops) == 1:
            if isinstance(node.ops[0], ast.In):
                call_expr = ast.Call(func=ast.Name(id="_flare_in", ctx=ast.Load()),
                                     args=[node.left, node.comparators[0]], keywords=[])
                ast.copy_location(call_expr, node)
                return call_expr
            elif isinstance(node.ops[0], ast.NotIn):
                call_expr = ast.Call(func=ast.Name(id="_flare_notin", ctx=ast.Load()),
                                     args=[node.left, node.comparators[0]], keywords=[])
                ast.copy_location(call_expr, node)
                return call_expr
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not):
            call_expr = ast.Call(func=ast.Name(id="_flare_not", ctx=ast.Load()), args=[node.operand], keywords=[])
            ast.copy_location(call_expr, node)
            return call_expr
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.And):
            func_name = "_flare_and"
        elif isinstance(node.op, ast.Or):
            func_name = "_flare_or"
        else:
            return node

        args = []
        for val in node.values:
            lam = ast.Lambda(args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
                             body=val)
            ast.copy_location(lam, val)
            args.append(lam)

        call_expr = ast.Call(func=ast.Name(id=func_name, ctx=ast.Load()), args=args, keywords=[])
        ast.copy_location(call_expr, node)
        return call_expr

    def visit_Assign(self, node):
        self.generic_visit(node)

        if len(node.targets) > 1:
            tmp_name = self.gen_name()
            assign_tmp = ast.Assign(targets=[ast.Name(id=tmp_name, ctx=ast.Store())], value=node.value)
            ast.copy_location(assign_tmp, node)
            new_assigns = [assign_tmp]

            for target in reversed(node.targets):
                single_assign = ast.Assign(targets=[target], value=ast.Name(id=tmp_name, ctx=ast.Load()))
                ast.copy_location(single_assign, node)
                res = self.visit_Assign(single_assign)
                if isinstance(res, list):
                    new_assigns.extend(res)
                else:
                    new_assigns.append(res)
            return new_assigns

        if len(node.targets) == 1:
            if isinstance(node.targets[0], ast.Name):
                var_name = node.targets[0].id
                is_local_val = self.in_flare_func

                call_expr = ast.Call(func=ast.Name(id="_flare_assign", ctx=ast.Load()),
                                     args=[ast.Constant(value=var_name), node.value,
                                           ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]),
                                           ast.Call(func=ast.Name(id="globals", ctx=ast.Load()), args=[], keywords=[]),
                                           ast.Constant(value=is_local_val)], keywords=[])

                new_assign = ast.Assign(targets=[ast.Name(id=var_name, ctx=ast.Store())], value=call_expr)
                ast.copy_location(new_assign, node)
                return new_assign

            elif isinstance(node.targets[0], ast.Tuple):
                tmp_name = self.gen_name()
                is_local_val = self.in_flare_func

                assign_tmp = ast.Assign(targets=[ast.Name(id=tmp_name, ctx=ast.Store())], value=node.value)
                ast.copy_location(assign_tmp, node)

                new_assigns = [assign_tmp]

                for i, elt in enumerate(node.targets[0].elts):
                    if isinstance(elt, ast.Name):
                        var_name = elt.id
                        subscript = ast.Subscript(value=ast.Name(id=tmp_name, ctx=ast.Load()),
                                                  slice=ast.Constant(value=i), ctx=ast.Load())

                        call_expr = ast.Call(func=ast.Name(id="_flare_assign", ctx=ast.Load()),
                                             args=[ast.Constant(value=var_name), subscript,
                                                   ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[],
                                                            keywords=[]),
                                                   ast.Call(func=ast.Name(id="globals", ctx=ast.Load()), args=[],
                                                            keywords=[]), ast.Constant(value=is_local_val)],
                                             keywords=[])

                        new_assign = ast.Assign(targets=[ast.Name(id=var_name, ctx=ast.Store())], value=call_expr)
                        ast.copy_location(new_assign, node)
                        new_assigns.append(new_assign)
                    else:
                        return node

                return new_assigns

        return node

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        if isinstance(node.target, ast.Name):
            var_name = node.target.id
            op_map = {ast.Add: "Add", ast.Sub: "Sub", ast.Mult: "Mult", ast.Div: "Div", ast.Mod: "Mod"}
            if type(node.op) in op_map:
                method = op_map[type(node.op)]
                call_expr = ast.Call(func=ast.Name(id="_flare_aug_assign", ctx=ast.Load()),
                                     args=[ast.Constant(value=var_name), ast.Constant(value=method), node.value,
                                           ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]),
                                           ast.Call(func=ast.Name(id="globals", ctx=ast.Load()), args=[], keywords=[])],
                                     keywords=[])
                expr = ast.Expr(value=call_expr)
                ast.copy_location(expr, node)
                return expr
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "success" and node.args:
            arg = node.args[0]
            if not isinstance(arg, ast.Lambda):
                node.args[0] = ast.Lambda(
                    args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]), body=arg)
                ast.copy_location(node.args[0], arg)
        return node

    def visit_Return(self, node):
        self.generic_visit(node)

        value = node.value if node.value is not None else ast.Constant(value=None)

        lambda_node = ast.Lambda(
            args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]), body=value)

        if_node = ast.If(test=ast.Compare(
            left=ast.Attribute(value=ast.Name(id="ctx", ctx=ast.Load()), attr="current_file", ctx=ast.Load()),
            ops=[ast.IsNot()], comparators=[ast.Constant(value=None)]), body=[ast.Expr(
            value=ast.Call(func=ast.Name(id="_flare_return", ctx=ast.Load()), args=[lambda_node], keywords=[])),
            ast.Raise(exc=ast.Call(
                func=ast.Attribute(value=ast.Name(id="ctx", ctx=ast.Load()), attr="FlareReturnException",
                                   ctx=ast.Load()), args=[], keywords=[]), cause=None)],
            orelse=[ast.Return(value=value)])
        ast.copy_location(if_node, node)

        return if_node

    def visit_With(self, node):
        self.generic_visit(node)

        name_body = self.gen_name()

        call_args = []
        assigns_outer = []
        assigns_inner = []
        for item in node.items:
            tmp_name = self.gen_name()
            assigns_outer.append(ast.Assign(targets=[ast.Name(id=tmp_name, ctx=ast.Store())], value=item.context_expr))

            if item.optional_vars:
                assigns_inner.append(ast.Assign(targets=[item.optional_vars],
                                                value=ast.Call(func=ast.Name(id="_flare_as_var", ctx=ast.Load()),
                                                               args=[ast.Name(id=tmp_name, ctx=ast.Load())],
                                                               keywords=[])))

            call_args.append(ast.Name(id=tmp_name, ctx=ast.Load()))

        body_func = ast.FunctionDef(name=name_body,
                                    args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[],
                                                       defaults=[]),
                                    body=assigns_inner + (node.body if node.body else [ast.Pass()]), decorator_list=[])
        ast.copy_location(body_func, node)

        call_args.append(ast.Name(id=name_body, ctx=ast.Load()))

        call_expr = ast.Expr(
            value=ast.Call(func=ast.Name(id="_flare_with", ctx=ast.Load()), args=call_args, keywords=[]))
        ast.copy_location(call_expr, node)

        return assigns_outer + [body_func, call_expr]


COMMAND_KEYWORDS = "advancement|attribute|ban|ban-ip|banlist|bossbar|clear|clone|damage|data|datapack|debug|defaultgamemode|deop|dialog|difficulty|effect|enchant|execute|experience|fetchprofile|fill|fillbiome|forceload|function|gamemode|gamerule|give|help|item|jfr|kick|kill|list|locate|loot|me|msg|op|pardon|pardon-ip|particle|perf|place|playsound|publish|random|recipe|reload|ride|rotate|save-all|save-off|save-on|say|schedule|scoreboard|seed|setblock|setidletimeout|setworldspawn|spawnpoint|spectate|spreadplayers|stop|stopsound|stopwatch|summon|swing|tag|team|teammsg|teleport|tell|tellraw|test|tick|time|title|tm|tp|transfer|trigger|unpublish|version|w|waypoint|weather|whitelist|worldborder|xp"
COMMAND_KEYWORDS_SET = set(COMMAND_KEYWORDS.split("|"))

COMMAND_RE = re.compile(r"^(\s*)(/?(?:" + COMMAND_KEYWORDS + r")\b|/\S*)(.*)$")


def evaluate_implicit_coord(seq) -> bool:
    if not seq:
        return False

    if seq[0].string not in ("~", "^", "+", "-", "$") and seq[0].type not in (tokenize.NUMBER, tokenize.NAME):
        return False

    PYTHON_KEYWORDS = {"lambda", "def", "import", "from", "for", "while", "if", "elif", "else", "return", "class",
                       "with", "as", "in", "not", "and", "or", "is", "pass", "yield", "raise", "try", "except",
                       "finally", "global", "nonlocal"}

    if seq[0].string in PYTHON_KEYWORDS:
        return False

    if seq[0].type == tokenize.NAME and len(seq) > 1 and seq[1].string == "(":
        return False

    if seq[0].string == "^":
        return True

    if len(seq) > 1 and seq[0].type in (tokenize.NUMBER, tokenize.NAME):
        if seq[1].type in (tokenize.NUMBER, tokenize.NAME):
            return True
        if seq[1].string in ("~", "^"):
            return True

    seen_tilde = False
    seen_caret_or_tilde = False

    for j, t in enumerate(seq):
        if t.string == "=":
            return False

        if t.string == "~":
            if seen_tilde:
                return True
            seen_tilde = True
            seen_caret_or_tilde = True

        if t.string == "^":
            if seen_caret_or_tilde:
                return True
            seen_caret_or_tilde = True

        if j > 0:
            prev = seq[j - 1]
            if t.type in (tokenize.NUMBER, tokenize.NAME) and prev.type in (tokenize.NUMBER, tokenize.NAME):
                return True
            if t.string == "~" and prev.type in (tokenize.NUMBER, tokenize.NAME):
                return True

    return False


PYTHON_KEYWORDS = {"False", "None", "True", "and", "as", "assert", "async", "await", "break", "case", "class",
                   "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if",
                   "import", "in", "is", "lambda", "match", "nonlocal", "not", "or", "pass", "raise", "return", "try",
                   "while", "with", "yield"}


def emit_target_nbt_addr(target_type, target_str, path_tokens, out_tokens):
    target_clean = target_str.strip('"').strip("'")
    addr_str = f"{target_type} {target_clean}"

    escaped = addr_str.replace('"', '\\"')
    out_tokens.append((tokenize.NAME, "nbt"))
    out_tokens.append((tokenize.OP, "("))
    out_tokens.append((tokenize.NAME, "addr"))
    out_tokens.append((tokenize.OP, "="))
    out_tokens.append((tokenize.STRING, f'"{escaped}"'))
    out_tokens.append((tokenize.OP, ")"))

    if path_tokens:
        out_tokens.append((tokenize.OP, "."))
        prev_is_dot = True
        for pt in path_tokens:
            if pt.type == tokenize.NUMBER and pt.string.startswith("."):
                num_str = pt.string.lstrip(".")
                if out_tokens and out_tokens[-1] == (tokenize.OP, "."):
                    out_tokens.pop()
                out_tokens.append((tokenize.OP, "["))
                out_tokens.append((tokenize.NUMBER, num_str))
                out_tokens.append((tokenize.OP, "]"))
                prev_is_dot = False
            elif pt.type == tokenize.STRING and prev_is_dot:
                if out_tokens and out_tokens[-1] == (tokenize.OP, "."):
                    out_tokens.pop()
                out_tokens.append((tokenize.OP, "["))
                out_tokens.append((tokenize.STRING, pt.string))
                out_tokens.append((tokenize.OP, "]"))
                prev_is_dot = False
            else:
                out_tokens.append((pt.type, pt.string))
                prev_is_dot = (pt.type == tokenize.OP and pt.string == ".")


def preprocess_minecraft_commands(source: str) -> str:
    source = re.sub(r'import\s+([a-zA-Z0-9_]+:[a-zA-Z0-9_/]+)\s+as\s+([a-zA-Z0-9_]+)', r'\2 = Function("\1")', source)

    def _repl_from_as(m):
        ns = m.group(1)
        func = m.group(2)
        alias = m.group(3)
        return f'{alias} = Function("{ns}/{func}")'

    def _repl_from(m):
        ns = m.group(1)
        func = m.group(2)
        return f'{func} = Function("{ns}/{func}")'

    source = re.sub(r'from\s+([a-zA-Z0-9_]+:[a-zA-Z0-9_/]+)\s+import\s+([a-zA-Z0-9_]+)\s+as\s+([a-zA-Z0-9_]+)',
                    _repl_from_as, source)
    source = re.sub(r'from\s+([a-zA-Z0-9_]+:[a-zA-Z0-9_/]+)\s+import\s+([a-zA-Z0-9_]+)(?!\s+as)', _repl_from, source)
    lines = source.split("\n")

    skip_lines = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.STRING and tok.start[0] < tok.end[0]:
                for line_num in range(tok.start[0] + 1, tok.end[0] + 1):
                    skip_lines.add(line_num)
    except (tokenize.TokenError, IndentationError):
        pass

    bracket_matches = {"}": "{", "]": "[", ")": "("}

    i = 0
    while i < len(lines):
        bracket_counts = {"{": 0, "[": 0, "(": 0}
        line_num = i + 1
        if line_num in skip_lines:
            i += 1
            continue

        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        match = COMMAND_RE.match(line)
        if match:
            if re.match(r"^\s*(?:" + COMMAND_KEYWORDS + r")\s*(?:[+\-*/%&|^]?=|\()", line):
                i += 1
                continue
            if re.match(r"^\s*(?:" + COMMAND_KEYWORDS + r")\s*\.", line):
                i += 1
                continue

            indent = match.group(1)
            cmd = match.group(2) + match.group(3)
            if cmd.startswith("/"):
                cmd = cmd[1:]

            in_string = False
            escape = False
            cmd_lines = []

            start_i = i

            while i < len(lines):
                current_line = lines[i]
                cmd_lines.append(current_line)

                for char in current_line:
                    if escape:
                        escape = False
                        continue
                    if char == "\\":
                        escape = True
                        continue
                    if char in ('"', "'"):
                        if in_string == char:
                            in_string = False
                        elif not in_string:
                            in_string = char
                        continue

                    if not in_string:
                        if char in bracket_counts:
                            bracket_counts[char] += 1
                        elif char in bracket_matches:
                            opener = bracket_matches[char]
                            if bracket_counts[opener] > 0:
                                bracket_counts[opener] -= 1

                if sum(bracket_counts.values()) == 0:
                    break
                i += 1

            cmd_lines[0] = cmd
            full_cmd = " ".join([c.strip() for c in cmd_lines])

            if '"""' in full_cmd:
                lines[start_i] = f"{indent}runcommand('''{full_cmd}''', locals(), globals())"
            else:
                lines[start_i] = f'{indent}runcommand("""{full_cmd}""", locals(), globals())'

            for j in range(start_i + 1, min(i + 1, len(lines))):
                lines[j] = ""

        i += 1

    intermediate_source = "\n".join(lines)
    intermediate_source = re.sub(r'(?<![0-9a-zA-Z_])0([bB])(?![01a-fA-F])', r'snbt(0, "\1")', intermediate_source)

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(intermediate_source).readline))
    except (tokenize.TokenError, IndentationError):
        return intermediate_source

    out_tokens = []
    i = 0
    nbt_depths = []
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == tokenize.NAME and tok.string == "nbt":
            j = i + 1
            while j < len(tokens) and tokens[j].type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                                         tokenize.DEDENT):
                j += 1
            if j < len(tokens) and tokens[j].type == tokenize.OP and tokens[j].string == "{":
                out_tokens.append((tokenize.NAME, "nbt"))
                out_tokens.append((tokenize.OP, "("))
                nbt_depths.append(0)
                i = j
                tok = tokens[i]

        if nbt_depths:
            if tok.type == tokenize.OP and tok.string == "{":
                nbt_depths[-1] += 1
            elif tok.type == tokenize.OP and tok.string == "}":
                nbt_depths[-1] -= 1
                if nbt_depths[-1] == 0:
                    nbt_depths.pop()
                    out_tokens.append((tok.type, tok.string))
                    out_tokens.append((tokenize.OP, ")"))
                    i += 1
                    continue

        if nbt_depths and tok.type == tokenize.NAME:
            j = i + 1
            while j < len(tokens) and tokens[j].type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                                         tokenize.DEDENT):
                j += 1
            if j < len(tokens) and tokens[j].type == tokenize.OP and tokens[j].string == ":":
                out_tokens.append((tokenize.STRING, f'"{tok.string}"'))
                i += 1
                continue

        if tok.type == tokenize.NAME and tok.string == "store":
            j = i + 1
            while j < len(tokens) and tokens[j].type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                                         tokenize.DEDENT):
                j += 1
            if j < len(tokens) and tokens[j].type == tokenize.OP and tokens[j].string == "(":
                bracket_count = 1
                curr = j + 1
                inside_tokens = []
                op_index = -1
                op_name_map = {"=": "iset", "+=": "iadd", "-=": "isub", "*=": "imul", "/=": "idiv", "//=": "idiv",
                               "%=": "imod"}
                op_found = None
                while curr < len(tokens) and bracket_count > 0:
                    inner_tok = tokens[curr]
                    if inner_tok.type == tokenize.OP:
                        if inner_tok.string in ("(", "{", "["):
                            bracket_count += 1
                        elif inner_tok.string in (")", "}", "]"):
                            bracket_count -= 1
                            if bracket_count == 0:
                                break
                        elif bracket_count == 1 and inner_tok.string in op_name_map:
                            op_index = len(inside_tokens)
                            op_found = op_name_map[inner_tok.string]
                    inside_tokens.append(inner_tok)
                    curr += 1

                if bracket_count == 0 and op_index > 0 and op_found:
                    var_toks = inside_tokens[:op_index]
                    val_toks = inside_tokens[op_index + 1:]

                    out_tokens.append((tokenize.NAME, "store"))
                    out_tokens.append((tokenize.OP, "("))
                    for vt in var_toks:
                        out_tokens.append((vt.type, vt.string))
                    out_tokens.append((tokenize.OP, ")"))
                    out_tokens.append((tokenize.OP, "."))
                    out_tokens.append((tokenize.NAME, op_found))
                    out_tokens.append((tokenize.OP, "("))
                    for vt in val_toks:
                        out_tokens.append((vt.type, vt.string))
                    out_tokens.append((tokenize.OP, ")"))

                    i = curr + 1
                    continue

        if tok.type == tokenize.NAME and tok.string in ("success", "store"):
            j = i + 1
            while j < len(tokens) and tokens[j].type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                                         tokenize.DEDENT):
                j += 1
            if j < len(tokens) and tokens[j].type == tokenize.OP and tokens[j].string == "(":
                k = j + 1
                while k < len(tokens) and tokens[k].type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                                             tokenize.DEDENT):
                    k += 1
                if k < len(tokens) and tokens[k].type == tokenize.NAME and tokens[k].string in COMMAND_KEYWORDS_SET:
                    bracket_count = 1
                    curr = k + 1
                    arg_tokens = [tokens[k]]
                    while curr < len(tokens) and bracket_count > 0:
                        inner_tok = tokens[curr]
                        if inner_tok.type == tokenize.OP:
                            if inner_tok.string in ("(", "{", "["):
                                bracket_count += 1
                            elif inner_tok.string in (")", "}", "]"):
                                bracket_count -= 1
                                if bracket_count == 0:
                                    break
                        arg_tokens.append(inner_tok)
                        curr += 1

                    if bracket_count == 0 and arg_tokens:
                        start_row, start_col = arg_tokens[0].start
                        end_row, end_col = arg_tokens[-1].end
                        lines_arr = intermediate_source.split("\n")
                        if start_row == end_row:
                            cmd_str = lines_arr[start_row - 1][start_col:end_col]
                        else:
                            parts = [lines_arr[start_row - 1][start_col:]]
                            for r in range(start_row, end_row - 1):
                                parts.append(lines_arr[r])
                            parts.append(lines_arr[end_row - 1][:end_col])
                            cmd_str = " ".join(p.strip() for p in parts if p.strip())

                        out_tokens.append((tokenize.NAME, tok.string))
                        out_tokens.append((tokenize.OP, "("))
                        out_tokens.append((tokenize.NAME, "lambda"))
                        out_tokens.append((tokenize.OP, ":"))
                        out_tokens.append((tokenize.NAME, "runcommand"))
                        out_tokens.append((tokenize.OP, "("))
                        cmd_str_esc = cmd_str.replace('"""', '\\"\\"\\"')
                        out_tokens.append((tokenize.STRING, f'"""{cmd_str_esc}"""'))
                        out_tokens.append((tokenize.OP, ","))
                        out_tokens.append((tokenize.NAME, "locals"))
                        out_tokens.append((tokenize.OP, "("))
                        out_tokens.append((tokenize.OP, ")"))
                        out_tokens.append((tokenize.OP, ","))
                        out_tokens.append((tokenize.NAME, "globals"))
                        out_tokens.append((tokenize.OP, "("))
                        out_tokens.append((tokenize.OP, ")"))
                        out_tokens.append((tokenize.OP, ")"))

                        i = curr
                        continue

        if tok.type == tokenize.NUMBER:
            if i + 1 < len(tokens):
                next_tok = tokens[i + 1]
                if next_tok.type == tokenize.NAME and tok.end == next_tok.start:
                    if next_tok.string in "bBsSlLfFdD":
                        out_tokens.append((tokenize.NAME, "snbt"))
                        out_tokens.append((tokenize.OP, "("))
                        out_tokens.append((tokenize.NUMBER, tok.string))
                        out_tokens.append((tokenize.OP, ","))
                        out_tokens.append((tokenize.STRING, f'"{next_tok.string}"'))
                        out_tokens.append((tokenize.OP, ")"))
                        i += 2
                        continue

        if tok.type == tokenize.NAME and tok.string.startswith("b"):
            is_b_coord = False
            rest = tok.string[1:]

            if not rest:
                if i + 1 < len(tokens):
                    next_tok = tokens[i + 1]
                    if next_tok.string in ("~", "^", "$") or (
                            next_tok.type == tokenize.NUMBER and next_tok.start == tok.end):
                        is_b_coord = True
            elif rest.startswith("~") or rest.startswith("^") or rest.isdigit():
                is_b_coord = True

            if is_b_coord:
                temp_i = i
                temp_bracket = 0
                collected_tokens = []
                while temp_i < len(tokens):
                    t = tokens[temp_i]
                    if t.type == tokenize.OP:
                        if t.string in ("[", "{", "("):
                            temp_bracket += 1
                        elif t.string in ("]", "}", ")"):
                            temp_bracket -= 1

                    if temp_bracket < 0:
                        break
                    if temp_bracket == 0 and t.string == ",":
                        break
                    if temp_bracket <= 0 and t.type in (tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT):
                        break

                    collected_tokens.append(t)
                    temp_i += 1

                k = 1
                modifiers = ""
                coords = []

                first_tok = collected_tokens[0]
                if first_tok.string != "b":
                    num_str = first_tok.string[1:]
                    modifiers += " "
                    coords.append(num_str)

                while k < len(collected_tokens):
                    t = collected_tokens[k]
                    if t.string in ("~", "^"):
                        mod = t.string
                        k += 1
                        num_str = "0"
                        if k < len(collected_tokens):
                            t2 = collected_tokens[k]
                            if t2.start == t.end:
                                if t2.type in (tokenize.NUMBER, tokenize.NAME):
                                    num_str = t2.string
                                    k += 1
                                elif t2.string in ("+", "-"):
                                    if k + 1 < len(collected_tokens) and collected_tokens[k + 1].start == t2.end and \
                                            collected_tokens[k + 1].type in (tokenize.NUMBER, tokenize.NAME):
                                        num_str = t2.string + collected_tokens[k + 1].string
                                        k += 2
                                elif t2.string == "$":
                                    if k + 3 < len(collected_tokens) and collected_tokens[k + 1].start == t2.end and \
                                            collected_tokens[k + 1].string == "(" and collected_tokens[
                                        k + 2].type == tokenize.NAME and collected_tokens[k + 3].string == ")":
                                        num_str = f"$({collected_tokens[k + 2].string})"
                                        k += 4
                        modifiers += mod
                        coords.append(num_str)
                    elif t.type in (tokenize.NUMBER, tokenize.NAME):
                        modifiers += " "
                        coords.append(t.string)
                        k += 1
                    elif t.string in ("+", "-"):
                        if k + 1 < len(collected_tokens) and collected_tokens[k + 1].start == t.end and \
                                collected_tokens[k + 1].type in (tokenize.NUMBER, tokenize.NAME):
                            modifiers += " "
                            coords.append(t.string + collected_tokens[k + 1].string)
                            k += 2
                        else:
                            break
                    elif t.string == "$":
                        if k + 3 < len(collected_tokens) and collected_tokens[k + 1].start == t.end and \
                                collected_tokens[k + 1].string == "(" and collected_tokens[
                            k + 2].type == tokenize.NAME and collected_tokens[k + 3].string == ")":
                            modifiers += " "
                            coords.append(f"$({collected_tokens[k + 2].string})")
                            k += 4
                        else:
                            break
                    else:
                        break

                has_tilde_or_caret = any(t.string in ("~", "^") for t in collected_tokens)
                if len(coords) >= 2 and (has_tilde_or_caret or first_tok.string == "b"):
                    out_tokens.append((tokenize.NAME, "block"))
                    out_tokens.append((tokenize.OP, "("))
                    out_tokens.append((tokenize.NAME, "ref"))
                    out_tokens.append((tokenize.OP, "="))
                    out_tokens.append((tokenize.STRING, f'"{modifiers}"'))
                    out_tokens.append((tokenize.OP, ","))
                    out_tokens.append((tokenize.NAME, "v"))
                    out_tokens.append((tokenize.OP, "="))
                    out_tokens.append((tokenize.OP, "["))
                    for j, c in enumerate(coords):
                        if j > 0:
                            out_tokens.append((tokenize.OP, ","))
                        if c.startswith("$("):
                            out_tokens.append((tokenize.STRING, f'"{c}"'))
                        elif c.replace('.', '', 1).replace('-', '', 1).replace('+', '', 1).isdigit():
                            out_tokens.append((tokenize.NUMBER, c))
                        else:
                            out_tokens.append((tokenize.NAME, c))
                    out_tokens.append((tokenize.OP, "]"))
                    out_tokens.append((tokenize.OP, ")"))

                    i += k
                    continue

        if tok.type == tokenize.OP and tok.string == "[":
            if i + 2 < len(tokens):
                t1 = tokens[i + 1]
                t2 = tokens[i + 2]
                if t1.type == tokenize.NAME and t1.string.upper() in "BIL" and t2.type == tokenize.OP and t2.string == ";":
                    arr_prefix = t1.string.upper()
                    bracket_depth = 1
                    inside_tokens = []
                    scan_idx = i + 3
                    while scan_idx < len(tokens) and bracket_depth > 0:
                        st = tokens[scan_idx]
                        if st.type == tokenize.OP:
                            if st.string in ("[", "{", "("):
                                bracket_depth += 1
                            elif st.string in ("]", "}", ")"):
                                bracket_depth -= 1
                                if bracket_depth == 0:
                                    break
                        inside_tokens.append(st)
                        scan_idx += 1

                    if bracket_depth == 0:
                        out_tokens.append((tokenize.NAME, "_snbt_array"))
                        out_tokens.append((tokenize.OP, "("))
                        out_tokens.append((tokenize.STRING, f'"{arr_prefix}"'))
                        out_tokens.append((tokenize.OP, ","))
                        out_tokens.append((tokenize.OP, "["))
                        for st in inside_tokens:
                            out_tokens.append((st.type, st.string))
                        out_tokens.append((tokenize.OP, "]"))
                        out_tokens.append((tokenize.OP, ")"))
                        i = scan_idx + 1
                        continue

        if tok.type == tokenize.OP and tok.string in ("[", "{", "(", ","):
            seq = []
            temp_i = i + 1
            depth = 0
            while temp_i < len(tokens):
                t = tokens[temp_i]
                if depth == 0 and t.type in (tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT):
                    break
                if t.type == tokenize.OP:
                    if t.string in ("[", "{", "("):
                        depth += 1
                    elif t.string in ("]", "}", ")"):
                        if depth == 0:
                            break
                        depth -= 1
                    elif t.string == ",":
                        if depth == 0:
                            break
                seq.append(t)
                temp_i += 1

            if evaluate_implicit_coord(seq):
                out_tokens.append(tok)

                modifiers = ""
                coords = []
                k = 0
                while k < len(seq):
                    t = seq[k]
                    if t.string in ("~", "^"):
                        mod = t.string
                        k += 1
                        num_str = "0"
                        if k < len(seq):
                            t2 = seq[k]
                            if t2.start == t.end:
                                if t2.type in (tokenize.NUMBER, tokenize.NAME):
                                    num_str = t2.string
                                    k += 1
                                elif t2.string in ("+", "-"):
                                    if k + 1 < len(seq) and seq[k + 1].start == t2.end and seq[k + 1].type in (
                                            tokenize.NUMBER, tokenize.NAME):
                                        num_str = t2.string + seq[k + 1].string
                                        k += 2
                                elif t2.string == "$":
                                    if k + 3 < len(seq) and seq[k + 1].start == t2.end and seq[k + 1].string == "(" and \
                                            seq[k + 2].type == tokenize.NAME and seq[k + 3].string == ")":
                                        num_str = f"$({seq[k + 2].string})"
                                        k += 4
                        modifiers += mod
                        coords.append(num_str)
                    elif t.type in (tokenize.NUMBER, tokenize.NAME):
                        modifiers += " "
                        coords.append(t.string)
                        k += 1
                    elif t.string in ("+", "-"):
                        if k + 1 < len(seq) and seq[k + 1].start == t.end and seq[k + 1].type in (tokenize.NUMBER,
                                                                                                  tokenize.NAME):
                            modifiers += " "
                            coords.append(t.string + seq[k + 1].string)
                            k += 2
                        else:
                            break
                    elif t.string == "$":
                        if k + 3 < len(seq) and seq[k + 1].start == t.end and seq[k + 1].string == "(" and seq[
                            k + 2].type == tokenize.NAME and seq[k + 3].string == ")":
                            modifiers += " "
                            coords.append(f"$({seq[k + 2].string})")
                            k += 4
                        else:
                            break
                    else:
                        break

                has_tilde_or_caret_seq = any(t.string in ("~", "^") for t in seq)
                if len(coords) >= 2 and has_tilde_or_caret_seq:
                    out_tokens.append(tok)
                    out_tokens.append((tokenize.NAME, "block"))
                    out_tokens.append((tokenize.OP, "("))
                    out_tokens.append((tokenize.NAME, "ref"))
                    out_tokens.append((tokenize.OP, "="))
                    out_tokens.append((tokenize.STRING, f'"{modifiers}"'))
                    out_tokens.append((tokenize.OP, ","))
                    out_tokens.append((tokenize.NAME, "v"))
                    out_tokens.append((tokenize.OP, "="))
                    out_tokens.append((tokenize.OP, "["))
                    for i_coord, c in enumerate(coords):
                        if i_coord > 0:
                            out_tokens.append((tokenize.OP, ","))
                        if c.startswith("$("):
                            out_tokens.append((tokenize.STRING, f'"{c}"'))
                        elif c.replace('.', '', 1).replace('-', '', 1).replace('+', '', 1).isdigit():
                            out_tokens.append((tokenize.NUMBER, c))
                        else:
                            out_tokens.append((tokenize.NAME, c))
                    out_tokens.append((tokenize.OP, "]"))
                    out_tokens.append((tokenize.OP, ")"))

                    i += 1 + k
                    continue

        if tok.type == tokenize.NAME and tok.string == "as":
            is_func_or_attr = False
            if i + 1 < len(tokens) and tokens[i + 1].type == tokenize.OP and tokens[i + 1].string == "(":
                is_func_or_attr = True
            elif i > 0 and tokens[i - 1].type == tokenize.OP and tokens[i - 1].string == ".":
                is_func_or_attr = True

            if is_func_or_attr:
                out_tokens.append((tokenize.NAME, "_as"))
                i += 1
                continue

        if tok.type == tokenize.NAME and tok.string == "with":
            if i > 0 and tokens[i - 1].type == tokenize.OP and tokens[i - 1].string == ".":
                out_tokens.append((tokenize.NAME, "with_"))
                i += 1
                continue

        if tok.type == tokenize.NAME and tok.string == "if":
            if i > 0 and tokens[i - 1].type == tokenize.OP and tokens[i - 1].string == ".":
                out_tokens.append((tokenize.NAME, f"{tok.string}_"))
                i += 1
                continue

        if tok.type == tokenize.OP and tok.string == "@":
            prev_tok = None
            for j in range(i - 1, -1, -1):
                if tokens[j].type not in (tokenize.NL, tokenize.COMMENT):
                    prev_tok = tokens[j]
                    break

            is_decorator = False
            if prev_tok is None or prev_tok.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                is_decorator = True

            if i + 1 < len(tokens) and tokens[i + 1].type == tokenize.NAME:
                name_tok = tokens[i + 1]
                if name_tok.string in ("a", "e", "p", "r", "s", "n", "c"):
                    is_decorator = False

            if not is_decorator:
                if i + 1 < len(tokens) and tokens[i + 1].type == tokenize.NAME:
                    name_tok = tokens[i + 1]
                    selector_base = "@" + name_tok.string
                    selector_end_idx = i + 2

                    selector_args_str = ""
                    has_bracket_args = False
                    if selector_end_idx < len(tokens) and tokens[selector_end_idx].type == tokenize.OP and tokens[
                        selector_end_idx].string == "[":
                        bracket_i = selector_end_idx + 1
                        temp_bracket = 1
                        matching_bracket_i = -1
                        while bracket_i < len(tokens) and temp_bracket > 0:
                            t = tokens[bracket_i]
                            if t.type == tokenize.OP:
                                if t.string in ("[", "{", "("):
                                    temp_bracket += 1
                                elif t.string in ("]", "}", ")"):
                                    temp_bracket -= 1
                                    if temp_bracket == 0 and t.string == "]":
                                        matching_bracket_i = bracket_i
                            bracket_i += 1

                        if matching_bracket_i != -1:
                            has_bracket_args = True
                            selector_args_str = "".join(
                                t.string for t in tokens[selector_end_idx + 1:matching_bracket_i])
                            selector_end_idx = matching_bracket_i + 1

                    full_selector_str = selector_base + (f"[{selector_args_str}]" if has_bracket_args else "")

                    next_tok_idx = selector_end_idx
                    has_objective = False
                    obj_str = ""
                    end_obj_idx = next_tok_idx

                    if next_tok_idx < len(tokens):
                        start_tok = tokens[next_tok_idx]

                        is_obj_start = False
                        if start_tok.type == tokenize.NAME and start_tok.string not in ("in", "is", "if", "else", "for",
                                                                                        "while", "and", "or", "not",
                                                                                        "def", "class", "import",
                                                                                        "from", "return"):
                            is_obj_start = True
                        elif start_tok.type == tokenize.NUMBER:
                            is_obj_start = True
                        elif start_tok.type == tokenize.OP and start_tok.string in ("!", "-", "+", "_"):
                            is_obj_start = True
                        elif start_tok.type == tokenize.OP and start_tok.string == ".":
                            prev_end = tokens[selector_end_idx - 1].end
                            if start_tok.start != prev_end:
                                is_obj_start = True

                        if is_obj_start:
                            has_objective = True
                            obj_str = start_tok.string
                            last_end = start_tok.end
                            end_obj_idx = next_tok_idx + 1

                            while end_obj_idx < len(tokens):
                                nt = tokens[end_obj_idx]
                                if nt.start == last_end and nt.type in (tokenize.NAME, tokenize.NUMBER, tokenize.OP):
                                    if nt.type == tokenize.OP and nt.string in (",", ";", "(", ")", "[", "]", "{", "}",
                                                                                "=", "==", "!=", "<", ">", "<=", ">=",
                                                                                ":"):
                                        break
                                    obj_str += nt.string
                                    last_end = nt.end
                                    end_obj_idx += 1
                                else:
                                    break

                    if has_objective:
                        addr_str = f"{full_selector_str} {obj_str}"
                        escaped = addr_str.replace('"', '\\"')
                        out_tokens.append((tokenize.NAME, "score"))
                        out_tokens.append((tokenize.OP, "("))
                        out_tokens.append((tokenize.NAME, "addr"))
                        out_tokens.append((tokenize.OP, "="))
                        out_tokens.append((tokenize.STRING, f'"{escaped}"'))
                        out_tokens.append((tokenize.OP, ")"))
                        i = end_obj_idx
                        continue
                    else:
                        if has_bracket_args:
                            escaped_sel = selector_base.replace('"', '\\"')
                            escaped_args = selector_args_str.replace('"', '\\"')
                            out_tokens.append((tokenize.NAME, "selector"))
                            out_tokens.append((tokenize.OP, "("))
                            out_tokens.append((tokenize.STRING, f'"{escaped_sel}"'))
                            out_tokens.append((tokenize.OP, ")"))
                            out_tokens.append((tokenize.OP, "."))
                            out_tokens.append((tokenize.NAME, "__selector_index__"))
                            out_tokens.append((tokenize.OP, "("))
                            out_tokens.append((tokenize.STRING, f'"{escaped_args}"'))
                            out_tokens.append((tokenize.OP, ")"))
                            i = selector_end_idx
                            continue
                        else:
                            out_tokens.append((tokenize.NAME, "selector"))
                            out_tokens.append((tokenize.OP, "("))
                            escaped = selector_base.replace('"', '\\"')
                            out_tokens.append((tokenize.STRING, f'"{escaped}"'))
                            out_tokens.append((tokenize.OP, ")"))
                            i = i + 2
                            continue

        if tok.type == tokenize.OP and tok.string == "[":
            has_selector_arg = False
            temp_i = i + 1
            temp_bracket = 1
            matching_bracket_i = -1
            while temp_i < len(tokens) and temp_bracket > 0:
                t = tokens[temp_i]
                if t.type == tokenize.OP:
                    if t.string in ("[", "{", "("):
                        temp_bracket += 1
                    elif t.string in ("]", "}", ")"):
                        temp_bracket -= 1
                        if temp_bracket == 0 and t.string == "]":
                            matching_bracket_i = temp_i
                    elif t.string == "=" and temp_bracket == 1:
                        if temp_i - 1 >= 0 and tokens[temp_i - 1].type == tokenize.NAME:
                            has_selector_arg = True
                    elif t.string == "$" and temp_bracket == 1 and temp_i + 1 < len(tokens) and tokens[
                        temp_i + 1].string == "(":
                        has_selector_arg = True
                temp_i += 1

            is_empty = (matching_bracket_i == i + 1)

            if (has_selector_arg or is_empty) and matching_bracket_i != -1:
                inner_str = ""
                for j in range(i + 1, matching_bracket_i):
                    inner_str += tokens[j].string

                out_tokens.append((tokenize.OP, "."))
                out_tokens.append((tokenize.NAME, "__selector_index__"))
                out_tokens.append((tokenize.OP, "("))
                out_tokens.append((tokenize.STRING, f'"{escaped}"'))
                out_tokens.append((tokenize.OP, ")"))

                i = matching_bracket_i + 1
                continue

        if tok.type == tokenize.NAME and tok.string == "storage":
            next_idx = i + 1
            if next_idx < len(tokens):
                first_tok = tokens[next_idx]
                if first_tok.line == tok.line and first_tok.start > tok.end:
                    if first_tok.type in (tokenize.NAME, tokenize.NUMBER, tokenize.STRING) or (
                            first_tok.type == tokenize.OP and first_tok.string in ("!", "-", "+", "_")):
                        target_tokens = [first_tok]
                        target_end = first_tok.end
                        scan = next_idx + 1

                        while scan < len(tokens):
                            st = tokens[scan]
                            if st.start == target_end and st.type in (tokenize.NAME, tokenize.NUMBER, tokenize.OP):
                                if st.type == tokenize.OP and st.string in (",", ";", "(", ")", "[", "]", "{", "}", "=",
                                                                            "==", "!=", "<", ">", "<=", ">="):
                                    break
                                target_tokens.append(st)
                                target_end = st.end
                                scan += 1
                            else:
                                break

                        target_str = "".join(t.string for t in target_tokens)

                        path_tokens = []
                        if scan < len(tokens):
                            path_start_tok = tokens[scan]
                            if path_start_tok.line == tok.line and path_start_tok.start > target_end:
                                if (
                                        path_start_tok.type == tokenize.NAME and path_start_tok.string not in PYTHON_KEYWORDS) or path_start_tok.type in (
                                        tokenize.NUMBER, tokenize.STRING):
                                    path_curr = scan
                                    last_path_end = path_start_tok.start

                                    while path_curr < len(tokens):
                                        pt = tokens[path_curr]
                                        if pt.line != tok.line or pt.type in (tokenize.NEWLINE, tokenize.NL,
                                                                              tokenize.ENDMARKER):
                                            break
                                        if path_curr > scan and pt.start != last_path_end:
                                            if tokens[path_curr - 1].type == tokenize.OP and tokens[
                                                path_curr - 1].string == ".":
                                                pass
                                            else:
                                                break

                                        if pt.type == tokenize.OP and pt.string not in (".", "!", "-", "+", "_"):
                                            break
                                        if pt.type == tokenize.NAME and pt.string in PYTHON_KEYWORDS:
                                            break

                                        path_tokens.append(pt)
                                        last_path_end = pt.end
                                        path_curr += 1
                                    scan = path_curr

                        emit_target_nbt_addr("storage", target_str, path_tokens, out_tokens)
                        i = scan
                        continue

        if tok.type == tokenize.NAME and tok.string == "entity":
            next_idx = i + 1
            if next_idx < len(tokens):
                first_tok = tokens[next_idx]
                if first_tok.line == tok.line and first_tok.start > tok.end:
                    if first_tok.type == tokenize.OP and first_tok.string == "@":
                        if next_idx + 1 < len(tokens) and tokens[next_idx + 1].type == tokenize.NAME:
                            sel_name = tokens[next_idx + 1].string
                            selector_base = "@" + sel_name
                            sel_end_idx = next_idx + 2

                            has_bracket = False
                            sel_args_str = ""
                            if sel_end_idx < len(tokens) and tokens[sel_end_idx].type == tokenize.OP and tokens[
                                sel_end_idx].string == "[":
                                bracket_i = sel_end_idx + 1
                                temp_bracket = 1
                                matching_bracket_i = -1
                                while bracket_i < len(tokens) and temp_bracket > 0:
                                    t = tokens[bracket_i]
                                    if t.type == tokenize.OP:
                                        if t.string in ("[", "{", "("):
                                            temp_bracket += 1
                                        elif t.string in ("]", "}", ")"):
                                            temp_bracket -= 1
                                            if temp_bracket == 0 and t.string == "]":
                                                matching_bracket_i = bracket_i
                                    bracket_i += 1
                                if matching_bracket_i != -1:
                                    has_bracket = True
                                    sel_args_str = "".join(t.string for t in tokens[sel_end_idx + 1:matching_bracket_i])
                                    sel_end_idx = matching_bracket_i + 1

                            full_selector_str = selector_base + (f"[{sel_args_str}]" if has_bracket else "")

                            path_tokens = []
                            scan = sel_end_idx
                            if scan < len(tokens):
                                path_start_tok = tokens[scan]
                                if path_start_tok.line == tok.line and path_start_tok.start > tokens[
                                    sel_end_idx - 1].end:
                                    if (
                                            path_start_tok.type == tokenize.NAME and path_start_tok.string not in PYTHON_KEYWORDS) or path_start_tok.type in (
                                            tokenize.NUMBER, tokenize.STRING):
                                        path_curr = scan
                                        last_path_end = path_start_tok.start
                                        while path_curr < len(tokens):
                                            pt = tokens[path_curr]
                                            if pt.line != tok.line or pt.type in (tokenize.NEWLINE, tokenize.NL,
                                                                                  tokenize.ENDMARKER):
                                                break
                                            if path_curr > scan and pt.start != last_path_end:
                                                if tokens[path_curr - 1].type == tokenize.OP and tokens[
                                                    path_curr - 1].string == ".":
                                                    pass
                                                else:
                                                    break
                                            if pt.type == tokenize.OP and pt.string not in (".", "!", "-", "+", "_"):
                                                break
                                            if pt.type == tokenize.NAME and pt.string in PYTHON_KEYWORDS:
                                                break
                                            path_tokens.append(pt)
                                            last_path_end = pt.end
                                            path_curr += 1
                                        scan = path_curr

                            emit_target_nbt_addr("entity", full_selector_str, path_tokens, out_tokens)
                            i = scan
                            continue

        if tok.type == tokenize.NAME and tok.string == "block":
            next_idx = i + 1
            if next_idx < len(tokens):
                first_tok = tokens[next_idx]
                if first_tok.line == tok.line and first_tok.start > tok.end:
                    curr_c = next_idx

                    if first_tok.type == tokenize.NAME and first_tok.string == "b" and next_idx + 1 < len(tokens) and \
                            tokens[next_idx + 1].start == first_tok.end and tokens[next_idx + 1].string in ("~", "^"):
                        curr_c = next_idx + 1

                    coord_parts = []
                    while curr_c < len(tokens) and len(coord_parts) < 3:
                        ct = tokens[curr_c]
                        if ct.line != tok.line or ct.type in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER):
                            break

                        axis_tokens = [ct]
                        axis_end = ct.end
                        scan_a = curr_c + 1
                        while scan_a < len(tokens):
                            st = tokens[scan_a]
                            if st.start == axis_end and st.type in (tokenize.NAME, tokenize.NUMBER,
                                                                    tokenize.OP) and st.string != ".":
                                axis_tokens.append(st)
                                axis_end = st.end
                                scan_a += 1
                            else:
                                break

                        part_str = "".join(t.string for t in axis_tokens)
                        coord_parts.append(part_str)
                        curr_c = scan_a

                        if curr_c < len(tokens) and tokens[curr_c].start > axis_end:
                            pass

                    if len(coord_parts) == 3:
                        coord_str = " ".join(coord_parts)

                        path_tokens = []
                        scan = curr_c
                        if scan < len(tokens):
                            path_start_tok = tokens[scan]
                            if path_start_tok.line == tok.line and path_start_tok.start > tokens[curr_c - 1].end:
                                if (
                                        path_start_tok.type == tokenize.NAME and path_start_tok.string not in PYTHON_KEYWORDS) or path_start_tok.type in (
                                        tokenize.NUMBER, tokenize.STRING):
                                    path_curr = scan
                                    last_path_end = path_start_tok.start
                                    while path_curr < len(tokens):
                                        pt = tokens[path_curr]
                                        if pt.line != tok.line or pt.type in (tokenize.NEWLINE, tokenize.NL,
                                                                              tokenize.ENDMARKER):
                                            break
                                        if path_curr > scan and pt.start != last_path_end:
                                            if tokens[path_curr - 1].type == tokenize.OP and tokens[
                                                path_curr - 1].string == ".":
                                                pass
                                            else:
                                                break
                                        if pt.type == tokenize.OP and pt.string not in (".", "!", "-", "+", "_"):
                                            break
                                        if pt.type == tokenize.NAME and pt.string in PYTHON_KEYWORDS:
                                            break
                                        path_tokens.append(pt)
                                        last_path_end = pt.end
                                        path_curr += 1
                                    scan = path_curr

                        emit_target_nbt_addr("block", coord_str, path_tokens, out_tokens)
                        i = scan
                        continue

        out_tokens.append((tok.type, tok.string))
        i += 1

    clean_tokens = [(t[0], t[1]) for t in out_tokens]
    return tokenize.untokenize(clean_tokens)


HEADER_IMPORTS = ("from flare import *\n"
                  "from flare import context as ctx\n"
                  "from flare.command_parser import interpolate_command\n"
                  "from flare import _flare_print as print\n"
                  "from flare.variables.builtins import flare_range as range, flare_ord as ord, flare_bin as bin, flare_len as len\n"
                  "from flare.variables.core import lazy_apply\n"
                  "from flare.variables.regex import re_patch as re\n")


def setup_global_env(global_env: dict) -> dict:
    exec(HEADER_IMPORTS, global_env)
    return global_env


def transform_source(source: str, filename: str = "<compiled>"):
    src = preprocess_minecraft_commands(source)
    tree = ast.parse(src, filename)

    analyzer = CallGraphAnalyzer()
    analyzer.visit(tree)
    flare.context._recursive_functions = analyzer.get_recursive_functions()

    transformer = FlareTransformer()
    tree = transformer.visit(tree)
    ast.fix_missing_locations(tree)

    code_obj = compile(tree, filename, "exec")
    return code_obj, tree


def process_and_exec(source: str, global_env: dict, filename: str = "<compiled>"):
    setup_global_env(global_env)
    code_obj, tree = transform_source(source, filename)
    try:
        exec(code_obj, global_env)
    except FlareReturnException:
        pass
    return code_obj, tree
