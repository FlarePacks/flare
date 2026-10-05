import flare.context as ctx
from flare.preprocessor import setup_global_env, transform_source
from flare import raycast, Bossbar, storage_scope, selector, score


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


def test_raycast_generation():
    files = run_flare("""
from flare import raycast, selector

def on_step():
    selector("@s").print("step")

def on_hit(target):
    target.damage(5)

def on_block(blk):
    blk.set("stone")

raycast(
    step=0.5,
    max_distance=10.0,
    on_step=on_step,
    on_hit_entity=on_hit,
    on_hit_block=on_block,
    stop_on_hit=True
)
""")
    all_cmds = get_all_cmds(files)
    # Raycast should launch step function and recurse
    assert "positioned ^ ^ ^0.5" in all_cmds
    assert "scoreboard players add #ray_dist_" in all_cmds
    assert "execute unless block ~ ~ ~ #minecraft:air" in all_cmds
    assert "damage @s 5 generic" in all_cmds
    assert "setblock ~ ~ ~ stone" in all_cmds


def test_bossbar_creation_and_binding():
    files = run_flare("""
from flare import Bossbar, score

bar = Bossbar("dragon_hp", "Ender Dragon", color="purple", style="notched_10", max_value=200, value=150)
bar.set_players("@a")

s = score(80)
bar.value = s
""")
    all_cmds = get_all_cmds(files)
    assert 'bossbar add pack:dragon_hp {"text": "Ender Dragon"}' in all_cmds
    assert "bossbar set pack:dragon_hp color purple" in all_cmds
    assert "bossbar set pack:dragon_hp style notched_10" in all_cmds
    assert "bossbar set pack:dragon_hp players @a" in all_cmds
    assert "execute store result bossbar pack:dragon_hp value run scoreboard players get" in all_cmds


def test_storage_scope():
    files = run_flare("""
from flare import storage_scope

with storage_scope("pack:cache") as s:
    s.score_count = 42
    s.player_name = "Alex"
""")
    all_cmds = get_all_cmds(files)
    assert 'data modify storage pack:cache score_count set value 42' in all_cmds
    assert 'data modify storage pack:cache player_name set value "Alex"' in all_cmds


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_") and callable(test):
            print(f"Running {name}...")
            test()
            print("  PASSED")
    print("\nALL PHASE 3 TESTS PASSED SUCCESSFULLY!")
