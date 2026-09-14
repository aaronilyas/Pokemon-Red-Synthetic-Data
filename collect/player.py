"""RAM-guided scripted run from boot to the Boulder Badge. No vision, no LLM."""

from __future__ import annotations

import traceback
from collections import deque
from pathlib import Path

from ram import (
    BIT_DISABLE_JOYPAD,
    EVENT_GOT_OAKS_PARCEL,
    EVENT_GOT_POKEDEX,
    EVENT_GOT_STARTER,
    EVENT_OAK_ASKED_TO_CHOOSE_MON,
    MAP_WARPS,
    FACE_DOWN,
    FACE_LEFT,
    FACE_RIGHT,
    FACE_UP,
    ITEM_ANTIDOTE,
    ITEM_OAKS_PARCEL,
    ITEM_POTION,
    MOVE_INFO,
    MOVE_LEECH_SEED,
    MOVE_TACKLE,
    MOVE_VINE_WHIP,
    OAKS_LAB,
    PALLET_TOWN,
    PEWTER_CITY,
    PEWTER_GYM,
    PEWTER_MART,
    PEWTER_POKECENTER,
    REDS_HOUSE_1F,
    REDS_HOUSE_2F,
    ROUTE_1,
    ROUTE_2,
    TYPE_GRASS,
    VIRIDIAN_CITY,
    VIRIDIAN_FOREST,
    FOREST_BLOCKED,
    VIRIDIAN_FOREST_NORTH_GATE,
    VIRIDIAN_FOREST_SOUTH_GATE,
    VIRIDIAN_MART,
    VIRIDIAN_POKECENTER,
    RAM,
    type_mult,
)

DIR_DELTA = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}
FACE_FOR = {
    "DOWN": FACE_DOWN,
    "UP": FACE_UP,
    "LEFT": FACE_LEFT,
    "RIGHT": FACE_RIGHT,
}
DIR_FOR_FACE = {v: k for k, v in FACE_FOR.items()}


class Stuck(Exception):
    def __init__(self, milestone: str, why: str):
        super().__init__(f"{milestone}: {why}")
        self.milestone = milestone
        self.why = why


class Player:
    def __init__(self, pyboy, recorder, ram: RAM, out_dir: Path, log_fn=print):
        self.pyboy = pyboy
        self.rec = recorder
        self.ram = ram
        self.out = Path(out_dir)
        self.log_fn = log_fn
        self.milestone = "boot"
        self.retries: list[dict] = []
        self.blocked: dict[int, set[tuple[int, int]]] = {}
        self._fail_count: dict[tuple[int, int, int], int] = {}
        self._no_move_steps = 0
        self._last_pos: tuple[int, int, int] | None = None
        self._milestone_store: dict[str, dict] = {}
        self.max_steps = 80_000
        self._progress = self.out / "progress.log"

    def log(self, msg: str) -> None:
        line = f"[{self.pyboy.frame_count:08d} {self.milestone} {self.ram.summary()}] {msg}"
        self.log_fn(line)
        with self._progress.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ------------------------------------------------------------------ I/O
    def commit(self, inputs: list[str], hold: int) -> None:
        if self.rec.steps >= self.max_steps:
            raise Stuck(self.milestone, f"hit max_steps={self.max_steps}")
        pos_before = self.ram.pos
        hp_before = None if not self.ram.lead() else self.ram.lead().hp
        battle_before = self.ram.in_battle
        self.rec.commit(inputs, hold)
        pos_after = self.ram.pos
        hp_after = None if not self.ram.lead() else self.ram.lead().hp
        if (
            pos_after != pos_before
            or self.ram.in_battle
            or battle_before
            or hp_after != hp_before
            or self.ram.has_boulder
        ):
            self._no_move_steps = 0
            self._last_pos = pos_after
        else:
            self._no_move_steps += 1
        if self._no_move_steps >= 400:
            if self._maybe_retry_milestone():
                return
            raise Stuck(self.milestone, "400 recorded steps with no coordinate/map change")
        if self.rec.steps % 200 == 0:
            self.log(f"steps={self.rec.steps} last={inputs}/{hold}")

    def a(self, hold: int = 8) -> None:
        self.commit(["A"], hold)

    def b(self, hold: int = 8) -> None:
        self.commit(["B"], hold)

    def start(self, hold: int = 8) -> None:
        self.commit(["START"], hold)

    def wait(self, hold: int = 8) -> None:
        self.commit([], hold)

    def pad(self, direction: str, hold: int = 16) -> None:
        self.commit([direction], hold)

    def wait_n(self, frames: int) -> None:
        while frames >= 32:
            self.wait(32)
            frames -= 32
        for h in (24, 16, 8):
            while frames >= h:
                self.wait(h)
                frames -= h

    # ------------------------------------------------------------------ state
    def save_milestone(self, name: str) -> None:
        self.milestone = name
        state_name = f"ms_{name}.state"
        self.rec.save_state(state_name)
        jsonl = self.rec.jsonl_path.read_text(encoding="utf-8") if self.rec.jsonl_path.exists() else ""
        self._milestone_store[name] = {
            "state": state_name,
            "jsonl": jsonl,
            "steps": self.rec.steps,
            "last_end": self.rec.last_end,
            "frame": int(self.pyboy.frame_count),
        }
        self.rec.save_state("last_milestone.state")
        self.log(f"saved milestone {name}")

    def restore_milestone(self, name: str) -> None:
        store = self._milestone_store[name]
        self.rec.jsonl_path.write_text(store["jsonl"], encoding="utf-8")
        self.rec.steps = store["steps"]
        self.rec.last_end = store["last_end"]
        self.rec.load_state(store["state"])
        self._no_move_steps = 0
        self.blocked.pop(self.ram.map_id, None)
        self.log(f"restored milestone {name}")

    def _maybe_retry_milestone(self) -> bool:
        if not self._milestone_store:
            return False
        if sum(1 for r in self.retries if r.get("milestone") == self.milestone) >= 3:
            return False
        name = list(self._milestone_store)[-1]
        self.retries.append(
            {
                "milestone": self.milestone,
                "restored": name,
                "frame": int(self.pyboy.frame_count),
                "pos": list(self.ram.pos),
            }
        )
        self.log(f"400-step stall; restoring {name}")
        self.restore_milestone(name)
        return True

    # ------------------------------------------------------------------ battles / text
    def _tile_cursor(self, x: int, y: int) -> bool:
        return self.ram.tile(x, y) in (0xED, 0xEE)

    def _command_cursor_visible(self) -> bool:
        return any(
            self._tile_cursor(x, y) for x, y in ((9, 14), (9, 16), (15, 14), (15, 16))
        )

    def _move_cursor_visible(self) -> bool:
        return any(self._tile_cursor(4, y) or self._tile_cursor(5, y) for y in range(12, 18))

    def _in_command_menu(self) -> bool:
        """DisplayBattleMenu is two 2-item columns, not a 4-item list.

        Left (FIGHT/ITEM): max=1, keys=A|RIGHT=0x11, y=14, x=9.
        Right (PKMN/RUN):  max=1, keys=A|LEFT=0x21,  y=14, x=15.
        Ignore leftover RAM when the ▶ cursor is not actually on that box.
        """
        if not self.ram.in_battle:
            return False
        keys = self.ram.menu_watched_keys
        mx = self.ram.max_menu_item
        if not (mx == 1 and keys in (0x11, 0x21)):
            if not (self.ram.top_menu_y == 0x0E and mx == 1 and keys):
                return False
        return self._command_cursor_visible()

    def _in_move_menu(self) -> bool:
        """MoveSelectionMenu: keys=0xC7, 1-indexed cursor, max=n_moves+1."""
        if not self.ram.in_battle:
            return False
        keys = self.ram.menu_watched_keys
        looks = keys == 0xC7 or (
            self.ram.top_menu_y == 0x0C
            and self.ram.top_menu_x == 0x05
            and (keys & 0xC0)
            and self.ram.max_menu_item >= 2
        )
        return bool(looks and self._move_cursor_visible())

    def _n_moves(self) -> int:
        moves, _pp = self._moves_and_pp()
        return sum(1 for m in moves if m)

    def _moves_and_pp(self) -> tuple[list[int], list[int]]:
        moves = self.ram.battle_moves()
        pp = self.ram.battle_pp()
        lead = self.ram.lead()
        if lead:
            party_pp = [p & 0x3F for p in lead.pp]
            if sum(pp) == 0 or (lead.moves[0] and pp[0] > 0 and party_pp[0] == 0):
                moves = list(lead.moves)
                pp = party_pp
            else:
                pp = [min(a, b) for a, b in zip(pp, party_pp)]
        return moves, pp

    def best_move_index(self) -> int:
        moves, pp = self._moves_and_pp()
        et1, et2 = self.ram.enemy_types()
        my_t1 = self.ram.u8(0xD019)
        my_t2 = self.ram.u8(0xD01A)
        best_i, best_s = 0, -1
        any_pp = False
        for i, mv in enumerate(moves):
            if mv == 0 or i >= 4:
                continue
            if pp[i] <= 0:
                continue
            any_pp = True
            power, typ = MOVE_INFO.get(mv, (40 if mv else 0, 0))
            if mv == MOVE_VINE_WHIP:
                power = 35
                typ = TYPE_GRASS
            score = power
            if power <= 0:
                score = 12 if mv == MOVE_LEECH_SEED else 1
            else:
                score *= type_mult(typ, et1, et2)
                if typ in (my_t1, my_t2):
                    score = int(score * 1.5)
            if mv == MOVE_VINE_WHIP:
                score += 50
            if mv == MOVE_TACKLE:
                score += 5
            if score > best_s:
                best_s, best_i = score, i
        if not any_pp:
            return 0
        return best_i

    def _move_cursor_to(self, target: int, vertical: bool = True, timeout: int = 12) -> None:
        for _ in range(timeout):
            cur = self.ram.current_menu_item
            if cur == target:
                return
            if vertical:
                self.pad("DOWN" if (target - cur) % 8 <= 4 else "UP", 8)
            else:
                if target % 2 != cur % 2:
                    self.pad("RIGHT" if cur % 2 == 0 else "LEFT", 8)
                elif target // 2 != cur // 2:
                    self.pad("DOWN" if cur < 2 else "UP", 8)
                else:
                    self.pad("DOWN", 8)
            self.wait(8)

    def _command_to_fight(self) -> None:
        keys = self.ram.menu_watched_keys
        cur = self.ram.current_menu_item
        if keys == 0x21:
            self.pad("LEFT", 16)
            self.wait(8)
            return
        if cur != 0:
            self.pad("UP", 16)
            self.wait(8)
            return
        self.a(8)
        self.wait(8)

    def _command_to_item(self) -> None:
        keys = self.ram.menu_watched_keys
        cur = self.ram.current_menu_item
        if keys == 0x21:
            self.pad("LEFT", 16)
            self.wait(8)
            return
        if cur != 1:
            self.pad("DOWN", 16)
            self.wait(8)
            return
        self.a(8)
        self.wait(8)

    def _pick_fight_best_move(self) -> None:
        if self._in_command_menu():
            self._command_to_fight()
            return
        if self._in_move_menu():
            idx = self.best_move_index()
            target = idx + 1  # MoveSelectionMenu is 1-indexed
            n = self._n_moves()
            if n and target > n:
                target = n
            if target < 1:
                target = 1
            for _ in range(8):
                if not self._in_move_menu():
                    break
                cur = self.ram.current_menu_item
                if cur == target:
                    self.a(8)
                    self.wait(8)
                    return
                if cur == 0:
                    self.pad("DOWN", 16)
                elif cur > target:
                    self.pad("UP", 16)
                else:
                    self.pad("DOWN", 16)
                self.wait(8)
            self.a(8)
            self.wait(8)
            return
        self.a(8)
        self.wait(8)

    def _use_potion_in_battle(self) -> bool:
        if not self.ram.has_item(ITEM_POTION):
            return False
        if self._in_command_menu():
            self._command_to_item()
            return False
        bag = self.ram.bag()
        potion_index = next((i for i, (it, _q) in enumerate(bag) if it == ITEM_POTION), None)
        if potion_index is None:
            self.b(8)
            self.wait(8)
            return False
        keys = self.ram.menu_watched_keys
        if keys in (0x03, 0x07) or (keys and self.ram.max_menu_item >= 0):
            self._move_cursor_to(potion_index, vertical=True)
            self.a(8)
            self.wait(16)
            self._move_cursor_to(0, vertical=True)
            self.a(8)
            self.wait(16)
            for _ in range(12):
                if self.ram.in_battle and not self.ram.font_loaded:
                    break
                self.a(8)
                self.wait(8)
            return True
        self.a(8)
        self.wait(8)
        return False

    def fight_battle(self) -> None:
        if not self.ram.in_battle:
            return
        if self.rec.steps >= self.max_steps:
            return
        self.log("battle start")
        idle_menus = 0
        last_hp = None
        idle_hp = 0
        loops = 0
        want_potion = False
        while self.ram.in_battle:
            loops += 1
            if self.rec.steps >= self.max_steps:
                return
            if self.ram.has_boulder and self.ram.map_id == PEWTER_GYM:
                break
            hp_now, mx = self.ram.battle_hp()
            if hp_now != last_hp:
                last_hp, idle_hp = hp_now, 0
            else:
                idle_hp += 1
            frac = (hp_now / mx) if mx else 1.0
            if frac <= 0.25 and self.ram.has_item(ITEM_POTION):
                want_potion = True
            if want_potion and not self.ram.has_item(ITEM_POTION):
                want_potion = False
            if loops % 80 == 0:
                self.log(f"battle loop {loops} want_potion={want_potion}")
            if hp_now == 0:
                self.a(8)
                self.wait(8)
                continue
            if self._in_command_menu():
                idle_menus = 0
                if want_potion:
                    self._command_to_item()
                else:
                    self._command_to_fight()
                continue
            if self._in_move_menu():
                idle_menus = 0
                want_potion = False
                if self.ram.current_menu_item == 0:
                    self.pad("DOWN", 16)
                    self.wait(8)
                elif idle_hp > 15:
                    self.a(8)
                    self.wait(8)
                else:
                    self._pick_fight_best_move()
                continue
            keys = self.ram.menu_watched_keys
            mx_item = self.ram.max_menu_item
            # SWITCH / STATS / CANCEL on a party slot
            if keys in (0x01, 0x02, 0x03) and mx_item == 2 and self.ram.top_menu_x >= 0x0B:
                self.b(8)
                self.wait(8)
                continue
            if want_potion and keys in (0x03, 0x07):
                if self._use_potion_in_battle():
                    want_potion = False
                continue
            if keys in (0x03, 0x07) and not want_potion:
                self.b(8)
                self.wait(8)
                continue
            idle_menus += 1
            self.a(8)
            self.wait(8)
            if idle_menus > 50 or idle_hp > 60:
                self.b(8)
                self.wait(8)
                idle_menus = 0
                idle_hp = 0
        for _ in range(40):
            if self.ram.has_boulder:
                break
            if self.ram.in_battle:
                break
            if self.ram.overworld_idle() and not self.ram.font_loaded:
                break
            self.a(8)
            self.wait(8)
        self.log("battle end")

    def mash_text(self, limit: int = 80) -> None:
        for _ in range(limit):
            if self.ram.in_battle:
                self.fight_battle()
                return
            if self.ram.has_boulder:
                return
            locked = (
                self.ram.font_loaded
                or self.ram.joy_ignore
                or self.ram.joypad_disabled
            )
            if not locked and self.ram.overworld_idle():
                return
            if self.ram.scripted_movement and not self.ram.font_loaded:
                self.wait(16)
                continue
            self.a(8)
            self.wait(8)

    def settle(self) -> None:
        """Handle battles/text/scripted walks until we can act in the overworld."""
        spins = 0
        while spins < 200:
            spins += 1
            if self.ram.has_boulder:
                return
            if self.ram.in_battle:
                self.fight_battle()
                continue
            if self.ram.scripted_movement and not self.ram.font_loaded:
                self.wait(16)
                continue
            if self.ram.font_loaded or self.ram.joy_ignore or self.ram.joypad_disabled:
                self.mash_text(limit=8)
                continue
            if self.ram.walk_counter or self.ram.movement_status == 3:
                self.wait(8)
                continue
            # Fade: pal offset or map mid-change. Waiting is fine.
            if self.ram.pal_offset:
                self.wait(8)
                continue
            if self.ram.wy < 0x88 and not self.ram.font_loaded:
                self.wait(8)
                continue
            return
        # One more battle/text pass then give up to caller.
        if self.ram.in_battle:
            self.fight_battle()

    # ------------------------------------------------------------------ walking
    def _blocked_set(self) -> set[tuple[int, int]]:
        s = self.blocked.setdefault(self.ram.map_id, set())
        if self.ram.map_id == VIRIDIAN_FOREST:
            s.update(FOREST_BLOCKED)
        return s

    def _finish_step(self, map_before: int, xy_before: tuple[int, int]) -> bool:
        for _ in range(4):
            if self.ram.walk_counter or self.ram.movement_status == 3:
                self.wait(8)
            else:
                break
        if self.ram.in_battle:
            self.fight_battle()
            return self.ram.map_id != map_before or self.ram.xy != xy_before
        if self.ram.font_loaded or self.ram.joy_ignore:
            self.mash_text()
        return self.ram.map_id != map_before or self.ram.xy != xy_before

    def try_step(self, direction: str) -> bool:
        self.settle()
        if self.ram.in_battle:
            self.fight_battle()
        if self.ram.in_battle:
            return False
        map_before = self.ram.map_id
        xy_before = self.ram.xy
        facing_before = self.ram.facing
        self.pad(direction, 16)
        if self._finish_step(map_before, xy_before):
            return True
        # First hold may only have turned the sprite; take the actual step.
        if self.ram.facing != facing_before or self.ram.facing != FACE_FOR[direction]:
            self.pad(direction, 16)
            if self._finish_step(map_before, xy_before):
                return True
        return False

    def walk_onto(self, direction: str) -> None:
        """One tile or a warp/door. Then wait through fades."""
        before_map = self.ram.map_id
        moved = self.try_step(direction)
        if not moved and self.ram.map_id == before_map:
            # Turn then step (16 frames may have only turned).
            moved = self.try_step(direction)
        for _ in range(24):
            if self.ram.map_id != before_map:
                break
            if self.ram.pal_offset or self.ram.scripted_movement:
                self.wait(16)
                continue
            if self.ram.in_battle:
                self.fight_battle()
                continue
            if self.ram.font_loaded:
                self.mash_text(limit=4)
                continue
            break
        self.settle()

    def bfs_next(self, tx: int, ty: int) -> str | None:
        sx, sy = self.ram.xy
        if (sx, sy) == (tx, ty):
            return None
        blocked = set(self._blocked_set())
        for wx, wy in MAP_WARPS.get(self.ram.map_id, ()):
            if (wx, wy) != (tx, ty):
                blocked.add((wx, wy))
        w, h = 80, 80
        start = (sx, sy)
        q = deque([start])
        prev: dict[tuple[int, int], tuple[tuple[int, int], str]] = {}
        seen = {start}
        while q:
            x, y = q.popleft()
            for d, (dx, dy) in DIR_DELTA.items():
                nx, ny = x + dx, y + dy
                if nx < 0 or ny < 0 or nx >= w or ny >= h:
                    continue
                if (nx, ny) in blocked and (nx, ny) != (tx, ty):
                    continue
                if (nx, ny) in seen:
                    continue
                seen.add((nx, ny))
                prev[(nx, ny)] = ((x, y), d)
                if (nx, ny) == (tx, ty):
                    q.clear()
                    break
                q.append((nx, ny))
        if (tx, ty) not in prev:
            # Greedy fallback.
            dx, dy = tx - sx, ty - sy
            if abs(dx) >= abs(dy) and dx != 0:
                return "RIGHT" if dx > 0 else "LEFT"
            if dy != 0:
                return "DOWN" if dy > 0 else "UP"
            if dx != 0:
                return "RIGHT" if dx > 0 else "LEFT"
            return None
        node = (tx, ty)
        last_dir = None
        while node != start:
            node, last_dir = prev[node]
            if node == start:
                return last_dir
        return last_dir

    def go(self, tx: int, ty: int, *, map_id: int | None = None, limit: int = 400) -> None:
        target_map = map_id if map_id is not None else self.ram.map_id
        fails = 0
        for _ in range(limit):
            self.settle()
            if self.ram.map_id != target_map:
                return
            if self.ram.xy == (tx, ty):
                return
            d = self.bfs_next(tx, ty)
            if d is None:
                return
            before = self.ram.xy
            if not self.try_step(d):
                if self.ram.in_battle:
                    fails = 0
                    continue
                nx = before[0] + DIR_DELTA[d][0]
                ny = before[1] + DIR_DELTA[d][1]
                if not self.ram.in_battle and not self.ram.font_loaded:
                    # Require two fails before treating a tile as a wall so
                    # walking NPCs are not permanently marked blocked.
                    key = (self.ram.map_id, nx, ny)
                    self._fail_count[key] = self._fail_count.get(key, 0) + 1
                    if self._fail_count[key] >= 2:
                        self._blocked_set().add((nx, ny))
                fails += 1
                if fails >= 8:
                    # Nudge: try the other axis.
                    sx, sy = self.ram.xy
                    alt = []
                    if tx != sx:
                        alt.append("RIGHT" if tx > sx else "LEFT")
                    if ty != sy:
                        alt.append("DOWN" if ty > sy else "UP")
                    for a in alt + ["UP", "DOWN", "LEFT", "RIGHT"]:
                        if self.try_step(a):
                            fails = 0
                            break
                    else:
                        fails = 0
            else:
                fails = 0
        if self.ram.xy != (tx, ty) and self.ram.map_id == target_map:
            raise Stuck(self.milestone, f"go({tx},{ty}) ended at {self.ram.xy} map={self.ram.map_id}")

    def enter_map(self, direction: str, dest: int, timeout: int = 40) -> None:
        if self.ram.map_id == dest:
            self.settle()
            return
        before = self.ram.map_id
        self.walk_onto(direction)
        for _ in range(timeout):
            if self.ram.map_id == dest:
                self.settle()
                return
            if self.ram.map_id != before:
                self.settle()
                return
            if self.ram.in_battle:
                self.fight_battle()
                continue
            if self.ram.font_loaded or self.ram.pal_offset or self.ram.scripted_movement:
                self.wait(16)
                continue
            self.pad(direction, 16)
            for _ in range(6):
                if self.ram.walk_counter == 0 and self.ram.movement_status != 3:
                    break
                self.wait(8)
            self.wait(16)
        if self.ram.map_id == before:
            raise Stuck(self.milestone, f"failed to enter map {dest:02X} via {direction}")

    def face(self, direction: str) -> None:
        if self.ram.facing == FACE_FOR[direction]:
            return
        self.pad(direction, 8)
        self.wait(8)

    def talk(self, direction: str, mashes: int = 60, *, step: bool = True) -> None:
        self.settle()
        if step:
            self.pad(direction, 16)
        else:
            self.face(direction)
        self.a(8)
        self.wait(8)
        self.mash_text(limit=mashes)
        self.settle()

    # ------------------------------------------------------------------ intro
    def ms_boot(self) -> None:
        self.milestone = "boot"
        self.rec.save_state("start.state")
        self.log("recording start.state")
        # Mash intro / title / new game / oak / naming until the bedroom LCD
        # is up AND a D-pad hold actually changes coordinates. wCurMap is set
        # to REDS_HOUSE_2F during Oak's speech, long before sprites load.
        probes = 0
        while True:
            if self.rec.steps > 4000:
                raise Stuck("boot", "never reached a controllable bedroom")
            self.start(8)
            self.wait(16)
            self.a(8)
            self.wait(16)
            probes += 1
            if probes % 8 == 0:
                self.start(8)
                self.wait(16)
            if not (
                self.ram.map_id == REDS_HOUSE_2F
                and self.ram.party_count == 0
                and self.ram.overworld_visible()
                and not self.ram.font_loaded
            ):
                continue
            before = self.ram.xy
            self.pad("DOWN", 16)
            self.wait(16)
            if self.ram.xy != before and self.ram.map_id == REDS_HOUSE_2F:
                break
            self.pad("RIGHT", 16)
            self.wait(16)
            if self.ram.xy != before and self.ram.map_id == REDS_HOUSE_2F:
                break
        self.settle()
        if self.ram.map_id != REDS_HOUSE_2F:
            raise Stuck("boot", f"map is {self.ram.map_id:02X} not bedroom")
        self.log(f"bedroom at {self.ram.xy} (walk confirmed)")
        self.save_milestone("bedroom")

    def ms_leave_house(self) -> None:
        self.milestone = "leave_house"
        # Stairs at (7, 1). Spawn is typically (3, 6).
        self.go(7, 1, map_id=REDS_HOUSE_2F)
        self.enter_map("UP", REDS_HOUSE_1F)
        self.settle()
        # Door at (2,7)/(3,7). Mom at (5,4) facing left — go around.
        if self.ram.map_id != REDS_HOUSE_1F:
            raise Stuck("leave_house", f"not 1F ({self.ram.map_id:02X})")
        self.go(3, 6, map_id=REDS_HOUSE_1F)
        self.go(3, 7, map_id=REDS_HOUSE_1F)
        self.enter_map("DOWN", PALLET_TOWN)
        self.settle()
        self.save_milestone("pallet")

    def ms_oak_lab_starter(self) -> None:
        self.milestone = "oak_intercept"
        if self.ram.map_id != PALLET_TOWN:
            raise Stuck(self.milestone, f"expected Pallet, got {self.ram.map_id:02X}")
        # North road is x≈8–11. y==1 trips Oak; don't treat (8,1) as a stand-on
        # target or go() fights the cutscene.
        x, y = self.ram.xy
        self.go(10, min(y, 8), map_id=PALLET_TOWN)
        self.go(10, 2, map_id=PALLET_TOWN)
        for _ in range(80):
            if self.ram.map_id == OAKS_LAB:
                break
            if self.ram.font_loaded or self.ram.joy_ignore or self.ram.scripted_movement:
                break
            if not self.try_step("UP"):
                self.try_step("LEFT")
                self.try_step("RIGHT")
                self.try_step("UP")
        # Oak cutscene: wait/mash until lab.
        for _ in range(400):
            if self.ram.map_id == OAKS_LAB:
                break
            if self.ram.in_battle:
                self.fight_battle()
                continue
            if self.ram.font_loaded or self.ram.joy_ignore:
                self.a(8)
                self.wait(8)
                continue
            if self.ram.scripted_movement:
                self.wait(16)
                continue
            self.a(8)
            self.wait(8)
            self.pad("UP", 16)
        self.settle()
        if self.ram.map_id != OAKS_LAB:
            raise Stuck("oak_intercept", f"never entered lab, map={self.ram.map_id:02X}")
        self.save_milestone("lab_entry")

        self.milestone = "pick_bulbasaur"
        # Wait until Oak has asked us to choose. wCurMap is lab long before
        # that speech; talking to a ball early only prints "those are Poké Balls".
        for _ in range(400):
            if self.ram.event(EVENT_OAK_ASKED_TO_CHOOSE_MON) or self.ram.event(EVENT_GOT_STARTER):
                break
            if self.ram.font_loaded or self.ram.joy_ignore or self.ram.scripted_movement:
                self.a(8)
                self.wait(8)
            else:
                self.a(8)
                self.wait(8)
        self.settle()
        # Bulbasaur ball at (8, 3). Stand at (8, 4) facing up. Do not walk
        # onto the table tile.
        self.go(8, 4, map_id=OAKS_LAB)
        for attempt in range(8):
            if self.ram.party_count >= 1 or self.ram.event(EVENT_GOT_STARTER):
                break
            if self.ram.xy != (8, 4):
                self.go(8, 4, map_id=OAKS_LAB)
            self.talk("UP", mashes=40, step=False)
            # Dex page + "You want Bulbasaur?" YES/NO (YES = item 0).
            for _ in range(40):
                if self.ram.party_count >= 1:
                    break
                if self.ram.tilemap_has_cursor() and self.ram.current_menu_item != 0:
                    self.pad("UP", 8)
                    self.wait(8)
                self.a(8)
                self.wait(8)
            if self.ram.party_count == 0:
                self.go(8, 4, map_id=OAKS_LAB)
        if self.ram.party_count < 1:
            raise Stuck("pick_bulbasaur", "did not obtain a starter")
        self.log(f"starter species={self.ram.lead().species if self.ram.lead() else '?'}")
        self.mash_text(limit=80)
        self.save_milestone("got_starter")

        self.milestone = "rival_lab"
        # Rival walks to Charmander; wait that out, then take the center aisle
        # to y=6 which is the script trigger.
        for _ in range(80):
            if self.ram.in_battle:
                break
            if self.ram.scripted_movement or self.ram.font_loaded or self.ram.joy_ignore:
                self.a(8)
                self.wait(8)
                continue
            break
        if not self.ram.in_battle:
            try:
                self.go(5, 5, map_id=OAKS_LAB, limit=120)
                self.go(5, 6, map_id=OAKS_LAB, limit=80)
            except Stuck:
                pass
        for _ in range(80):
            if self.ram.in_battle:
                break
            if self.ram.font_loaded or self.ram.joy_ignore or self.ram.scripted_movement:
                self.a(8)
                self.wait(8)
                continue
            if self.ram.y < 6:
                self.try_step("DOWN")
            else:
                self.a(8)
                self.wait(8)
        self.fight_battle()
        if self.ram.in_battle:
            self.fight_battle()
        self.mash_text(limit=120)
        self.settle()
        self.save_milestone("rival_done")

        # Leave lab south.
        self.milestone = "leave_lab"
        self.go(4, 11, map_id=OAKS_LAB, limit=200)
        self.enter_map("DOWN", PALLET_TOWN)
        self.settle()
        self.save_milestone("pallet_after_starter")

    def _leave_pallet_houses(self) -> None:
        if self.ram.map_id == REDS_HOUSE_2F:
            self.go(7, 1, map_id=REDS_HOUSE_2F)
            self.enter_map("UP", REDS_HOUSE_1F)
        if self.ram.map_id == REDS_HOUSE_1F:
            self.go(3, 7, map_id=REDS_HOUSE_1F)
            self.enter_map("DOWN", PALLET_TOWN)

    def _to_route1_from_pallet(self) -> None:
        self._leave_pallet_houses()
        if self.ram.map_id != PALLET_TOWN:
            return
        self.go(10, 6, map_id=PALLET_TOWN, limit=200)
        self.go(10, 2, map_id=PALLET_TOWN, limit=200)
        for _ in range(24):
            if self.ram.map_id == ROUTE_1:
                return
            if self.ram.in_battle:
                self.fight_battle()
                continue
            self.walk_onto("UP")

    def _to_viridian(self) -> None:
        for _ in range(40):
            self.settle()
            if self.ram.map_id == VIRIDIAN_CITY:
                return
            if self.ram.map_id in (REDS_HOUSE_1F, REDS_HOUSE_2F, PALLET_TOWN, OAKS_LAB):
                if self.ram.map_id == OAKS_LAB:
                    self.go(4, 11, map_id=OAKS_LAB, limit=120)
                    self.enter_map("DOWN", PALLET_TOWN)
                self._to_route1_from_pallet()
                continue
            if self.ram.map_id == ROUTE_1:
                self.go(10, 2, map_id=ROUTE_1, limit=300)
                for _ in range(20):
                    if self.ram.map_id != ROUTE_1:
                        break
                    if self.ram.in_battle:
                        self.fight_battle()
                        continue
                    self.walk_onto("UP")
                continue
            # Unknown map: step north and hope.
            self.walk_onto("UP")
        if self.ram.map_id != VIRIDIAN_CITY:
            raise Stuck(self.milestone, f"could not reach Viridian (map={self.ram.map_id:02X} xy={self.ram.xy})")

    def ms_viridian_parcel(self) -> None:
        self.milestone = "route1_viridian"
        self._to_viridian()
        self.save_milestone("viridian")

        self.milestone = "mart_parcel"
        # Mart door (29, 19).
        self.go(29, 20, map_id=VIRIDIAN_CITY, limit=400)
        self.go(29, 19, map_id=VIRIDIAN_CITY)
        self.enter_map("UP", VIRIDIAN_MART)
        self.settle()
        # Clerk at (0, 5). Counter tile (1,5) is blocked; stand at (2,5).
        try:
            self.go(2, 5, map_id=VIRIDIAN_MART, limit=80)
        except Stuck:
            pass
        if not self.ram.has_item(ITEM_OAKS_PARCEL):
            self.talk("LEFT", mashes=80)
        if not self.ram.has_item(ITEM_OAKS_PARCEL) and not self.ram.event(EVENT_GOT_OAKS_PARCEL):
            self.talk("LEFT", mashes=80)
        self.mash_text(40)
        try:
            self.go(3, 7, map_id=VIRIDIAN_MART, limit=80)
        except Stuck:
            self.go(4, 7, map_id=VIRIDIAN_MART, limit=80)
        self.enter_map("DOWN", VIRIDIAN_CITY)
        self.settle()
        self.save_milestone("got_parcel")

        self.milestone = "deliver_parcel"
        for _ in range(30):
            self.settle()
            if self.ram.map_id == OAKS_LAB:
                break
            if self.ram.map_id == VIRIDIAN_CITY:
                self.go(20, 34, map_id=VIRIDIAN_CITY, limit=300)
                for _ in range(20):
                    if self.ram.map_id != VIRIDIAN_CITY:
                        break
                    self.walk_onto("DOWN")
                continue
            if self.ram.map_id == ROUTE_1:
                self.go(10, 33, map_id=ROUTE_1, limit=300)
                for _ in range(20):
                    if self.ram.map_id != ROUTE_1:
                        break
                    if self.ram.in_battle:
                        self.fight_battle()
                        continue
                    self.walk_onto("DOWN")
                continue
            if self.ram.map_id == PALLET_TOWN:
                self.go(12, 12, map_id=PALLET_TOWN, limit=200)
                self.go(12, 11, map_id=PALLET_TOWN, limit=80)
                self.enter_map("UP", OAKS_LAB)
                continue
            if self.ram.map_id in (REDS_HOUSE_1F, REDS_HOUSE_2F):
                self._leave_pallet_houses()
                continue
            self.walk_onto("DOWN")
        self.settle()
        if self.ram.map_id != OAKS_LAB:
            raise Stuck("deliver_parcel", f"not in lab ({self.ram.map_id:02X})")
        # Oak at (5, 2). Stand (5, 3) face up.
        self.go(5, 3, map_id=OAKS_LAB)
        self.talk("UP", mashes=200)
        for _ in range(250):
            if self.ram.event(EVENT_GOT_POKEDEX):
                break
            if self.ram.in_battle:
                self.fight_battle()
                continue
            if self.ram.font_loaded or self.ram.joy_ignore or self.ram.scripted_movement:
                self.a(8)
                self.wait(8)
                continue
            self.a(8)
            self.wait(8)
        if not self.ram.event(EVENT_GOT_POKEDEX):
            # Talk to Oak again.
            self.go(5, 3, map_id=OAKS_LAB)
            self.talk("UP", mashes=200)
        self.mash_text(80)
        self.settle()
        self.go(4, 11, map_id=OAKS_LAB, limit=200)
        self.enter_map("DOWN", PALLET_TOWN)
        self.settle()
        self.save_milestone("pokedex")

    def ms_forest_pewter(self) -> None:
        self.milestone = "back_to_viridian"
        self._to_viridian()
        # Optional center heal.
        if self.ram.hp_frac() < 0.7:
            self._heal_center(VIRIDIAN_CITY, 23, 25, VIRIDIAN_POKECENTER)
        self.save_milestone("viridian_ready")

        self.milestone = "route2_forest"
        self._reach_forest_and_pewter()

    def _enter_forest_south_gate(self) -> None:
        if self.ram.map_id == ROUTE_2:
            self.go(3, 43, map_id=ROUTE_2, limit=400)
            self.enter_map("UP", VIRIDIAN_FOREST_SOUTH_GATE)
        if self.ram.map_id == VIRIDIAN_FOREST_SOUTH_GATE:
            try:
                self.go(5, 1, map_id=VIRIDIAN_FOREST_SOUTH_GATE, limit=60)
            except Stuck:
                try:
                    self.go(4, 1, map_id=VIRIDIAN_FOREST_SOUTH_GATE, limit=40)
                except Stuck:
                    pass
            for _ in range(16):
                if self.ram.map_id != VIRIDIAN_FOREST_SOUTH_GATE:
                    break
                self.pad("UP", 16)
                self.wait(24)
        if self.ram.map_id == VIRIDIAN_FOREST_SOUTH_GATE:
            try:
                self.go(5, 1, map_id=VIRIDIAN_FOREST_SOUTH_GATE, limit=40)
            except Stuck:
                pass
            for _ in range(12):
                if self.ram.map_id != VIRIDIAN_FOREST_SOUTH_GATE:
                    break
                self.pad("UP", 16)
                self.wait(24)

    def _reach_forest_and_pewter(self) -> None:
        for attempt in range(16):
            self.settle()
            if self.ram.map_id == PEWTER_CITY:
                self.save_milestone("pewter")
                return
            if self.ram.map_id in (VIRIDIAN_POKECENTER, PEWTER_POKECENTER):
                try:
                    self.go(3, 7, map_id=self.ram.map_id, limit=80)
                except Stuck:
                    pass
                dest = VIRIDIAN_CITY if self.ram.map_id == VIRIDIAN_POKECENTER else PEWTER_CITY
                self.enter_map("DOWN", dest)
                continue
            if self.ram.map_id == VIRIDIAN_CITY:
                if self.ram.hp_frac() < 0.7:
                    self._heal_center(VIRIDIAN_CITY, 23, 25, VIRIDIAN_POKECENTER)
                self.go(18, 2, map_id=VIRIDIAN_CITY, limit=300)
                for _ in range(20):
                    if self.ram.map_id != VIRIDIAN_CITY:
                        break
                    self.walk_onto("UP")
                continue
            if self.ram.map_id == ROUTE_2:
                # South of forest vs north of forest: y>=20 is south of the woods.
                if self.ram.y >= 20:
                    self._enter_forest_south_gate()
                else:
                    # Pewter's connection is a 2-tile gap at x=8–9, y=0–1.
                    # UP from x=3–5 y=2 walks into trees.
                    if "route2_north" not in self._milestone_store:
                        self.save_milestone("route2_north")
                    try:
                        self.go(8, 2, map_id=ROUTE_2, limit=200)
                    except Stuck:
                        try:
                            self.go(9, 2, map_id=ROUTE_2, limit=80)
                        except Stuck:
                            pass
                    for _ in range(24):
                        if self.ram.map_id != ROUTE_2:
                            break
                        if self.ram.in_battle:
                            self.fight_battle()
                            continue
                        self.walk_onto("UP")
                continue
            if self.ram.map_id == VIRIDIAN_FOREST_SOUTH_GATE:
                self._enter_forest_south_gate()
                continue
            if self.ram.map_id == VIRIDIAN_FOREST:
                if attempt == 0:
                    self.save_milestone("forest")
                try:
                    self._traverse_forest()
                except Stuck as e:
                    self.log(f"forest attempt {attempt} {e}")
                    self.blocked[VIRIDIAN_FOREST] = set(FOREST_BLOCKED)
                continue
            if self.ram.map_id == VIRIDIAN_FOREST_NORTH_GATE:
                # Same as the south gate: (4,1) UP is a wall; (5,1) UP warps.
                try:
                    self.go(5, 1, map_id=VIRIDIAN_FOREST_NORTH_GATE, limit=40)
                except Stuck:
                    try:
                        self.go(4, 1, map_id=VIRIDIAN_FOREST_NORTH_GATE, limit=20)
                    except Stuck:
                        pass
                for xdoor in (5, 4):
                    if self.ram.map_id != VIRIDIAN_FOREST_NORTH_GATE:
                        break
                    if self.ram.xy != (xdoor, 1):
                        try:
                            self.go(xdoor, 1, map_id=VIRIDIAN_FOREST_NORTH_GATE, limit=20)
                        except Stuck:
                            continue
                    try:
                        self.enter_map("UP", ROUTE_2, timeout=16)
                    except Stuck:
                        continue
                if self.ram.map_id == VIRIDIAN_FOREST_NORTH_GATE:
                    self.enter_map("UP", ROUTE_2)
                continue
            if self.ram.map_id in (PALLET_TOWN, ROUTE_1, OAKS_LAB, REDS_HOUSE_1F, REDS_HOUSE_2F):
                self._to_viridian()
                continue
            self.walk_onto("UP")
        if self.ram.map_id != PEWTER_CITY:
            raise Stuck("forest_traverse", f"not pewter ({self.ram.map_id:02X})")
        self.save_milestone("pewter")

    def _exit_forest_north(self) -> None:
        try:
            self.go(1, 1, map_id=VIRIDIAN_FOREST, limit=120)
        except Stuck:
            try:
                self.go(2, 1, map_id=VIRIDIAN_FOREST, limit=60)
            except Stuck:
                pass
        for _ in range(16):
            if self.ram.map_id != VIRIDIAN_FOREST:
                return
            if self.ram.in_battle:
                self.fight_battle()
                continue
            self.pad("UP", 16)
            self.wait(24)

    def _traverse_forest(self) -> None:
        self.milestone = "forest_traverse"
        # North warps are (1,0)/(2,0). y<=12 is the north chamber; leave there.
        if self.ram.map_id == VIRIDIAN_FOREST and self.ram.y <= 12:
            self._exit_forest_north()
            return
        # South gap (15–18,47) → open row y=40–43 → x=6–8 channel through
        # y=34–39 trees → y=30–31 west opening → x=1–2 north corridor.
        for wx, wy in (
            (16, 44),
            (16, 42),
            (8, 42),
            (7, 34),
            (7, 32),
            (6, 30),
            (2, 30),
            (2, 22),
            (2, 12),
            (2, 2),
        ):
            if self.ram.map_id != VIRIDIAN_FOREST:
                return
            if self.ram.y <= 12:
                self._exit_forest_north()
                return
            try:
                self.go(wx, wy, map_id=VIRIDIAN_FOREST, limit=250)
            except Stuck:
                self.log(f"forest waypoint ({wx},{wy}) skip")
                self.blocked[VIRIDIAN_FOREST] = set(FOREST_BLOCKED)
        if self.ram.map_id == VIRIDIAN_FOREST:
            self._exit_forest_north()

    def _grind_until_vine_whip(self) -> None:
        lead = self.ram.lead()
        if not lead:
            return
        if MOVE_VINE_WHIP in lead.moves or lead.level >= 13:
            return
        self.log(f"grinding from lv{lead.level}")
        # Pace a short corridor; wilds will interrupt.
        origin = self.ram.xy
        loops = 0
        while loops < 80:
            lead = self.ram.lead()
            if lead and (MOVE_VINE_WHIP in lead.moves or lead.level >= 13):
                self.log(f"grind done lv{lead.level} moves={lead.moves}")
                return
            if self.ram.map_id != VIRIDIAN_FOREST:
                return
            if self.ram.critical_hp() and not self.ram.has_item(ITEM_POTION):
                self.log("grind abort: low HP, no potion")
                return
            self.try_step("LEFT")
            self.try_step("RIGHT")
            loops += 1
        self.go(*origin, map_id=VIRIDIAN_FOREST, limit=200)

    def _heal_center(self, city: int, door_x: int, door_y: int, interior: int) -> None:
        if self.ram.map_id != city:
            return
        self.go(door_x, door_y, map_id=city, limit=300)
        self.enter_map("UP", interior)
        try:
            self.go(3, 4, map_id=interior, limit=80)
        except Stuck:
            pass
        self.talk("UP", mashes=40)
        # YES to heal.
        for _ in range(16):
            if self.ram.overworld_idle() and not self.ram.font_loaded:
                break
            if self.ram.menu_watched_keys and self.ram.current_menu_item != 0:
                self.pad("UP", 8)
                self.wait(8)
            self.a(8)
            self.wait(8)
        self.mash_text(40)
        self.go(3, 7, map_id=interior)
        self.enter_map("DOWN", city)
        self.settle()

    def _leave_pewter_interior(self) -> None:
        if self.ram.map_id in (PEWTER_MART, PEWTER_POKECENTER):
            try:
                self.go(3, 7, map_id=self.ram.map_id, limit=80)
            except Stuck:
                pass
            self.enter_map("DOWN", PEWTER_CITY)

    def _ensure_pewter_city(self) -> None:
        self._leave_pewter_interior()
        if self.ram.map_id == PEWTER_GYM:
            try:
                self.go(4, 13, map_id=PEWTER_GYM, limit=80)
            except Stuck:
                pass
            self.enter_map("DOWN", PEWTER_CITY)
        if self.ram.map_id == ROUTE_2:
            try:
                self.go(8, 2, map_id=ROUTE_2, limit=120)
            except Stuck:
                try:
                    self.go(9, 2, map_id=ROUTE_2, limit=60)
                except Stuck:
                    pass
            for _ in range(16):
                if self.ram.map_id != ROUTE_2:
                    break
                if self.ram.in_battle:
                    self.fight_battle()
                    continue
                self.walk_onto("UP")
        if self.ram.map_id == PEWTER_CITY and self.ram.y >= 34:
            # Spawned on the Route 2 connection row; step north off it.
            self.try_step("UP")
            self.try_step("UP")

    def _buy_potions_pewter(self) -> None:
        if self.ram.map_id != PEWTER_CITY:
            return
        if self.ram.bag_qty(ITEM_POTION) >= 3:
            return
        self.go(23, 17, map_id=PEWTER_CITY, limit=300)
        self.enter_map("UP", PEWTER_MART)
        try:
            self.go(2, 5, map_id=PEWTER_MART, limit=80)
        except Stuck:
            pass
        self.talk("LEFT", mashes=20)
        # BUY/SELL/QUIT: BUY = 0
        for _ in range(8):
            if self.ram.menu_watched_keys:
                break
            self.a(8)
            self.wait(8)
        self._move_cursor_to(0, vertical=True)
        self.a(8)
        self.wait(16)
        # Item list: Potion is typically index 1 in Pewter.
        self.pad("DOWN", 8)
        self.wait(8)
        self.a(8)
        self.wait(16)
        # Quantity: tap RIGHT a few times then A.
        for _ in range(4):
            self.pad("RIGHT", 8)
            self.wait(8)
        self.a(8)
        self.wait(16)
        for _ in range(10):
            self.b(8)
            self.wait(8)
            if self.ram.overworld_idle() and not self.ram.font_loaded:
                break
        self._leave_pewter_interior()
        self.settle()

    def ms_brock(self) -> None:
        self.milestone = "pewter_prep"
        self._ensure_pewter_city()
        if self.ram.hp_frac() < 0.85:
            self._heal_center(PEWTER_CITY, 13, 25, PEWTER_POKECENTER)
        self._ensure_pewter_city()
        self.save_milestone("pewter_healed")

        self.milestone = "pewter_grind"
        for _g in range(12):
            lead = self.ram.lead()
            if lead and (lead.level >= 12 or MOVE_VINE_WHIP in lead.moves):
                break
            if self.ram.map_id == PEWTER_CITY:
                if self.ram.hp_frac() < 0.7:
                    self._heal_center(PEWTER_CITY, 13, 25, PEWTER_POKECENTER)
                    self._ensure_pewter_city()
                try:
                    self.go(18, 35, map_id=PEWTER_CITY, limit=200)
                except Stuck:
                    pass
                for _ in range(10):
                    if self.ram.map_id != PEWTER_CITY:
                        break
                    self.walk_onto("DOWN")
            if self.ram.map_id == ROUTE_2:
                try:
                    self.go(5, 3, map_id=ROUTE_2, limit=80)
                except Stuck:
                    try:
                        self.go(4, 4, map_id=ROUTE_2, limit=40)
                    except Stuck:
                        pass
                for n in range(80):
                    lead = self.ram.lead()
                    if lead and (lead.level >= 12 or MOVE_VINE_WHIP in lead.moves):
                        break
                    if self.ram.hp_frac() < 0.3:
                        break
                    self.try_step("LEFT" if n % 2 == 0 else "RIGHT")
                if self.ram.hp_frac() < 0.3:
                    self._ensure_pewter_city()
        self._ensure_pewter_city()
        if self.ram.hp_frac() < 0.9:
            self._heal_center(PEWTER_CITY, 13, 25, PEWTER_POKECENTER)
        self._ensure_pewter_city()
        self.save_milestone("pewter_healed")

        self.milestone = "pewter_gym"
        for attempt in range(12):
            if self.ram.has_boulder:
                self.log("Boulder Badge obtained")
                return
            self._ensure_pewter_city()
            if self.ram.hp_frac() < 0.9:
                self._heal_center(PEWTER_CITY, 13, 25, PEWTER_POKECENTER)
            self._ensure_pewter_city()
            self.go(16, 17, map_id=PEWTER_CITY, limit=400)
            try:
                self.enter_map("UP", PEWTER_GYM)
            except Stuck:
                continue
            if self.ram.map_id != PEWTER_GYM:
                continue
            self.settle()
            # Jr trainer at (3,6) faces right. Walk the west column to skip him
            # so Brock gets a full-HP lead.
            try:
                self.go(2, 12, map_id=PEWTER_GYM, limit=40)
                self.go(2, 2, map_id=PEWTER_GYM, limit=100)
                self.go(4, 2, map_id=PEWTER_GYM, limit=40)
            except Stuck:
                try:
                    self.go(4, 2, map_id=PEWTER_GYM, limit=80)
                except Stuck:
                    pass
            self.settle()
            if self.ram.in_battle:
                self.fight_battle()
            if self.ram.has_boulder:
                self.log("Boulder Badge obtained")
                return
            if self.ram.map_id != PEWTER_GYM:
                continue
            for _ in range(10):
                if self.ram.has_boulder:
                    self.log("Boulder Badge obtained")
                    return
                if self.ram.map_id != PEWTER_GYM:
                    break
                if self.ram.in_battle:
                    self.fight_battle()
                    continue
                self.talk("UP", mashes=40)
            if self.ram.has_boulder:
                self.log("Boulder Badge obtained")
                return
        if not self.ram.has_boulder:
            raise Stuck("pewter_gym", "beat sequence finished without badge bit")

    def play(self) -> dict:
        try:
            self.ms_boot()
            self.ms_leave_house()
            self.ms_oak_lab_starter()
            self.ms_viridian_parcel()
            self.ms_forest_pewter()
            self.ms_brock()
            self.settle()
            # Keep mashing a little if the bit is about to flip.
            for _ in range(40):
                if self.ram.has_boulder:
                    break
                self.a(8)
                self.wait(8)
            if not self.ram.has_boulder:
                raise Stuck(self.milestone, "no boulder badge at end")
            self.rec.save_state("end.state")
            self.log("DONE boulder badge")
            return {
                "result": "boulder_badge",
                "milestone": "brock",
                "retries": self.retries,
            }
        except Stuck as e:
            self.log(f"STUCK {e}")
            self.rec.save_state("end.state")
            return {
                "result": "stuck",
                "milestone": e.milestone,
                "why": e.why,
                "retries": self.retries,
            }
        except Exception as e:
            self.log("CRASH " + traceback.format_exc())
            try:
                self.rec.save_state("end.state")
            except Exception:
                pass
            return {
                "result": "stuck",
                "milestone": self.milestone,
                "why": f"{type(e).__name__}: {e}",
                "retries": self.retries,
            }
