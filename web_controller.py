import itertools
import json

from engine import (
    Engine,
    Tournament,
    PokerTournament,
    BauCuaEngine,
    BauCuaSession,
    BC_FACES,
    player_name,
)


ROOM_IDS = itertools.count(1)
ROOM = None

KINDS = ("Tiến lên", "Tá lả", "Poker", "Ba cào", "Bầu cua")


class Room:
    def __init__(self, kind, tournament=False, seats=4):
        if kind not in KINDS:
            raise ValueError("Trò chơi không hợp lệ.")

        seats = int(seats)

        if not 2 <= seats <= 9:
            raise ValueError("Số ghế phải từ 2 đến 9.")

        self.kind = kind
        self.is_tournament = bool(tournament)

        self.seats = (
            seats
            if kind in ("Poker", "Ba cào", "Bầu cua")
            and not tournament
            else 4
        )

        self.room_id = next(ROOM_IDS)
        self.version = 0
        self.hand_number = 0
        self.logs = []
        self.accounted = False
        self.complete = False

        self.session = None
        self.bank = None
        self.previous_button = None
        self.places = {}
        self.eliminated = []

        if kind == "Bầu cua":
            self.session = BauCuaSession(
                tournament=self.is_tournament,
                seats=self.seats,
            )

        elif self.is_tournament:
            self.session = Tournament(kind)

        elif kind == "Poker":
            self.bank = {
                pid: 1000 for pid in range(self.seats)
            }

        self.start_hand()
        self.account()

    def log(self, text):
        self.logs.append(str(text))
        self.logs = self.logs[-160:]

    def start_hand(self):
        self.accounted = False
        session = self.session

        if self.kind == "Bầu cua":
            ids, messages = session.prepare()

            for message in messages:
                self.log(message)

            self.game = BauCuaEngine(
                ids,
                [session.bank[pid] for pid in ids],
                logger=self.log,
            )

        elif self.kind == "Poker":
            if self.is_tournament:
                roster = list(session.current_group)
                bank = session.bank
                previous = session.previous_button

                if (
                    session.rebuy_allowed()
                    and session.hand_index in (1, 2)
                ):
                    for pid in roster:
                        if bank[pid] == 0:
                            bank[pid] = 1000
                            session.points[pid] = 1000
                            session.rebuys[pid] += 1

                            self.log(
                                f"{player_name(pid)} nhận lại "
                                "1.000 xu tại vòng 32."
                            )
            else:
                roster = list(self.bank)
                bank = self.bank
                previous = self.previous_button

            ids = [pid for pid in roster if bank[pid] > 0]

            if len(ids) < 2:
                raise RuntimeError("Không đủ người để mở ván Poker.")

            if previous is None:
                button_pid = ids[0]
            else:
                start = roster.index(previous)
                button_pid = next(
                    roster[(start + offset) % len(roster)]
                    for offset in range(1, len(roster) + 1)
                    if roster[(start + offset) % len(roster)] in ids
                )

            if self.is_tournament:
                session.previous_button = button_pid
            else:
                self.previous_button = button_pid

            self.game = Engine(
                "Poker",
                ids,
                hand_number=ids.index(button_pid),
                logger=self.log,
                starting_stacks=[bank[pid] for pid in ids],
            )

        else:
            if session is not None:
                ids = list(session.current_group)
                shift = session.hand_index % len(ids)
                ids = ids[shift:] + ids[:shift]
                number = 0
            else:
                ids = list(range(self.seats))
                number = self.hand_number

            self.game = Engine(
                self.kind,
                ids,
                hand_number=number,
                logger=self.log,
            )

            self.game.score_tournament = (
                session
                if self.kind in ("Tiến lên", "Tá lả")
                else None
            )

        self.log("── " + self.label() + " ──")

    def label(self):
        session = self.session

        if self.complete:
            return "PHIÊN ĐÃ KẾT THÚC"

        if session is not None:
            return (
                f"{session.label} • Bàn {session.group_index + 1}"
                f" • Lượt {session.hand_index + 1}"
            )

        return f"Ván nhanh #{self.hand_number + 1}"

    def account(self):
        game = self.game

        if not game.done or self.accounted:
            return

        self.accounted = True

        if self.session is not None:
            self.session.record_hand(game)
            self.complete = self.session.complete
            return

        if self.kind != "Poker":
            return

        for seat, pid in enumerate(game.ids):
            self.bank[pid] = game.chips[seat]

        busted = [
            seat for seat in range(game.n)
            if game.chips[seat] == 0
            and game.ids[seat] not in self.places
        ]

        busted.sort(
            key=lambda seat: (
                game.starting_chips[seat], -seat
            )
        )

        for seat in busted:
            pid = game.ids[seat]
            place = self.seats - len(self.eliminated)

            self.places[pid] = place
            self.eliminated.append(pid)

            self.log(f"{player_name(pid)} bị loại, hạng {place}.")

        survivors = [
            pid for pid, chips in self.bank.items()
            if chips > 0
        ]

        if len(survivors) == 1:
            self.places[survivors[0]] = 1
            self.complete = True

    def next_hand(self):
        if not self.game.done:
            raise ValueError("Ván hiện tại chưa kết thúc.")

        self.account()

        if self.complete:
            return

        if self.session is not None:
            self.session.advance()

            if self.session.complete:
                self.complete = True
                self.log("Phiên đã kết thúc.")
                return
        else:
            self.hand_number += 1

        self.start_hand()
        self.account()

    def report(self):
        if self.session is not None:
            text = self.session.report()

            if self.kind == "Poker":
                # Phần mô tả report gốc chưa khớp logic rebuy mới.
                return (
                    "LƯU Ý LUẬT ĐANG ÁP DỤNG:\n"
                    "Chỉ vòng 32 được cấp lại 1.000 xu trước "
                    "ván 2/3 khi hết xu.\n"
                    "Các vòng sau không cấp lại; bàn có thể "
                    "kết thúc sớm khi còn tối đa một người có xu.\n"
                    "Một số dòng mô tả cũ bên dưới chưa cập nhật.\n\n"
                    + text
                )

            return text

        if self.kind == "Poker":
            lines = ["POKER — SỐ DƯ SAU VÁN", ""]

            for pid in sorted(
                self.bank,
                key=lambda pid: (
                    self.places.get(pid, 0),
                    -self.bank[pid],
                ),
            ):
                place = self.places.get(pid)
                state = f"Hạng {place}" if place else "Đang chơi"

                lines.append(
                    f"{player_name(pid)}: {self.bank[pid]:,} xu"
                    f" • {state}"
                )

            return "\n".join(lines)

        if self.game.done:
            return self.game.analyze()[0]

        return "Ván nhanh đang diễn ra, chưa có kết quả cuối."

    def snapshot(self):
        game = self.game
        human = game.human_seat()

        players = []

        for seat, pid in enumerate(game.ids):
            row = {
                "pid": pid,
                "name": game.name(seat),
                "active": not game.done and game.turn == seat,
                "count": len(game.hands[seat]),
                "cards": [],
                "melds": [],
                "playable": [],
                "detail": "",
            }

            if self.kind == "Bầu cua":
                row["detail"] = (
                    f"{game.chips[seat]:,} xu • "
                    f"Cược {sum(game.wagers[seat]):,}"
                    + (" • Đã chốt" if seat in game.locked else "")
                )

            elif self.kind == "Tá lả":
                row["cards"] = [
                    card if pid == 0 or game.done else None
                    for card in game.phom_loose[seat]
                ]

                row["melds"] = [
                    [
                        card if game.phom_card_visible(seat, card)
                        else None
                        for card in group
                    ]
                    for group in game.phom_melds[seat]
                ]

                row["detail"] = (
                    f"{row['count']} lá • "
                    f"Đánh {game.discard_count[seat]}/4"
                )

                if (
                    pid == 0
                    and not game.done
                    and game.turn == seat
                    and game.phase == "discard"
                ):
                    row["playable"] = list(game.phom_loose[seat])

            else:
                row["cards"] = [
                    card if game.visible(seat) else None
                    for card in game.hands[seat]
                ]

                if self.kind == "Poker":
                    tags = []

                    if seat == game.small_blind:
                        tags.append("SB")
                    if seat == game.big_blind:
                        tags.append("BB")
                    if seat in game.folded:
                        tags.append("FOLD")
                    elif game.chips[seat] == 0:
                        tags.append("HẾT XU" if game.done else "ALL-IN")

                    row["detail"] = (
                        f"{game.chips[seat]:,} xu"
                        f" • Cược vòng {game.bets[seat]:,}"
                        f" • {' / '.join(tags)}"
                    )

                elif self.kind == "Ba cào":
                    row["detail"] = f"{game.chips[seat]:,} xu"

                else:
                    row["detail"] = f"Còn {row['count']} lá"

                    if game.done:
                        row["detail"] += (
                            f" • Hạng {game.rank_map[seat]}"
                        )

                    if seat in getattr(game, "lung_seats", set()):
                        row["detail"] += " • LỦNG"
                    if seat in game.thoi_two:
                        row["detail"] += " • THỐI 2"

                    if pid == 0 and not game.done:
                        row["playable"] = list(game.hands[seat])

            players.append(row)

        human_turn = (
            not game.done
            and human is not None
            and game.turn == human
        )

        reaction = (
            human_turn
            and self.kind == "Tiến lên"
            and game.tl_reacting
        )

        if self.complete:
            mode = "finished"
        elif game.done:
            mode = "next" if human is None else "wait"
        elif human_turn:
            mode = "reaction" if reaction else "human"
        else:
            mode = "bot"

        summary = (
            "Xu ảo • Kết quả tạo sau khi mọi người chốt cược"
            if self.kind == "Bầu cua"
            else game.summary()
        )

        result = {
            "key": f"{self.room_id}:{self.version}",
            "kind": self.kind,
            "label": self.label(),
            "status": game.status,
            "summary": summary,
            "players": players,
            "center": game.board if self.kind == "Poker" else game.table,
            "options": game.options() if human_turn else [],
            "mode": mode,
            "done": game.done,
            "complete": self.complete,
            "logs": self.logs,
        }

        if self.kind == "Bầu cua":
            result["bc"] = {
                "faces": list(BC_FACES),
                "selected": game.selected_face,
                "wagers": (
                    game.wagers[human] if human is not None else [0] * 6
                ),
                "available": (
                    game.available(human) if human is not None else 0
                ),
                "dice": [BC_FACES[index] for index in game.dice],
            }

        return result


def handle(raw):
    global ROOM

    request = json.loads(raw)
    operation = request.get("op")
    text = None
    cards = None

    if operation == "new":
        ROOM = Room(
            request.get("kind", "Tiến lên"),
            request.get("tournament", False),
            request.get("seats", 4),
        )
    else:
        if ROOM is None:
            raise ValueError("Hãy bắt đầu phiên trước.")

        game = ROOM.game

        if operation == "action":
            if (
                game.done
                or game.turn < 0
                or game.ids[game.turn] != 0
            ):
                raise ValueError("Chưa đến lượt bạn.")

            selected = [
                tuple(card) for card in request.get("selected", [])
            ]

            game.action(request["action"], selected)

        elif operation == "bot":
            if (
                not game.done
                and game.turn >= 0
                and game.ids[game.turn] != 0
            ):
                game.bot()

        elif operation == "next":
            ROOM.next_hand()

        elif operation == "hint":
            text, cards = game.analyze()

        elif operation == "report":
            text = ROOM.report()

        else:
            raise ValueError("Lệnh không hợp lệ.")

        if operation not in ("hint", "report"):
            ROOM.version += 1
            ROOM.account()

    return json.dumps({
        "state": ROOM.snapshot(),
        "text": text,
        "cards": cards,
    }, ensure_ascii=False)
