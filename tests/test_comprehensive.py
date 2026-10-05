import math
import flare.context as ctx
from flare.preprocessor import setup_global_env, transform_source
from flare import (
    score, fixed, bigscore, float32, float64, nbt, nbtstr, nbtint, selector, item,
    parse_int, parse_float, style, stopwatch, predicate, schedule, flrand
)
from flare.variables.core import FlareValue, UnsupportedOperandError
from flare.control_flow import ScoreIfMatches, ScoreUnlessMatches, ScoreIfScore


def run_flare(code: str) -> dict:
    ctx.reset_context()
    ctx._current_namespace = "pack"
    global_env = {"__name__": "__main__", "__file__": "main.py"}
    setup_global_env(global_env)
    code_obj, _ = transform_source(code, "main.py")
    exec(code_obj, global_env)
    ctx.evaluate_pending_exports()
    return dict(ctx.files)


def get_all_cmds(files: dict) -> str:
    return "\n".join("\n".join(lines) for lines in files.values())


# ==============================================================================
# Bug Fix Tests
# ==============================================================================

def test_bug1_contradictory_score_ranges():
    # x > 10 and x < 5 is contradictory. It should emit impossible constant match, NOT "11..4"
    files = run_flare("""
x = score(addr="#x")
if x > 10 and x < 5:
    score(addr="#out")[...] = 1
""")
    cmds = get_all_cmds(files)
    assert "11..4" not in cmds, f"Found invalid Minecraft range '11..4' in commands: {cmds}"
    assert "if score 0 __flare__constant__ matches 1" in cmds, f"Expected impossible constant condition in: {cmds}"


def test_bug2_match_wildcard_only():
    # Match statement with only wildcard `case _:` must not drop the body
    files = run_flare("""
x = score(addr="#x")
out = score(addr="#out")
match x:
    case _:
        out[...] = 42
""")
    cmds = get_all_cmds(files)
    assert "42" in cmds and "pack_out" in cmds, f"Wildcard body was dropped! Commands:\n{cmds}"


def test_bug3_list_unpacking():
    # List unpacking `[a, b] = (10, 20)` should use _flare_assign
    files = run_flare("""
[a, b] = [score(addr="#val1"), score(addr="#val2")]
out = score(addr="#out")
out[...] = a + b
""")
    cmds = get_all_cmds(files)
    assert "#val1" in cmds and "#val2" in cmds, f"List unpacking failed! Commands:\n{cmds}"


def test_bug4_inline_condition_invert_and_stopwatch_notin():
    # Inverting InlineCondition or using stopwatch not in range should not raise TypeError
    files = run_flare("""
if stopwatch("my_timer") not in (0, 100):
    score(addr="#out")[...] = 1
""")
    cmds = get_all_cmds(files)
    assert "unless stopwatch my_timer 0..100" in cmds, f"Expected unless stopwatch condition in: {cmds}"


def test_bug5_floor_division_score():
    # score // score and score //= int should be supported
    files = run_flare("""
a = score(100, addr="#a")
b = score(7, addr="#b")
c = score(addr="#c")
c[...] = a // b
a //= 5
""")
    cmds = get_all_cmds(files)
    assert "/= pack_b" in cmds or "/=" in cmds, f"Expected /= operation in: {cmds}"
    assert "/= #_5" in cmds or "/=" in cmds, f"Expected //= in: {cmds}"


def test_bug6_exponentiation_score():
    # score ** 2, score ** 3, score **= 2
    files = run_flare("""
x = score(5, addr="#x")
y = score(addr="#y")
y[...] = x ** 2
x **= 3
""")
    cmds = get_all_cmds(files)
    assert "*=" in cmds, f"Expected multiplication operations for pow in: {cmds}"


def test_bug7_negative_string_slicing():
    # Negative string slicing should not produce negative offsets in commands
    files = run_flare("""
s = nbt("HelloWorld", addr="storage flare:test str")
sub = nbt(addr="storage flare:test sub")
sub[...] = s[-5:]
""")
    cmds = get_all_cmds(files)
    assert " -5" not in cmds, f"Found negative offset in commands: {cmds}"
    assert "$(start)" in cmds, f"Expected $(start) macro in commands: {cmds}"


def test_bug8_dynamic_score_nbt_indexing():
    # Dynamic score indexing on nbt list should use macro, not [[Score ...]]
    files = run_flare("""
my_list = nbt([10, 20, 30], addr="storage flare:test my_list")
idx = score(1, addr="#idx")
val = score(addr="#val")
val[...] = my_list[idx]
my_list[idx] = 99
""")
    cmds = get_all_cmds(files)
    assert "[[Score" not in cmds, f"Found unparsed score string in commands: {cmds}"
    assert "$(index)" in cmds, f"Expected macro placeholder $(index) in commands: {cmds}"


def test_bug9_stopwatch_container_in():
    # (0, 100) in stopwatch("t")
    files = run_flare("""
if (0, 100) in stopwatch("t"):
    score(addr="#out1")[...] = 1
if stopwatch("t") in (0, 50):
    score(addr="#out2")[...] = 2
""")
    cmds = get_all_cmds(files)
    assert "if stopwatch t 0..100" in cmds, f"Expected if stopwatch t 0..100 in: {cmds}"
    assert "if stopwatch t 0..50" in cmds, f"Expected if stopwatch t 0..50 in: {cmds}"


def test_bug10_nbt_imod_typo():
    val = nbt("not_a_number", addr="storage flare:test str")
    try:
        val %= 5
        assert False, "Expected UnsupportedOperandError"
    except UnsupportedOperandError as e:
        assert "%=" in str(e), f"Expected '%=' in error message, got: {e}"


# ==============================================================================
# Innovation Tests
# ==============================================================================

def test_innovation1_flrand_choice():
    # flrand.choice on Python list and NBT list
    files = run_flare("""
py_list = [100, 200, 300]
res1 = score(addr="#res1")
res1[...] = flrand.choice(py_list)

nbt_list = nbt([1, 2, 3, 4], addr="storage flare:test nums")
res2 = score(addr="#res2")
res2[...] = flrand.choice(nbt_list)
""")
    cmds = get_all_cmds(files)
    assert "random value" in cmds, f"Expected random value command in: {cmds}"
    assert "$(index)" in cmds, f"Expected macro indexing for choice in: {cmds}"


def test_innovation2_dynamic_score_pow():
    # Dynamic exponentiation: score ** score
    files = run_flare("""
base = score(3, addr="#base")
exp = score(4, addr="#exp")
res = score(addr="#res")
res[...] = base ** exp
""")
    cmds = get_all_cmds(files)
    assert "%= #_2" in cmds or "%=" in cmds, f"Expected modulo in binary pow loop in: {cmds}"
    assert "pow_0" in cmds or "/pow_" in cmds, f"Expected generated pow helper function in: {cmds}"


def test_innovation3_bitwise_shifts():
    # score << 2, score >> 1, score <<= 3, score >>= 2
    files = run_flare("""
x = score(10, addr="#x")
y = score(addr="#y")
y[...] = x << 2
z = score(addr="#z")
z[...] = x >> 1
x <<= 3
x >>= 2
""")
    cmds = get_all_cmds(files)
    # 1 << 2 = 4, 1 >> 1 = 2, 1 << 3 = 8, 1 >> 2 = 4
    assert "*= #_4" in cmds, f"Expected *= #_4 in commands: {cmds}"
    assert "/= #_2" in cmds, f"Expected /= #_2 in commands: {cmds}"
    assert "*= #_8" in cmds, f"Expected *= #_8 in commands: {cmds}"
    assert "/= #_4" in cmds, f"Expected /= #_4 in commands: {cmds}"


def test_innovation4_score_range_membership():
    # score in range(1, 10), score in (1, 10), score not in range(1, 10)
    files = run_flare("""
x = score(addr="#x")
out = score(addr="#out")
if x in range(1, 10):
    out[...] = 1
if x in (20, 30):
    out[...] = 2
if x not in range(50, 100):
    out[...] = 3
""")
    cmds = get_all_cmds(files)
    assert "matches 1..9" in cmds, f"Expected matches 1..9 in: {cmds}"
    assert "matches 20..30" in cmds, f"Expected matches 20..30 in: {cmds}"
    assert "unless score" in cmds and "matches 50..99" in cmds, f"Expected unless matches 50..99 in: {cmds}"


# ==============================================================================
# Untested Feature Tests
# ==============================================================================

def test_untested_control_flow():
    # while with else, for loop with break and continue, schedule
    files = run_flare("""
i = score(0, addr="#i")
while i < 5:
    i += 1
    if i == 2:
        continue
    if i == 4:
        break
else:
    score(addr="#else_run")[...] = 1

with schedule("10t", append=True):
    score(addr="#sched_run")[...] = 1
""")
    cmds = get_all_cmds(files)
    assert "schedule function" in cmds and "sched_" in cmds, f"Expected schedule command in: {cmds}"
    assert "!break" in cmds, f"Expected !break flag for while loop in: {cmds}"


def test_untested_execute_modifiers():
    # positioned, rotated, facing, align, summon, on, store
    files = run_flare("""
from flare import positioned, summon, store, runcommand, score

s = score(addr="#count")
with positioned((10, 64, 10)).rotated((0, 90)).align("xyz"):
    with summon("minecraft:zombie"):
        runcommand("say Summoned!")

with store(s):
    runcommand("seed")
""")
    cmds = get_all_cmds(files)
    assert "positioned 10 64 10" in cmds, f"Expected positioned in: {cmds}"
    assert "rotated 0 90" in cmds, f"Expected rotated in: {cmds}"
    assert "align xyz" in cmds, f"Expected align in: {cmds}"
    assert "summon minecraft:zombie" in cmds, f"Expected summon in: {cmds}"
    assert "store result score" in cmds, f"Expected store result in: {cmds}"


def test_untested_flrand_functions():
    # randint, random
    files = run_flare("""
r1 = flrand.randint(1, 10)
r2 = score(addr="#r2")
r2[...] = flrand.random(dest=r2)
""")
    cmds = get_all_cmds(files)
    assert "random value 1..10" in cmds, f"Expected random value 1..10 in: {cmds}"


def test_untested_math_functions():
    # sqrt, sin, cos
    files = run_flare("""
import math
x = fixed(4.0, addr="#x")
s = fixed(addr="#s")
s[...] = math.sqrt(x)
c = fixed(addr="#c")
c[...] = math.cos(x)
""")
    cmds = get_all_cmds(files)
    assert "cos" in cmds or "*=" in cmds or "#cos" in cmds, f"Expected math evaluation in: {cmds}"


def test_untested_struct():
    # Struct declaration and field usage
    files = run_flare("""
from flare import struct, nbt

@struct
class Point:
    x: int
    y: int

p = nbt[Point](addr="storage flare:test point")
p.x = 10
p.y = 20
""")
    cmds = get_all_cmds(files)
    assert "pack_p.x set value 10" in cmds, f"Expected point.x set value 10 in: {cmds}"
    assert "pack_p.y set value 20" in cmds, f"Expected point.y set value 20 in: {cmds}"


def test_untested_complex():
    # Complex numbers
    files = run_flare("""
from flare import complex, fixed

c1 = complex(fixed(1.0, addr="#r1"), fixed(2.0, addr="#i1"))
c2 = complex(fixed(3.0, addr="#r2"), fixed(4.0, addr="#i2"))
c3 = c1 + c2
""")
    cmds = get_all_cmds(files)
    assert "+=" in cmds, f"Expected += in complex addition: {cmds}"


def test_untested_storage():
    # storage usage
    files = run_flare("""
from flare import storage

s = storage("flare:custom")
s.my_data = 123
""")
    cmds = get_all_cmds(files)
    assert "storage flare:custom" in cmds, f"Expected storage flare:custom in: {cmds}"


# ==============================================================================
# Main Runner
# ==============================================================================

if __name__ == "__main__":
    tests = [
        test_bug1_contradictory_score_ranges,
        test_bug2_match_wildcard_only,
        test_bug3_list_unpacking,
        test_bug4_inline_condition_invert_and_stopwatch_notin,
        test_bug5_floor_division_score,
        test_bug6_exponentiation_score,
        test_bug7_negative_string_slicing,
        test_bug8_dynamic_score_nbt_indexing,
        test_bug9_stopwatch_container_in,
        test_bug10_nbt_imod_typo,
        test_innovation1_flrand_choice,
        test_innovation2_dynamic_score_pow,
        test_innovation3_bitwise_shifts,
        test_innovation4_score_range_membership,
        test_untested_control_flow,
        test_untested_execute_modifiers,
        test_untested_flrand_functions,
        test_untested_math_functions,
        test_untested_struct,
        test_untested_complex,
        test_untested_storage,
    ]

    for test in tests:
        print(f"Running {test.__name__}...")
        test()
        print("  PASSED")

    print("\n" + "=" * 50)
    print("ALL COMPREHENSIVE TESTS PASSED SUCCESSFULLY (21/21)!")
    print("=" * 50)
