from typing import Any, Union, Optional  # noqa

from . import context
from .generated import resource_classes as rc
from .generated.resource_classes import *

__all__ = ["add_resource", "add_tag", "add_advancement", "add_banner_pattern", "add_cat_variant", "add_chat_type",
           "add_chicken_variant", "add_cow_variant", "add_damage_type", "add_dialog", "add_dimension",
           "add_dimension_type", "add_enchantment", "add_enchantment_provider", "add_frog_variant", "add_instrument",
           "add_item_modifier", "add_jukebox_song", "add_loot_table", "add_painting_variant", "add_pig_variant",
           "add_predicate", "add_recipe", "add_sulfur_cube_archetype", "add_test_environment", "add_test_instance",
           "add_timeline", "add_trade_set", "add_trial_spawner", "add_trim_material", "add_trim_pattern",
           "add_villager_trade", "add_wolf_sound_variant", "add_wolf_variant", "add_world_clock", "add_worldgen_biome",
           "add_worldgen_configured_carver", "add_worldgen_configured_feature", "add_worldgen_density_function",
           "add_worldgen_noise", "add_worldgen_noise_settings", "add_worldgen_placed_feature",
           "add_worldgen_processor_list", "add_worldgen_structure", "add_worldgen_structure_set",
           "add_worldgen_template_pool", "add_worldgen_world_preset", "add_worldgen_flat_level_generator_preset",
           "add_worldgen_multi_noise_biome_source_parameter_list", "add_zombie_nautilus_variant", "add_block_tag",
           "add_item_tag", "add_entity_type_tag", "add_fluid_tag", "add_function_tag",
           "add_game_event_tag", ] + rc.__all__


def _to_dict(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__print__"):
        return obj.__print__()
    if hasattr(obj, "__dict__"):
        return {k: _to_dict(v) for k, v in obj.__dict__.items() if not k.startswith("_") and v is not None}
    if isinstance(obj, list):
        return [_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items() if v is not None}
    return obj


def _split_path(path: str):
    if ":" in path:
        ns, path = path.split(":", 1)
    else:
        ns = context._current_namespace
    return ns, path


def _prepend_path(path: str, first: str):
    ns, path = _split_path(path)
    return f"{ns}:{first}{path}"


def add_resource(path: str, data: Any, *, return_path: str | None = None):
    data = _to_dict(data)

    if ":" in path:
        ns, file_path = path.split(":", 1)
    else:
        ns = context._current_namespace
        file_path = path

    context.json_files[f"{ns}:{file_path}.json"] = data

    if return_path is not None:
        r_ns, r_path = _split_path(return_path)
        return f"{r_ns}:{r_path}"

    return f"{ns}:{file_path}"


def add_tag(registry: str, name: str, data: Union[dict, list]):
    if isinstance(data, list):
        data = {"values": data}
    res = add_resource(_prepend_path(name, f"tags/{registry}/"), data, return_path=name)
    r_ns, r_path = _split_path(res)
    return f"#{r_ns}:{r_path}"


def add_advancement(name: str, data: Union[dict, "Advancement"]):
    pack_format = getattr(context, "config", {}).get("pack_format", 15)
    adv_dir = "advancement/" if pack_format >= 45 else "advancements/"
    return add_resource(_prepend_path(name, adv_dir), data, return_path=name)


def add_banner_pattern(name: str, data: Union[dict, "BannerPattern"]):
    return add_resource(_prepend_path(name, "banner_pattern/"), data, return_path=name)


def add_cat_variant(name: str, data: Union[dict, "CatVariant"]):
    return add_resource(_prepend_path(name, "cat_variant/"), data, return_path=name)


def add_chat_type(name: str, data: Union[dict, "ChatType"]):
    return add_resource(_prepend_path(name, "chat_type/"), data, return_path=name)


def add_chicken_variant(name: str, data: Union[dict, "ChickenVariant"]):
    return add_resource(_prepend_path(name, "chicken_variant/"), data, return_path=name)


def add_cow_variant(name: str, data: Union[dict, "CowVariant"]):
    return add_resource(_prepend_path(name, "cow_variant/"), data, return_path=name)


def add_damage_type(name: str, data: Union[dict, "DamageType"]):
    return add_resource(_prepend_path(name, "damage_type/"), data, return_path=name)


def add_dialog(name: str, data: Union[dict, "Dialog"]):
    return add_resource(_prepend_path(name, "dialog/"), data, return_path=name)


def add_dimension(name: str, data: Union[dict, "Dimension"]):
    return add_resource(_prepend_path(name, "dimension/"), data, return_path=name)


def add_dimension_type(name: str, data: Union[dict, "DimensionType"]):
    return add_resource(_prepend_path(name, "dimension_type/"), data, return_path=name)


def add_enchantment(name: str, data: Union[dict, "Enchantment"]):
    return add_resource(_prepend_path(name, "enchantment/"), data, return_path=name)


def add_enchantment_provider(name: str, data: Union[dict, "EnchantmentProvider"]):
    return add_resource(_prepend_path(name, "enchantment_provider/"), data, return_path=name)


def add_frog_variant(name: str, data: Union[dict, "FrogVariant"]):
    return add_resource(_prepend_path(name, "frog_variant/"), data, return_path=name)


def add_instrument(name: str, data: Union[dict, "Instrument"]):
    return add_resource(_prepend_path(name, "instrument/"), data, return_path=name)


def add_item_modifier(name: str, data: Union[dict, "ItemModifier"]):
    return add_resource(_prepend_path(name, "item_modifier/"), data, return_path=name)


def add_jukebox_song(name: str, data: Union[dict, "JukeboxSong"]):
    return add_resource(_prepend_path(name, "jukebox_song/"), data, return_path=name)


def add_loot_table(name: str, data: Union[dict, "LootTable"]):
    return add_resource(_prepend_path(name, "loot_table/"), data, return_path=name)


def add_painting_variant(name: str, data: Union[dict, "PaintingVariant"]):
    return add_resource(_prepend_path(name, "painting_variant/"), data, return_path=name)


def add_pig_variant(name: str, data: Union[dict, "PigVariant"]):
    return add_resource(_prepend_path(name, "pig_variant/"), data, return_path=name)


def add_predicate(name: str, data: Union[dict, "Predicate"]):
    from .execute_modifiers import predicate
    res = add_resource(_prepend_path(name, "predicate/"), data, return_path=name)
    return predicate(res)


def add_recipe(name: str, data: Union[dict, "Recipe"]):
    return add_resource(_prepend_path(name, "recipe/"), data, return_path=name)


def add_sulfur_cube_archetype(name: str, data: Union[dict, "SulfurCubeArchetype"]):
    return add_resource(_prepend_path(name, "sulfur_cube_archetype/"), data, return_path=name)


def add_test_environment(name: str, data: Union[dict, "TestEnvironment"]):
    return add_resource(_prepend_path(name, "test_environment/"), data, return_path=name)


def add_test_instance(name: str, data: Union[dict, "TestInstance"]):
    return add_resource(_prepend_path(name, "test_instance/"), data, return_path=name)


def add_timeline(name: str, data: Union[dict, "Timeline"]):
    return add_resource(_prepend_path(name, "timeline/"), data, return_path=name)


def add_trade_set(name: str, data: Union[dict, "TradeSet"]):
    return add_resource(_prepend_path(name, "trade_set/"), data, return_path=name)


def add_trial_spawner(name: str, data: Union[dict, "TrialSpawner"]):
    return add_resource(_prepend_path(name, "trial_spawner/"), data, return_path=name)


def add_trim_material(name: str, data: Union[dict, "TrimMaterial"]):
    return add_resource(_prepend_path(name, "trim_material/"), data, return_path=name)


def add_trim_pattern(name: str, data: Union[dict, "TrimPattern"]):
    return add_resource(_prepend_path(name, "trim_pattern/"), data, return_path=name)


def add_villager_trade(name: str, data: Union[dict, "VillagerTrade"]):
    return add_resource(_prepend_path(name, "villager_trade/"), data, return_path=name)


def add_wolf_sound_variant(name: str, data: Union[dict, "WolfSoundVariant"]):
    return add_resource(_prepend_path(name, "wolf_sound_variant/"), data, return_path=name)


def add_wolf_variant(name: str, data: Union[dict, "WolfVariant"]):
    return add_resource(_prepend_path(name, "wolf_variant/"), data, return_path=name)


def add_world_clock(name: str, data: Union[dict, "WorldClock"]):
    return add_resource(_prepend_path(name, "world_clock/"), data, return_path=name)


def add_worldgen_biome(name: str, data: Union[dict, "Biome"]):
    return add_resource(_prepend_path(name, "worldgen/biome/"), data, return_path=name)


def add_worldgen_configured_carver(name: str, data: Union[dict, "ConfiguredCarver"]):
    return add_resource(_prepend_path(name, "worldgen/configured_carver/"), data, return_path=name)


def add_worldgen_configured_feature(name: str, data: Union[dict, "ConfiguredFeature"]):
    return add_resource(_prepend_path(name, "worldgen/configured_feature/"), data, return_path=name)


def add_worldgen_density_function(name: str, data: Union[dict, "DensityFunction"]):
    return add_resource(_prepend_path(name, "worldgen/density_function/"), data, return_path=name)


def add_worldgen_noise(name: str, data: Union[dict, "NoiseParameters"]):
    return add_resource(_prepend_path(name, "worldgen/noise/"), data, return_path=name)


def add_worldgen_noise_settings(name: str, data: Union[dict, "NoiseGeneratorSettings"]):
    return add_resource(_prepend_path(name, "worldgen/noise_settings/"), data, return_path=name)


def add_worldgen_placed_feature(name: str, data: Union[dict, "PlacedFeature"]):
    return add_resource(_prepend_path(name, "worldgen/placed_feature/"), data, return_path=name)


def add_worldgen_processor_list(name: str, data: Union[dict, "ProcessorList"]):
    return add_resource(_prepend_path(name, "worldgen/processor_list/"), data, return_path=name)


def add_worldgen_structure(name: str, data: Union[dict, "Structure"]):
    return add_resource(_prepend_path(name, "worldgen/structure/"), data, return_path=name)


def add_worldgen_structure_set(name: str, data: Union[dict, "StructureSet"]):
    return add_resource(_prepend_path(name, "worldgen/structure_set/"), data, return_path=name)


def add_worldgen_template_pool(name: str, data: Union[dict, "TemplatePool"]):
    return add_resource(_prepend_path(name, "worldgen/template_pool/"), data, return_path=name)


def add_worldgen_world_preset(name: str, data: Union[dict, "WorldPreset"]):
    return add_resource(_prepend_path(name, "worldgen/world_preset/"), data, return_path=name)


def add_worldgen_flat_level_generator_preset(name: str, data: Union[dict, "FlatGeneratorPreset"]):
    return add_resource(_prepend_path(name, "worldgen/flat_level_generator_preset/"), data, return_path=name)


def add_worldgen_multi_noise_biome_source_parameter_list(name: str,
                                                         data: Union[dict, "MultiNoiseBiomeSourceParameterList"]):
    return add_resource(_prepend_path(name, "worldgen/multi_noise_biome_source_parameter_list/"), data,
                        return_path=name)


def add_zombie_nautilus_variant(name: str, data: Union[dict, "ZombieNautilusVariant"]):
    return add_resource(_prepend_path(name, "zombie_nautilus_variant/"), data, return_path=name)


def add_block_tag(name: str, data: Union[dict, list[str]]):
    return add_tag("block", name, data)


def add_item_tag(name: str, data: Union[dict, list[str]]):
    return add_tag("item", name, data)


def add_entity_type_tag(name: str, data: Union[dict, list[str]]):
    return add_tag("entity_type", name, data)


def add_fluid_tag(name: str, data: Union[dict, list[str]]):
    return add_tag("fluid", name, data)


def add_function_tag(name: str, data: Union[dict, list[str]]):
    return add_tag("function", name, data)


def add_game_event_tag(name: str, data: Union[dict, list[str]]):
    return add_tag("game_event", name, data)
