import flare.context as ctx
from flare.preprocessor import setup_global_env, transform_source
from flare import (
    score, fixed, bigscore, float32, float64, nbt, nbtstr, nbtint, selector, item,
    parse_int, parse_float, style
)
from flare.variables.core import FlareValue, lattice_type, get_lattice_rank


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
# Phase 1: Dynamic Type Lattice & Automatic Promotion
# ==============================================================================

def test_lattice_ranks():
    assert get_lattice_rank(score) == 10
    assert get_lattice_rank(fixed) == 20
    assert get_lattice_rank(bigscore) == 30
    assert get_lattice_rank(float32) == 40
    assert get_lattice_rank(float64) == 50

    @lattice_type(99)
    class CustomType(FlareValue):
        pass

    assert get_lattice_rank(CustomType) == 99
    inst = CustomType()
    assert get_lattice_rank(inst) == 99


def test_custom_lattice_type_promotion():
    @lattice_type(45)
    class CustomFloat(FlareValue):
        def __init__(self, val=0):
            self.s = score(val)
        def __implicit__(self, target_types):
            return self
        def __add__(self, other):
            from flare.variables.core import BinaryOp
            return BinaryOp(self, other, "+")
        def _compile_into(self, dest):
            self.s._compile_into(dest)

    cf = CustomFloat(10)
    s = score(5)
    op = s + cf
    # Leaf selection should pick the higher-ranked CustomFloat (rank 45 > score rank 10)
    assert isinstance(op._best_leaf(), CustomFloat)



def test_score_and_fixed_coercion():
    files = run_flare("""
s = score(10)
f = fixed(2.5)
res = s + f
""")
    all_cmds = get_all_cmds(files)
    # s is coerced to fixed (multiplied by 10000)
    assert "#_10000" in all_cmds
    assert "scoreboard players operation" in all_cmds


def test_explicit_cast():
    files = run_flare("""
s = score(42)
f = s.cast(fixed)
n = s.cast(nbtint)
""")
    all_cmds = get_all_cmds(files)
    assert "execute store result storage flare:temp" in all_cmds
    assert "data modify storage pack:vars pack_n set from storage flare:temp" in all_cmds


# ==============================================================================
# Phase 2: Runtime String Interpolation & Number-to-String Conversion
# ==============================================================================

def test_number_to_str():
    files = run_flare("""
s = score(100)
str_var = nbtstr()
str_var[...] = s
""")
    all_cmds = get_all_cmds(files)
    assert "execute store result storage flare:temp" in all_cmds
    assert "set string storage flare:temp" in all_cmds
    assert "data modify storage pack:vars pack_str_var set from" in all_cmds


def test_dynamic_fstring():
    files = run_flare("""
name = nbtstr("Steve")
s = score(50)
msg = f"Hello {name}, score: {s}!"
""")
    all_cmds = get_all_cmds(files)
    assert "format_" in all_cmds
    assert "with storage flare:macro" in all_cmds

    # Check macro function content
    macro_key = [k for k in files.keys() if "format_" in k][0]
    macro_cmds = "\n".join(files[macro_key])
    assert "$data modify storage flare:temp" in macro_cmds
    assert "$(arg_0)" in macro_cmds
    assert "$(arg_1)" in macro_cmds


# ==============================================================================
# Phase 3: Runtime String-to-Number Parsing (parse_int & parse_float)
# ==============================================================================

def test_parse_int():
    files = run_flare("""
input_val = nbtstr("-1234")
res = parse_int(input_val)
""")
    all_cmds = get_all_cmds(files)
    assert "parse_int_loop_" in all_cmds
    assert "run scoreboard players operation pack_res __pack__vars__ *= #_n1" in all_cmds

    loop_key = [k for k in files.keys() if "parse_int_loop_" in k][0]
    loop_cmds = "\n".join(files[loop_key])
    assert "parse_char_" in loop_cmds
    assert 'execute if data storage flare:temp' in loop_cmds


def test_parse_float():
    files = run_flare("""
input_val = nbtstr("3.1415")
pi = parse_float(input_val)
""")
    all_cmds = get_all_cmds(files)
    assert "parse_float_loop_" in all_cmds
    assert "parse_pad_loop_" in all_cmds


# ==============================================================================
# Phase 4: Minecraft 1.20.5+ Data Component System & Item Manipulation
# ==============================================================================

def test_item_slots_and_components():
    files = run_flare("""
s = selector("@s")
s.mainhand.custom_data.player_level = score(5)
s.mainhand.damage += 1
s.mainhand.custom_name = style("Excalibur", color="gold")
s.mainhand = item("diamond_sword", damage=10)
s.inventory[0].damage += 5
s.offhand.replace(item("shield"))
""")
    all_cmds = get_all_cmds(files)

    # custom_data
    assert 'execute store result entity @s SelectedItem.components."minecraft:custom_data".player_level int 1 run scoreboard players get' in all_cmds
    # damage += 1
    assert 'execute store result entity @s SelectedItem.components."minecraft:damage" int 1 run scoreboard players get' in all_cmds
    # custom_name
    assert 'data modify entity @s SelectedItem.components."minecraft:custom_name" set value "{\\"color\\": \\"gold\\", \\"text\\": \\"Excalibur\\"}"' in all_cmds
    # item replace weapon.mainhand
    assert 'item replace entity @s weapon.mainhand with diamond_sword[damage=10]' in all_cmds
    # inventory[0] damage += 5
    assert 'execute store result entity @s Inventory[{Slot: 0b}].components."minecraft:damage" int 1 run scoreboard players get' in all_cmds
    # item replace weapon.offhand
    assert 'item replace entity @s weapon.offhand with shield' in all_cmds


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            print(f"Running {name}...")
            func()
            print("  PASSED")
    print("\nALL INNOVATION TESTS PASSED SUCCESSFULLY!")
