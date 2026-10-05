import flare.context as ctx
from flare.preprocessor import setup_global_env, transform_source
from flare import vec3, StateEnum, state, selector, export


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


def test_vec3_arithmetic_and_methods():
    files = run_flare("""
v1 = vec3(10, 20, 30)
v2 = vec3(1, 2, 3)
v3 = v1 + v2
v_scaled = v1 * 2
dot_val = v1.dot(v2)
cross_vec = v1.cross(v2)
dist = v1.distance_to(v2)
""")
    all_cmds = get_all_cmds(files)
    # Check that addition, multiplication, and geometric operations emit scoreboard math
    assert "+=" in all_cmds
    assert "*=" in all_cmds
    assert "scoreboard players operation" in all_cmds


def test_vec3_entity_pos_sync():
    files = run_flare("""
v = vec3.from_entity("@s", "Pos")
v.y += 2
v.apply_to("@s", "Pos")
""")
    all_cmds = get_all_cmds(files)
    # Check entity data get and execute store result entity
    assert "execute store result score" in all_cmds
    assert "run data get entity @s Pos[0]" in all_cmds
    assert "execute store result entity @s Pos[0] double" in all_cmds


def test_state_enum_and_transitions():
    class GameState(StateEnum):
        LOBBY = 0
        ACTIVE = 1
        FINISHED = 2

    files = run_flare("""
from flare import StateEnum, state

class Phase(StateEnum):
    LOBBY = 0
    ACTIVE = 1
    FINISHED = 2

curr = state(Phase.LOBBY)
curr[...] = Phase.ACTIVE

if curr == Phase.ACTIVE:
    p = selector("@a")
    p.print("Game is active!")
""")
    all_cmds = get_all_cmds(files)
    # State should emit scoreboard operations on its objective and condition
    assert "scoreboard players set pack_curr" in all_cmds or "scoreboard players set #phase" in all_cmds
    assert "tellraw @a" in all_cmds
    assert "matches 1 run tellraw @a" in all_cmds


def test_state_enum_pattern_matching():
    files = run_flare("""
from flare import StateEnum, state, selector

class Phase(StateEnum):
    LOBBY = 0
    ACTIVE = 1
    FINISHED = 2

curr = state(Phase.ACTIVE)

match curr:
    case Phase.LOBBY:
        selector("@a").print("In lobby")
    case Phase.ACTIVE:
        selector("@a").print("In game")
    case Phase.FINISHED:
        selector("@a").print("Game over")
""")
    all_cmds = get_all_cmds(files)
    assert "matches 0 run return run tellraw @a" in all_cmds
    assert "matches 1 run return run tellraw @a" in all_cmds
    assert "matches 2 run return run tellraw @a" in all_cmds


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_") and callable(test):
            print(f"Running {name}...")
            test()
            print("  PASSED")
    print("\nALL PHASE 2 TESTS PASSED SUCCESSFULLY!")
