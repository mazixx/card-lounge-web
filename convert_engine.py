import ast
import copy
from pathlib import Path


SOURCE = Path("card_lounge_original.txt")

ENGINE_CLASSES = {
    "Engine",
    "Tournament",
    "BauCuaEngine",
    "BauCuaSession",
}

EXCLUDED_FUNCTIONS = {
    "main",
    "install",
    "install_baucua",
    "install_tienlen_lung",
    "install_tournament_penalties",
}


def target_name(node):
    if not isinstance(node, ast.Assign):
        return None

    if len(node.targets) != 1:
        return None

    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def assigns_engine(node):
    return (
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "Engine"
            for target in node.targets
        )
    )


def extract_installer(original, name, variables, functions, classes=()):
    result = copy.deepcopy(original)
    result.name = name
    result.body = []

    for node in original.body:
        if isinstance(node, ast.Assign):
            if target_name(node) in variables or assigns_engine(node):
                result.body.append(copy.deepcopy(node))

        elif isinstance(node, ast.FunctionDef):
            if node.name in functions:
                result.body.append(copy.deepcopy(node))

        elif isinstance(node, ast.ClassDef):
            if node.name in classes:
                result.body.append(copy.deepcopy(node))

    return result


def main():
    tree = ast.parse(
        SOURCE.read_text(encoding="utf-8-sig"),
        filename=str(SOURCE),
    )

    definitions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }

    required = {"install", "install_tienlen_lung"}

    if not required.issubset(definitions):
        raise SystemExit("File nguồn thiếu bản vá Poker hoặc Tiến lên.")

    kept = []

    for original in tree.body:
        node = copy.deepcopy(original)

        if isinstance(node, ast.Import):
            node.names = [
                alias for alias in node.names
                if not alias.name.startswith("tkinter")
            ]
            if node.names:
                kept.append(node)

        elif isinstance(node, ast.ImportFrom):
            if not (node.module or "").startswith("tkinter"):
                kept.append(node)

        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            kept.append(node)

        elif isinstance(node, ast.ClassDef):
            if node.name in ENGINE_CLASSES:
                kept.append(node)

        elif isinstance(node, ast.FunctionDef):
            if node.name not in EXCLUDED_FUNCTIONS:
                kept.append(node)

        # Không giữ lời gọi cấp module hoặc khối main Tkinter.

    poker = extract_installer(
        definitions["install"],
        "_install_poker",
        variables={
            "Engine",
            "OldTournament",
            "player_name",
            "cards_text",
            "poker_best",
            "equity_estimate",
            "poker_names",
            "old_engine_init",
            "old_options",
            "old_bot",
            "old_analyze",
            "old_summary",
        },
        functions={
            "engine_init",
            "start_poker",
            "poker_pay",
            "live_seats",
            "can_raise",
            "fraction_spend",
            "poker_action",
            "poker_progress",
            "settle_poker",
            "hand_label",
            "options",
            "bot",
            "analyze",
            "summary",
            "tournament_factory",
        },
        classes={"PokerTournament"},
    )

    # Đưa lớp và factory ra module để controller web sử dụng.
    poker.body.extend(ast.parse(
        'namespace["PokerTournament"] = PokerTournament\n'
        'namespace["Tournament"] = tournament_factory\n'
    ).body)

    lung = extract_installer(
        definitions["install_tienlen_lung"],
        "_install_lung",
        variables={
            "Engine",
            "old_start_tl",
            "old_analyze",
        },
        functions={
            "start_tl",
            "tl_active",
            "tl_finish_if_needed",
            "analyze",
        },
    )

    kept.extend([poker, lung])

    kept.extend(ast.parse(
        "_install_poker(globals())\n"
        "_install_lung(globals())\n"
    ).body)

    output_tree = ast.Module(body=kept, type_ignores=[])
    ast.fix_missing_locations(output_tree)

    forbidden = {"tk", "ttk", "messagebox", "ScrolledText", "CardLounge"}

    references = {
        node.id
        for node in ast.walk(output_tree)
        if isinstance(node, ast.Name)
    }

    if references & forbidden:
        raise SystemExit(
            "Engine vẫn còn tham chiếu giao diện: "
            + ", ".join(sorted(references & forbidden))
        )

    output = ast.unparse(output_tree) + "\n"
    compile(output, "engine.py", "exec")

    Path("engine.py").write_text(output, encoding="utf-8")
    print("Đã tạo engine.py, giữ Poker no-limit và luật lủng.")


if __name__ == "__main__":
    main()
