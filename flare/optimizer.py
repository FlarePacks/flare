import re
from typing import List, Set, Tuple, Optional

# Match direct scoreboard set: scoreboard players set <player> <objective> <val>
_SCORE_SET_RE = re.compile(r"^scoreboard\s+players\s+set\s+(\S+)\s+(\S+)\s+(-?\d+)$")

# Match direct scoreboard add/remove: scoreboard players (add|remove) <player> <objective> <val>
_SCORE_ADD_REM_RE = re.compile(r"^scoreboard\s+players\s+(add|remove)\s+(\S+)\s+(\S+)\s+(\d+)$")

# Match direct scoreboard operation: scoreboard players operation <target_p> <target_o> <op> <source_p> <source_o>
_SCORE_OP_RE = re.compile(r"^scoreboard\s+players\s+operation\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$")

# Match data modify: data modify <target_type> <target> <path> set ...
_DATA_MODIFY_EMPTY_STR_RE = re.compile(r"^data\s+modify\s+(\S+\s+\S+\s+\S+)\s+set\s+value\s+[\"'][\"']$")
_DATA_MODIFY_RE = re.compile(r"^data\s+modify\s+(\S+\s+\S+\s+\S+)\s+set\s+(.+)$")


def is_identity_move(cmd: str) -> bool:
    """Checks if cmd is an identity move: scoreboard players operation A B = A B."""
    m = _SCORE_OP_RE.match(cmd)
    if m:
        t_p, t_o, op, s_p, s_o = m.groups()
        if op == "=" and t_p == s_p and t_o == s_o:
            return True
    return False


def is_identity_arithmetic(cmd: str) -> bool:
    """Checks if cmd is identity arithmetic like +0, -0, *1, /1."""
    m_ar = _SCORE_ADD_REM_RE.match(cmd)
    if m_ar:
        action, p, o, val = m_ar.groups()
        if val == "0":
            return True

    m_op = _SCORE_OP_RE.match(cmd)
    if m_op:
        t_p, t_o, op, s_p, s_o = m_op.groups()
        if op in ("+=", "-=") and s_p == "#_0":
            return True
        if op in ("*=", "/=") and s_p == "#_1":
            return True

    return False


def is_dead_store_pair(prev_cmd: str, curr_cmd: str) -> bool:
    """Checks if prev_cmd wrote to an address that curr_cmd unconditionally overwrites without reading."""
    m_prev_set = _SCORE_SET_RE.match(prev_cmd)
    if m_prev_set:
        p1, o1, _ = m_prev_set.groups()

        m_curr_set = _SCORE_SET_RE.match(curr_cmd)
        if m_curr_set:
            p2, o2, _ = m_curr_set.groups()
            if p1 == p2 and o1 == o2:
                return True

        m_curr_op = _SCORE_OP_RE.match(curr_cmd)
        if m_curr_op:
            p2, o2, op, s_p, s_o = m_curr_op.groups()
            if op == "=" and p1 == p2 and o1 == o2:
                if not (s_p == p1 and s_o == o1):
                    return True

    m_prev_dm = _DATA_MODIFY_EMPTY_STR_RE.match(prev_cmd)
    if m_prev_dm:
        target1 = m_prev_dm.group(1)
        m_curr_dm = _DATA_MODIFY_RE.match(curr_cmd)
        if m_curr_dm:
            target2 = m_curr_dm.group(1)
            rest = m_curr_dm.group(2)
            if target1 == target2 and target1 not in rest:
                return True

    return False


def is_barrier(cmd: str) -> bool:
    """Checks if a command is a control-flow or side-effect barrier for dead-store analysis."""
    c = cmd.strip()
    if c.startswith("execute ") or c.startswith("function ") or c.startswith("return ") or c.startswith("$"):
        return True
    return False


def get_cmd_rw(cmd: str) -> Tuple[Optional[Tuple[str, str]], Set[Tuple[str, str]]]:
    """Returns (written_var, read_vars) for direct scoreboard commands."""
    m_set = _SCORE_SET_RE.match(cmd)
    if m_set:
        p, o, _ = m_set.groups()
        return (p, o), set()

    m_op = _SCORE_OP_RE.match(cmd)
    if m_op:
        tp, to, op, sp, so = m_op.groups()
        if op == "=":
            return (tp, to), {(sp, so)}
        elif op == "><":
            return None, {(tp, to), (sp, so)}
        else:
            return (tp, to), {(tp, to), (sp, so)}

    m_ar = _SCORE_ADD_REM_RE.match(cmd)
    if m_ar:
        _, p, o, _ = m_ar.groups()
        return (p, o), {(p, o)}

    return None, set()


def eliminate_dead_stores(commands: List[str]) -> List[str]:
    """Eliminates dead stores in straight-line blocks of scoreboard commands."""
    n = len(commands)
    dead_indices = set()

    # Partition into blocks between barriers
    block_start = 0
    while block_start < n:
        block_end = block_start
        while block_end < n and not is_barrier(commands[block_end]):
            block_end += 1

        # Analyze block from block_start to block_end
        # Work backwards: keep track of variables read after the current point
        read_vars: Set[Tuple[str, str]] = set()
        written_vars: Set[Tuple[str, str]] = set()

        for i in range(block_end - 1, block_start - 1, -1):
            cmd = commands[i].strip()
            write_var, read_var_set = get_cmd_rw(cmd)

            if write_var is not None:
                # If this variable is overwritten later in the block without being read in between
                if write_var in written_vars and write_var not in read_vars:
                    dead_indices.add(i)
                else:
                    written_vars.add(write_var)

            # Update reads
            read_vars.update(read_var_set)

        block_start = block_end + 1

    return [cmd for i, cmd in enumerate(commands) if i not in dead_indices]


def optimize_commands(commands: List[str]) -> List[str]:
    """Applies a multi-pass peephole optimizer over a list of Minecraft commands."""
    if not commands:
        return []

    # Pass 1: Eliminate identity moves and zero arithmetic
    filtered = []
    for cmd in commands:
        cmd_stripped = cmd.strip()
        if not cmd_stripped or cmd_stripped.startswith("#"):
            filtered.append(cmd)
            continue

        if is_identity_move(cmd_stripped) or is_identity_arithmetic(cmd_stripped):
            continue

        filtered.append(cmd)

    # Pass 2: Dead store elimination in straight-line blocks
    return eliminate_dead_stores(filtered)
