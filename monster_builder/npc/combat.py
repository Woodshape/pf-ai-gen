"""Optional NPC routines: one shared transformation path, never base-stat buffs."""
import copy
import re

OPTION_FEATS = {
    "feat.power-attack", "feat.deadly-aim", "feat.point-blank-shot", "feat.rapid-shot", "feat.manyshot",
    "feat.two-weapon-fighting", "feat.improved-two-weapon-fighting", "feat.greater-two-weapon-fighting",
    "feat.vital-strike", "feat.improved-vital-strike", "feat.greater-vital-strike", "feat.combat-expertise",
    "feat.arcane-strike", "feat.cleave", "feat.great-cleave", "feat.pinpoint-targeting", "feat.whirlwind-attack",
    "feat.scorpion-style", "feat.gorgon-s-fist", "feat.stunning-fist", "feat.medusa-s-wrath",
}
VITAL = {"feat.vital-strike": 2, "feat.improved-vital-strike": 3, "feat.greater-vital-strike": 4}
TWF = {"feat.two-weapon-fighting", "feat.improved-two-weapon-fighting", "feat.greater-two-weapon-fighting"}
SINGLE = set(VITAL) | {"feat.cleave", "feat.great-cleave", "feat.pinpoint-targeting", "feat.scorpion-style", "feat.gorgon-s-fist"}
FULL = TWF | {"feat.rapid-shot", "feat.manyshot", "feat.whirlwind-attack", "feat.medusa-s-wrath"}
UNARMED = {"feat.scorpion-style", "feat.gorgon-s-fist", "feat.stunning-fist", "feat.medusa-s-wrath"}
BOWS = {"longbow", "shortbow", "composite-longbow", "composite-shortbow"}


def _damage(expression):
    match = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", expression)
    if not match:
        raise ValueError("routine requires supported weapon dice plus a flat damage modifier")
    return int(match[1]), int(match[2]), int(match[3] or 0)


def calculate_routine(items, attacks, feat_ids, bab, modifiers, request):
    """Calculate an explicitly chosen weapon/action/feat combination.

    Request: {weaponId, offHandWeaponId?, action: attack|full-attack,
              options: [feat IDs]}. Choosing a contextual option (e.g. PBS)
    establishes a labelled condition, never an unconditional base bonus.
    Raises ValueError for illegal combinations or unsupported equipment.
    """
    if not isinstance(request, dict) or set(request) - {"weaponId", "offHandWeaponId", "action", "options"}:
        raise ValueError("invalid combat routine fields")
    action, options = request.get("action"), request.get("options")
    if action not in {"attack", "full-attack"} or not isinstance(options, list) or not options or any(not isinstance(value, str) for value in options):
        raise ValueError("choose an action and a nonempty list of feat IDs")
    selected, active = set(feat_ids), set(options)
    if len(active) != len(options) or active - OPTION_FEATS or active - selected:
        raise ValueError("routine options must be distinct, implemented feats owned by this NPC")
    if (action == "attack" and active & FULL) or (action == "full-attack" and active & SINGLE) or len(active & SINGLE) > 1:
        raise ValueError("incompatible attack actions; single-attack feats cannot be used with a full attack")
    if "feat.whirlwind-attack" in active and active & (FULL - {"feat.whirlwind-attack"}):
        raise ValueError("Whirlwind Attack forfeits all bonus and extra attacks")
    if len(active & TWF) > 1:
        raise ValueError("choose one two-weapon routine; owned progression feats apply automatically")
    item_map = {item["itemId"]: item for item in items if item.get("category") == "weapon"}
    base_map = {attack["itemId"]: attack for attack in attacks if attack.get("itemId") and not attack.get("rapidShot")}
    weapon_id = request.get("weaponId")
    if not isinstance(weapon_id, str) or weapon_id not in item_map or weapon_id not in base_map:
        raise ValueError("choose an equipped weapon with a supported base attack")
    weapon = item_map[weapon_id]
    ranged = base_map[weapon_id]["attackType"] == "ranged"
    if active & {"feat.deadly-aim", "feat.point-blank-shot", "feat.rapid-shot", "feat.manyshot", "feat.pinpoint-targeting"} and not ranged:
        raise ValueError("this option requires a ranged weapon")
    if active & ({"feat.power-attack", "feat.combat-expertise", "feat.cleave", "feat.great-cleave", "feat.whirlwind-attack"} | TWF) and ranged:
        raise ValueError("this option requires a melee weapon")
    if "feat.rapid-shot" in active and weapon["effects"].get("reloadAction") in {"move", "full-round"}:
        raise ValueError("this weapon cannot reload quickly enough for Rapid Shot")
    if "feat.manyshot" in active and weapon["effects"].get("weaponType") not in BOWS:
        raise ValueError("Manyshot requires a bow")
    if active & UNARMED and weapon["effects"].get("weaponType") != "unarmed-strike":
        raise ValueError("this option requires an unarmed strike")
    off_id = request.get("offHandWeaponId")
    paired = bool(active & TWF)
    if bool(off_id) != paired:
        raise ValueError("two-weapon fighting requires an explicit off-hand weapon, and other routines do not use one")
    if paired:
        if off_id not in item_map or off_id not in base_map or base_map[off_id]["attackType"] != "melee":
            raise ValueError("choose an equipped melee off-hand weapon")
        if off_id == weapon_id and weapon.get("quantity", 1) < 2:
            raise ValueError("using two copies of a weapon requires quantity at least two")
        if any(item_map[key]["effects"].get("twoHanded") for key in (weapon_id, off_id)):
            raise ValueError("a two-handed weapon cannot be used in this two-weapon routine")
        if any(item.get("effects", {}).get("shieldCategory") for item in items):
            raise ValueError("shield-equipped two-weapon states are not implemented; unequip the shield for this routine")
    lines = [copy.deepcopy(base_map[weapon_id])]
    lines[0]["hand"] = "primary"
    if action == "attack" or "feat.whirlwind-attack" in active:
        lines[0]["attackBonuses"] = lines[0]["attackBonuses"][:1]
    if paired:
        off = copy.deepcopy(base_map[off_id])
        count = 1 + int("feat.improved-two-weapon-fighting" in selected) + int("feat.greater-two-weapon-fighting" in selected)
        off["attackBonuses"] = [off["attackBonuses"][0] - 5 * index for index in range(count)]
        off["hand"] = "off-hand"
        lines.append(off)
    state, notes = {}, []
    step = 1 + bab // 4
    if "feat.power-attack" in active:
        state["cmbPenalty"] = -step
        notes.append("Power Attack lasts until your next turn; no bonus to touch or non-HP damage.")
    if "feat.deadly-aim" in active:
        notes.append("Deadly Aim lasts until your next turn; no bonus to touch or non-HP damage.")
    if "feat.point-blank-shot" in active:
        notes.append("Only within 30 feet.")
    if "feat.combat-expertise" in active:
        state.update(dodgeAC=step, dodgeTouchAC=step, cmdBonus=step)
        state["cmbPenalty"] = state.get("cmbPenalty", 0) - step
        notes.append("Combat Expertise lasts until your next turn; dodge bonus is lost when Dexterity is denied.")
    if "feat.arcane-strike" in active:
        if not isinstance(modifiers.get("casterLevel"), int) or modifiers["casterLevel"] < 1:
            raise ValueError("Arcane Strike requires an available arcane caster level")
        state.update(actionCost="swift", weaponsTreatedAsMagic=True)
        notes.append("Arcane Strike lasts 1 round.")
    if active & {"feat.cleave", "feat.great-cleave"}:
        state.update(acPenalty=-2, touchACPenalty=-2, flatFootedACPenalty=-2, cmdPenalty=-2)
        notes.append("If this attack hits, attack an adjacent foe within reach; Great Cleave can continue the chain. Never attack a target twice; AC penalty lasts until your next turn.")
    if "feat.pinpoint-targeting" in active:
        state.update(ignoreTargetAC=["armor", "natural-armor", "shield"], noMovementThisRound=True)
    if "feat.whirlwind-attack" in active:
        state.update(oneAttackPerTarget=True, forfeitsExtraAttacks=True)
        notes.append("One highest-bonus melee attack per opponent within reach; no bonus or extra attacks.")
    if active & UNARMED:
        if not isinstance(modifiers.get("characterLevel"), int) or not isinstance(modifiers.get("wisdom"), int):
            raise ValueError("unarmed feat actions require character level and Wisdom")
        dc = 10 + modifiers["characterLevel"] // 2 + modifiers["wisdom"]
        if active & (UNARMED - {"feat.medusa-s-wrath"}):
            state["fortitudeDC"] = dc
        if "feat.scorpion-style" in active:
            state.update(durationRounds=max(0, modifiers["wisdom"]), targetSpeed=5)
            notes.append("On hit, target's base land speed becomes 5 feet unless it saves.")
        if "feat.gorgon-s-fist" in active:
            notes.append("Target must already have reduced speed; a failed save staggers it until the end of your next turn.")
        if "feat.stunning-fist" in active:
            monk = modifiers.get("monkLevels", 0)
            state["usesPerDay"] = monk + (modifiers["characterLevel"] - monk) // 4
            notes.append("Declare one unarmed attack before rolling; costs one use even on a miss, at most once per round. Failed save stuns for 1 round; GM checks immunities.")
        if "feat.medusa-s-wrath" in active:
            notes.append("Two extra unarmed attacks only against a dazed, flat-footed, paralyzed, staggered, stunned or unconscious foe.")
    for line in lines:
        effect = item_map[line["itemId"]]["effects"]
        count, die, flat = _damage(line["damageExpression"])
        penalty = 0
        off_hand = line["hand"] == "off-hand"
        if paired:
            penalty -= 2 if item_map[off_id]["effects"].get("lightWeapon") else 4
            if off_hand and "feat.double-slice" not in selected:
                strength = max(0, modifiers["strength"])
                flat -= strength - strength // 2
        if "feat.power-attack" in active:
            penalty -= step
            flat += step if off_hand else step * (3 if effect.get("twoHanded") else 2)
        if "feat.deadly-aim" in active:
            penalty -= step
            flat += 2 * step
        if "feat.combat-expertise" in active:
            penalty -= step
        if "feat.point-blank-shot" in active:
            penalty += 1
            flat += 1
        if "feat.arcane-strike" in active:
            flat += min(5, 1 + modifiers["casterLevel"] // 5)
        if "feat.rapid-shot" in active:
            penalty -= 2
            line["attackBonuses"].insert(0, line["attackBonuses"][0])
        if "feat.medusa-s-wrath" in active and not off_hand:
            line["attackBonuses"][:0] = [line["attackBonuses"][0]] * 2
        for feat in active & set(VITAL):
            state.update(extraDiceNotMultipliedOnCritical=True, extraWeaponDice=f"{count * (VITAL[feat] - 1)}d{die}")
            count *= VITAL[feat]
        line["attackBonuses"] = [bonus + penalty for bonus in line["attackBonuses"]]
        line["attackBonusExpression"] = "/".join(f"{bonus:+d}" for bonus in line["attackBonuses"])
        line["damageExpression"] = f"{count}d{die}" + (f"{flat:+d}" if flat else "")
        if "feat.manyshot" in active:
            line["firstAttackProjectiles"] = 2
            notes.append("First attack fires two arrows: full damage per arrow; precision and critical damage once; DR/resistance separately per arrow.")
    return {"id": "routine.requested", "request": copy.deepcopy(request), "feats": sorted(active),
            "fullAttack": action == "full-attack", "attacks": lines, "state": state, "notes": notes}


def combat_routines(items, attacks, feat_ids, bab, modifiers):
    """Discover single-option previews; explicit pairs/combinations use calculate_routine."""
    selected = set(feat_ids)
    choices = selected & (OPTION_FEATS - TWF)
    # Show only the strongest owned tier in automatic previews.
    for chain in (("feat.vital-strike", "feat.improved-vital-strike", "feat.greater-vital-strike"), ("feat.cleave", "feat.great-cleave")):
        owned = [feat for feat in chain if feat in choices]
        choices.difference_update(owned[:-1])
    result = []
    for feat in sorted(choices):
        for attack in attacks:
            if not attack.get("itemId") or attack.get("rapidShot"):
                continue
            request = {"weaponId": attack["itemId"], "action": "full-attack" if feat in FULL else "attack", "options": [feat]}
            try:
                result.append(calculate_routine(items, attacks, feat_ids, bab, modifiers, request))
            except ValueError:
                # Discovery omits inapplicable weapon/option pairs; explicit
                # requests surface the same validation error to the caller.
                continue
    return result
