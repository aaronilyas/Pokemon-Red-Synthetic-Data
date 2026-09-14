"""Pokemon Red USA (pret/pokered) RAM reads. Collector-only; never written to JSONL."""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Addresses from pret/pokered wram.asm + Datacrystal (USA Red/Blue).
# Spec-mandated:
# ---------------------------------------------------------------------------
W_IS_IN_BATTLE = 0xD057
W_OBTAINED_BADGES = 0xD356
W_CUR_MAP = 0xD35E
W_Y_COORD = 0xD361
W_X_COORD = 0xD362
W_PARTY_COUNT = 0xD163
W_SPRITE_PLAYER_FACING = 0xC109  # 0 down, 4 up, 8 left, 0xC right

# Sprite state (player is struct 0 of wSpriteStateData1 at 0xC100)
W_SPRITE_PLAYER_MOVEMENT_STATUS = 0xC101  # 0 uninit, 1 ready, 2 delayed, 3 moving

# Menus (SECTION WRAM)
W_TOP_MENU_ITEM_Y = 0xCC24
W_TOP_MENU_ITEM_X = 0xCC25
W_CURRENT_MENU_ITEM = 0xCC26
W_MAX_MENU_ITEM = 0xCC28
W_MENU_WATCHED_KEYS = 0xCC29
W_PLAYER_MOVE_LIST_INDEX = 0xCC2E

# Scripted joypad / ignore (Datacrystal + pret)
W_SIMULATED_JOYPAD_INDEX = 0xCD38
W_JOY_IGNORE = 0xCD6B

# Overworld walk
W_FONT_LOADED = 0xCFC4  # bit 0 = font in VRAM (text/menu; NPC walk disabled)
W_WALK_COUNTER = 0xCFC5

# Battle structs
W_ENEMY_MON_SPECIES = 0xCFE5
W_ENEMY_MON_HP = 0xCFE6  # 2 bytes, big-endian
W_ENEMY_MON_TYPE1 = 0xCFEA
W_ENEMY_MON_TYPE2 = 0xCFEB
W_BATTLE_MON_SPECIES = 0xD014
W_BATTLE_MON_HP = 0xD015
W_BATTLE_MON_STATUS = 0xD018
W_BATTLE_MON_TYPE1 = 0xD019
W_BATTLE_MON_TYPE2 = 0xD01A
W_BATTLE_MON_MOVES = 0xD01C  # 4 bytes
W_BATTLE_MON_LEVEL = 0xD022
W_BATTLE_MON_MAX_HP = 0xD023
W_BATTLE_MON_PP = 0xD02D  # 4 bytes

W_TEXT_BOX_ID = 0xD125

# Party
W_PARTY_SPECIES = 0xD164
W_PARTY_MON1 = 0xD16B
PARTY_MON_SIZE = 44
MON_HP = 1
MON_STATUS = 4
MON_TYPE1 = 5
MON_TYPE2 = 6
MON_MOVES = 8
MON_PP = 0x1D
MON_LEVEL = 0x21
MON_MAX_HP = 0x22

# Bag
W_NUM_BAG_ITEMS = 0xD31D
W_BAG_ITEMS = 0xD31E

W_PLAYER_MONEY = 0xD347  # 3 bytes BCD
W_OPTIONS = 0xD355

# Map / tileset
W_CUR_MAP_TILESET = 0xD367
W_TILESET_COLLISION_PTR = 0xD530  # from PyBoy gen1 wrapper
W_GRASS_TILE = 0xD535

# Status flags (counted back from wEventFlags = 0xD747)
W_STATUS_FLAGS4 = 0xD72E
W_STATUS_FLAGS5 = 0xD730
W_EVENT_FLAGS = 0xD747

# Misc
W_MISC_FLAGS = 0xCD60  # approximate; BIT_SEEN_BY_TRAINER = 0. Probed at runtime.
W_PAL_OFFSET = 0xD35D  # wMapPalOffset; non-zero during some fades

# Tilemap / PPU
W_TILE_MAP = 0xC3A0
SCREEN_WIDTH = 20
SCREEN_HEIGHT = 18
R_WY = 0xFF4A
R_WX = 0xFF4B

# Script indices (wGameProgressFlags). wOaksLabCurScript is first.
W_OAKS_LAB_CUR_SCRIPT = 0xD5F0
W_PALLET_TOWN_CUR_SCRIPT = 0xD5F1
W_VIRIDIAN_CITY_CUR_SCRIPT = 0xD5F4
W_VIRIDIAN_MART_CUR_SCRIPT = 0xD60D

# Event bits (event_constants.asm, const_def from 0)
EVENT_FOLLOWED_OAK_INTO_LAB = 0x00
EVENT_GOT_TOWN_MAP = 0x18
EVENT_FOLLOWED_OAK_INTO_LAB_2 = 0x20
EVENT_OAK_ASKED_TO_CHOOSE_MON = 0x21
EVENT_GOT_STARTER = 0x22
EVENT_BATTLED_RIVAL_IN_OAKS_LAB = 0x23
EVENT_GOT_POKEBALLS_FROM_OAK = 0x24
EVENT_GOT_POKEDEX = 0x25
EVENT_OAK_APPEARED_IN_PALLET = 0x27
EVENT_OAK_GOT_PARCEL = 0x38
EVENT_GOT_OAKS_PARCEL = 0x39
EVENT_GOT_POTION_SAMPLE = 0x3C0
EVENT_BEAT_BROCK = 0x77

# Maps
PALLET_TOWN = 0x00
VIRIDIAN_CITY = 0x01
PEWTER_CITY = 0x02
ROUTE_1 = 0x0C
ROUTE_2 = 0x0D
REDS_HOUSE_1F = 0x25
REDS_HOUSE_2F = 0x26
OAKS_LAB = 0x28
VIRIDIAN_POKECENTER = 0x29
VIRIDIAN_MART = 0x2A
VIRIDIAN_FOREST_NORTH_GATE = 0x2F
ROUTE_2_GATE = 0x31
VIRIDIAN_FOREST_SOUTH_GATE = 0x32
VIRIDIAN_FOREST = 0x33
PEWTER_GYM = 0x36
PEWTER_MART = 0x38
PEWTER_POKECENTER = 0x3A

# Facing
FACE_DOWN = 0x00
FACE_UP = 0x04
FACE_LEFT = 0x08
FACE_RIGHT = 0x0C

# Items / moves
ITEM_POTION = 0x14
ITEM_OAKS_PARCEL = 0x46
ITEM_POKE_BALL = 0x04
ITEM_ANTIDOTE = 0x0B

MOVE_VINE_WHIP = 0x16
MOVE_TACKLE = 0x21
MOVE_GROWL = 0x2D
MOVE_LEECH_SEED = 0x49
MOVE_SCRATCH = 0x0A
MOVE_POISON_STING = 0x28
MOVE_STRING_SHOT = 0x51
MOVE_HARDEN = 0x6A

# Types (gen 1)
TYPE_NORMAL = 0x00
TYPE_FIGHTING = 0x01
TYPE_FLYING = 0x02
TYPE_POISON = 0x03
TYPE_GROUND = 0x04
TYPE_ROCK = 0x05
TYPE_BUG = 0x07
TYPE_GHOST = 0x08
TYPE_FIRE = 0x14
TYPE_WATER = 0x15
TYPE_GRASS = 0x16
TYPE_ELECTRIC = 0x17
TYPE_PSYCHIC = 0x18
TYPE_ICE = 0x19
TYPE_DRAGON = 0x1A

# wStatusFlags5 bits
BIT_SCRIPTED_NPC_MOVEMENT = 0
BIT_DISABLE_JOYPAD = 5
BIT_NO_TEXT_DELAY = 6
BIT_SCRIPTED_MOVEMENT_STATE = 7

# wStatusFlags4 bits
BIT_USED_POKECENTER = 2
BIT_GOT_STARTER = 3
BIT_NO_BATTLES = 4
BIT_BATTLE_OVER_OR_BLACKOUT = 5
BIT_INIT_SCRIPTED_MOVEMENT = 7

# wFontLoaded
BIT_FONT_LOADED = 0

# Move power / type for the tiny set we care about. Power 0 = status.
MOVE_INFO: dict[int, tuple[int, int]] = {
    MOVE_VINE_WHIP: (35, TYPE_GRASS),
    MOVE_TACKLE: (35, TYPE_NORMAL),
    MOVE_GROWL: (0, TYPE_NORMAL),
    MOVE_LEECH_SEED: (0, TYPE_GRASS),
    MOVE_SCRATCH: (40, TYPE_NORMAL),
    MOVE_POISON_STING: (15, TYPE_POISON),
    MOVE_STRING_SHOT: (0, TYPE_BUG),
    MOVE_HARDEN: (0, TYPE_NORMAL),
    0x01: (40, TYPE_NORMAL),  # Pound
    0x28: (15, TYPE_POISON),
    0x51: (0, TYPE_BUG),
    0x10: (40, TYPE_FLYING),  # Gust (gen 1: Normal actually — still damaging)
    0x62: (40, TYPE_NORMAL),  # Quick Attack
    0x34: (40, TYPE_FIRE),  # Ember
}

# Very small gen-1 effectiveness: attack_type -> {def_type: multiplier_tenths}
# 20 = super, 10 = neutral, 5 = not very, 0 = immune
_EFF: dict[int, dict[int, int]] = {
    TYPE_NORMAL: {TYPE_ROCK: 5, TYPE_GHOST: 0},
    TYPE_GRASS: {
        TYPE_WATER: 20,
        TYPE_GROUND: 20,
        TYPE_ROCK: 20,
        TYPE_FIRE: 5,
        TYPE_GRASS: 5,
        TYPE_POISON: 5,
        TYPE_FLYING: 5,
        TYPE_BUG: 5,
        TYPE_DRAGON: 5,
    },
    TYPE_FIRE: {TYPE_GRASS: 20, TYPE_BUG: 20, TYPE_ICE: 20, TYPE_WATER: 5, TYPE_FIRE: 5, TYPE_ROCK: 5, TYPE_DRAGON: 5},
    TYPE_WATER: {TYPE_FIRE: 20, TYPE_GROUND: 20, TYPE_ROCK: 20, TYPE_WATER: 5, TYPE_GRASS: 5, TYPE_DRAGON: 5},
    TYPE_POISON: {TYPE_GRASS: 20, TYPE_POISON: 5, TYPE_GROUND: 5, TYPE_ROCK: 5, TYPE_GHOST: 5},
    TYPE_BUG: {TYPE_GRASS: 20, TYPE_POISON: 20, TYPE_FIRE: 5, TYPE_FIGHTING: 5, TYPE_FLYING: 5, TYPE_GHOST: 5},
    TYPE_FLYING: {TYPE_GRASS: 20, TYPE_FIGHTING: 20, TYPE_BUG: 20, TYPE_ROCK: 5, TYPE_ELECTRIC: 5},
    TYPE_GROUND: {TYPE_FIRE: 20, TYPE_ELECTRIC: 20, TYPE_POISON: 20, TYPE_ROCK: 20, TYPE_GRASS: 5, TYPE_BUG: 5, TYPE_FLYING: 0},
    TYPE_ROCK: {TYPE_FIRE: 20, TYPE_ICE: 20, TYPE_FLYING: 20, TYPE_BUG: 20, TYPE_FIGHTING: 5, TYPE_GROUND: 5},
}


def type_mult(atk: int, def1: int, def2: int) -> int:
    """Return product of tenths-multipliers (100 = 1.0x)."""
    m = 10
    for dt in {def1, def2}:
        m = m * _EFF.get(atk, {}).get(dt, 10) // 10
    return m


# Viridian Forest collision (34×48 walk tiles). '#' is a tree/wall.
# West x=1–2 is open only for y≤25; y=32–39 west is solid trees.
FOREST_ASCII = """
#..###############################
#.####........##.................#
#..###........##.................#
#..###........##....##########...#
#..###...##...##...############..#
#..###...##...##...############..#
#..###...##...##...############..#
#..###...##...##...############..#
#..###...##...##.................#
#..###...##...##.................#
#..###...##...##...######..###...#
#..###...##...##...######..###...#
#..###...##...##...######..###...#
#..###...##...##...######..###...#
#..###...##...##...######..###...#
#..###...##...##...######..###...#
#..###...##........######..###...#
#..###...##........######.####...#
#..###...##........######........#
#..###...##........######........#
#..###...################...###..#
#..###...################...###..#
#........################...###..#
#........################...###..#
#...#........############...###..#
#............############...###..#
###########..############...###..#
###########..############...###..#
###########..############...###..#
###########..############...###..#
#........################...###..#
#........################...###..#
######..........#..######........#
######.............######........#
######...######....######...######
######...######....######...######
######...######....######...######
######...######....######...######
######...######....######...######
######...######....######...######
#.......................#........#
#...............##...............#
#...............##...............#
#................................#
###############....###############
###############...################
###############....###############
###############....###############
""".strip().splitlines()

FOREST_BLOCKED: set[tuple[int, int]] = {
    (x, y)
    for y, row in enumerate(FOREST_ASCII)
    for x, ch in enumerate(row)
    if ch == "#"
}

# Door tiles to avoid unless they are the navigation target.
MAP_WARPS: dict[int, set[tuple[int, int]]] = {
    PALLET_TOWN: {(5, 5), (13, 5), (12, 11)},
    VIRIDIAN_CITY: {(23, 25), (29, 19), (21, 15), (21, 9), (32, 7)},
    PEWTER_CITY: {(14, 7), (19, 5), (16, 17), (29, 13), (23, 17), (7, 29), (13, 25)}
    | {(x, 35) for x in range(20)},
    ROUTE_2: {(12, 9), (3, 11), (15, 19), (16, 35), (15, 39), (3, 43)},
}

MAP_NAMES = {
    PALLET_TOWN: "Pallet Town",
    VIRIDIAN_CITY: "Viridian City",
    PEWTER_CITY: "Pewter City",
    ROUTE_1: "Route 1",
    ROUTE_2: "Route 2",
    REDS_HOUSE_1F: "Red's House 1F",
    REDS_HOUSE_2F: "Red's House 2F",
    OAKS_LAB: "Oak's Lab",
    VIRIDIAN_POKECENTER: "Viridian Pokecenter",
    VIRIDIAN_MART: "Viridian Mart",
    VIRIDIAN_FOREST_NORTH_GATE: "Forest North Gate",
    ROUTE_2_GATE: "Route 2 Gate",
    VIRIDIAN_FOREST_SOUTH_GATE: "Forest South Gate",
    VIRIDIAN_FOREST: "Viridian Forest",
    PEWTER_GYM: "Pewter Gym",
    PEWTER_MART: "Pewter Mart",
    PEWTER_POKECENTER: "Pewter Pokecenter",
}


@dataclass(frozen=True)
class PartyMon:
    species: int
    hp: int
    max_hp: int
    level: int
    status: int
    moves: tuple[int, int, int, int]
    pp: tuple[int, int, int, int]
    type1: int
    type2: int


class RAM:
    def __init__(self, pyboy):
        self.pyboy = pyboy

    def u8(self, addr: int) -> int:
        return int(self.pyboy.memory[addr])

    def u16be(self, addr: int) -> int:
        return (self.u8(addr) << 8) | self.u8(addr + 1)

    @property
    def in_battle(self) -> int:
        return self.u8(W_IS_IN_BATTLE)

    @property
    def badges(self) -> int:
        return self.u8(W_OBTAINED_BADGES)

    @property
    def has_boulder(self) -> bool:
        return bool(self.badges & 1)

    @property
    def map_id(self) -> int:
        return self.u8(W_CUR_MAP)

    @property
    def y(self) -> int:
        return self.u8(W_Y_COORD)

    @property
    def x(self) -> int:
        return self.u8(W_X_COORD)

    @property
    def xy(self) -> tuple[int, int]:
        return self.x, self.y

    @property
    def pos(self) -> tuple[int, int, int]:
        return self.map_id, self.x, self.y

    @property
    def party_count(self) -> int:
        return self.u8(W_PARTY_COUNT)

    @property
    def facing(self) -> int:
        return self.u8(W_SPRITE_PLAYER_FACING)

    @property
    def movement_status(self) -> int:
        return self.u8(W_SPRITE_PLAYER_MOVEMENT_STATUS)

    @property
    def walk_counter(self) -> int:
        return self.u8(W_WALK_COUNTER)

    @property
    def font_loaded(self) -> bool:
        return bool(self.u8(W_FONT_LOADED) & (1 << BIT_FONT_LOADED))

    @property
    def joy_ignore(self) -> int:
        return self.u8(W_JOY_IGNORE)

    @property
    def simulated_joy(self) -> int:
        return self.u8(W_SIMULATED_JOYPAD_INDEX)

    @property
    def status5(self) -> int:
        return self.u8(W_STATUS_FLAGS5)

    @property
    def joypad_disabled(self) -> bool:
        return bool(self.status5 & (1 << BIT_DISABLE_JOYPAD))

    @property
    def scripted_movement(self) -> bool:
        s5 = self.status5
        return bool(
            (s5 & (1 << BIT_SCRIPTED_MOVEMENT_STATE))
            or (s5 & (1 << BIT_SCRIPTED_NPC_MOVEMENT))
            or self.simulated_joy
        )

    @property
    def current_menu_item(self) -> int:
        return self.u8(W_CURRENT_MENU_ITEM)

    @property
    def max_menu_item(self) -> int:
        return self.u8(W_MAX_MENU_ITEM)

    @property
    def menu_watched_keys(self) -> int:
        return self.u8(W_MENU_WATCHED_KEYS)

    @property
    def top_menu_y(self) -> int:
        return self.u8(W_TOP_MENU_ITEM_Y)

    @property
    def top_menu_x(self) -> int:
        return self.u8(W_TOP_MENU_ITEM_X)

    @property
    def move_list_index(self) -> int:
        return self.u8(W_PLAYER_MOVE_LIST_INDEX)

    @property
    def text_box_id(self) -> int:
        return self.u8(W_TEXT_BOX_ID)

    @property
    def pal_offset(self) -> int:
        return self.u8(W_PAL_OFFSET)

    def event(self, bit: int) -> bool:
        return bool(self.u8(W_EVENT_FLAGS + (bit // 8)) & (1 << (bit % 8)))

    def party_mon(self, index: int = 0) -> PartyMon | None:
        if index >= self.party_count:
            return None
        base = W_PARTY_MON1 + index * PARTY_MON_SIZE
        moves = tuple(self.u8(base + MON_MOVES + i) for i in range(4))
        pp = tuple(self.u8(base + MON_PP + i) for i in range(4))
        return PartyMon(
            species=self.u8(base),
            hp=self.u16be(base + MON_HP),
            max_hp=self.u16be(base + MON_MAX_HP),
            level=self.u8(base + MON_LEVEL),
            status=self.u8(base + MON_STATUS),
            moves=moves,  # type: ignore[arg-type]
            pp=pp,  # type: ignore[arg-type]
            type1=self.u8(base + MON_TYPE1),
            type2=self.u8(base + MON_TYPE2),
        )

    def lead(self) -> PartyMon | None:
        return self.party_mon(0)

    def bag(self) -> list[tuple[int, int]]:
        n = min(self.u8(W_NUM_BAG_ITEMS), 20)
        items = []
        for i in range(n):
            item = self.u8(W_BAG_ITEMS + i * 2)
            qty = self.u8(W_BAG_ITEMS + i * 2 + 1)
            if item in (0x00, 0xFF):
                break
            items.append((item, qty))
        return items

    def bag_qty(self, item_id: int) -> int:
        return sum(q for i, q in self.bag() if i == item_id)

    def has_item(self, item_id: int) -> bool:
        return self.bag_qty(item_id) > 0

    def battle_moves(self) -> list[int]:
        return [self.u8(W_BATTLE_MON_MOVES + i) for i in range(4)]

    def battle_pp(self) -> list[int]:
        return [self.u8(W_BATTLE_MON_PP + i) & 0x3F for i in range(4)]

    def battle_hp(self) -> tuple[int, int]:
        return self.u16be(W_BATTLE_MON_HP), self.u16be(W_BATTLE_MON_MAX_HP)

    def enemy_hp(self) -> int:
        return self.u16be(W_ENEMY_MON_HP)

    def enemy_types(self) -> tuple[int, int]:
        return self.u8(W_ENEMY_MON_TYPE1), self.u8(W_ENEMY_MON_TYPE2)

    def tile(self, x: int, y: int) -> int:
        return self.u8(W_TILE_MAP + y * SCREEN_WIDTH + x)

    def tilemap_has_cursor(self) -> bool:
        # Menu cursor tiles in gen 1 are typically 0xED (▶) / 0xEE.
        for i in range(SCREEN_WIDTH * SCREEN_HEIGHT):
            t = self.u8(W_TILE_MAP + i)
            if t in (0xED, 0xEE):
                return True
        return False

    def overworld_locked(self) -> bool:
        if self.in_battle:
            return True
        if self.font_loaded:
            return True
        if self.joy_ignore:
            return True
        if self.joypad_disabled:
            return True
        if self.scripted_movement:
            return True
        if self.walk_counter:
            return True
        if self.movement_status == 3:
            return True
        return False

    def overworld_idle(self) -> bool:
        return not self.overworld_locked()

    def hp_frac(self) -> float:
        mon = self.lead()
        if not mon or mon.max_hp <= 0:
            return 1.0
        return mon.hp / mon.max_hp

    def critical_hp(self) -> bool:
        return self.hp_frac() <= 0.25

    @property
    def wy(self) -> int:
        return self.u8(R_WY)

    @property
    def tile0(self) -> int:
        return self.u8(W_TILE_MAP)

    def overworld_visible(self) -> bool:
        """True when the LCD is showing a loaded map, not intro/fade blank."""
        t0 = self.tile0
        if t0 in (0x00, 0x7F):
            return False
        if self.wy < 0x80:
            return False
        return True

    def map_name(self) -> str:
        return MAP_NAMES.get(self.map_id, f"map_{self.map_id:02X}")

    def summary(self) -> str:
        mon = self.lead()
        hp = f"{mon.hp}/{mon.max_hp} lv{mon.level}" if mon else "-"
        return (
            f"{self.map_name()} ({self.map_id:02X}) xy=({self.x},{self.y}) "
            f"face={self.facing:02X} battle={self.in_battle} hp={hp} "
            f"badge={self.badges:02X} joy={self.joy_ignore:02X} "
            f"s5={self.status5:02X} walk={self.walk_counter} "
            f"font={int(self.font_loaded)} sim={self.simulated_joy} wy={self.wy:02X} "
            f"menu={self.current_menu_item}/{self.max_menu_item} keys={self.menu_watched_keys:02X} "
            f"top=({self.top_menu_x},{self.top_menu_y}) ehp={self.enemy_hp()}"
        )

    def addresses_alive(self) -> bool:
        """True if USA Red/Blue party/map addresses look populated after intro."""
        mid = self.map_id
        return mid <= 0xF7
