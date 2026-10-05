import flare.context as ctx
from flare.preprocessor import setup_global_env, transform_source
from flare import score, selector, export, tag


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


def test_peephole_optimizer_identity_move():
    # An assignment to self should be eliminated by the peephole optimizer
    files = run_flare("""
s = score(10, addr="pack_x __pack__vars__")
s[...] = s
""")
    all_cmds = get_all_cmds(files)
    # The identity move `scoreboard players operation pack_x __pack__vars__ = pack_x __pack__vars__` must be dropped
    assert "scoreboard players operation pack_x __pack__vars__ = pack_x __pack__vars__" not in all_cmds


def test_peephole_optimizer_identity_arithmetic():
    files = run_flare("""
s = score(10, addr="pack_x __pack__vars__")
s += 0
""")
    all_cmds = get_all_cmds(files)
    # Adding 0 must be eliminated
    assert "scoreboard players add pack_x __pack__vars__ 0" not in all_cmds


def test_peephole_optimizer_dead_store():
    files = run_flare("""
s = score(0)
y = score(5)
s[...] = y
""")
    all_cmds = get_all_cmds(files)
    # The initial set of s to 0 before copying y into it is a dead store and should be eliminated
    lines = [line.strip() for line in all_cmds.splitlines() if line.strip()]
    assert "scoreboard players set pack_s __pack__vars__ 0" not in lines
    assert "scoreboard players operation pack_s __pack__vars__ = pack_y __pack__vars__" in all_cmds


def test_selector_effect_helpers():
    files = run_flare("""
p = selector("@s")
p.effect.give("speed", duration=25, amplifier=2, show_particles=False)
p.effect.clear("speed")
p.effect.clear()
""")
    all_cmds = get_all_cmds(files)
    assert "effect give @s speed 25 2 true" in all_cmds
    assert "effect clear @s speed" in all_cmds
    assert "effect clear @s" in all_cmds


def test_selector_damage_and_sound():
    files = run_flare("""
p = selector("@s")
p.damage(10, damage_type="magic", by="@e[type=zombie,limit=1]")
p.playsound("entity.experience_orb.pickup", channel="player", volume=0.8, pitch=1.2)
""")
    all_cmds = get_all_cmds(files)
    assert "damage @s 10 magic by @e[type=zombie,limit=1]" in all_cmds
    assert "playsound entity.experience_orb.pickup player @s ~ ~ ~ 0.8 1.2" in all_cmds


def test_selector_gamemode_and_xp_and_ride():
    files = run_flare("""
p = selector("@s")
p.gamemode("creative")
p.xp.add(50)
p.xp.add_levels(3)
p.ride.mount("@e[type=boat,limit=1]")
p.ride.dismount()
""")
    all_cmds = get_all_cmds(files)
    assert "gamemode creative @s" in all_cmds
    assert "experience add @s 50 points" in all_cmds
    assert "experience add @s 3 levels" in all_cmds
    assert "ride @s mount @e[type=boat,limit=1]" in all_cmds
    assert "ride @s dismount" in all_cmds


def test_tag_decorator_multiple_tags():
    files = run_flare("""
@export
@tag("minecraft:tick", "pack:game_loop")
def main():
    pass
""")
    assert "minecraft:tags/functions/tick.json" in ctx.json_files
    assert "pack:tags/functions/game_loop.json" in ctx.json_files
    tick_values = ctx.json_files["minecraft:tags/functions/tick.json"]["values"]
    loop_values = ctx.json_files["pack:tags/functions/game_loop.json"]["values"]
    assert "pack:main" in tick_values
    assert "pack:main" in loop_values


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_") and callable(test):
            print(f"Running {name}...")
            test()
            print("  PASSED")
    print("\nALL PHASE 1 TESTS PASSED SUCCESSFULLY!")
