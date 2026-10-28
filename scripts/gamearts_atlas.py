#!/usr/bin/env python3
"""Single owner of what an atlas's animation tags mean and when a set of tags is valid.

A tag names a run of frames of one sheet, inclusive at both ends, the way Aseprite's frame tags do: `from` and `to` are frame indexes,
`direction` is how the run plays (forward, reverse, pingpong starting forward, pingpong_reverse starting backward) and `repeat` is how many times
it plays, where 0 or absent means it repeats forever. Aseprite writes `repeat` only when it is above zero; so does the exchange export. The builder
and the sheet validator both ask this module, so a tag is judged the same way when it is written and when it is read back.

It also owns what makes a UI kit consistent: nine-slice margins that leave a stretchable centre, the states of a control (normal, hover, pressed,
disabled, focus, the names UI toolkits use) all present once and alike in size, and icon sets whose frames share a size and a padding.
"""
TAG_DIRECTIONS = ("forward", "reverse", "pingpong", "pingpong_reverse")
UI_STATES = ("normal", "hover", "pressed", "disabled", "focus")


def tag_problems(tags, frame_count):
    """Every reason a list of tags is not valid for a sheet of `frame_count` frames (an empty list means it is)."""
    problems, seen = [], set()
    for position, tag in enumerate(tags):
        label = f"tag {position}"
        if not isinstance(tag, dict):
            problems.append(f"{label} is not an object")
            continue
        name = tag.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"{label} needs a name")
        else:
            label = f"tag {name!r}"
            if name in seen:
                problems.append(f"{label}: the name is used twice")
            seen.add(name)
        first, last = tag.get("from"), tag.get("to")
        if type(first) is not int or type(last) is not int:
            problems.append(f"{label}: from and to must be whole numbers (frame indexes)")
        else:
            for value in sorted({first, last}):
                if not 0 <= value < frame_count:
                    problems.append(f"{label}: frame {value} does not exist (the sheet has {frame_count} frames)")
            if first > last:
                problems.append(f"{label}: from {first} is after to {last}")
        if tag.get("direction") is None:
            problems.append(f"{label}: has no direction; give one of {', '.join(TAG_DIRECTIONS)}")
        elif tag["direction"] not in TAG_DIRECTIONS:
            problems.append(f"{label}: direction {tag['direction']!r} is not one of {', '.join(TAG_DIRECTIONS)}")
        repeat = tag.get("repeat", 0)
        if type(repeat) is not int or repeat < 0:
            problems.append(f"{label}: repeat must be a whole number of 0 or more (0 repeats forever)")
    return problems


def source_box(frame):
    """(x, y, w, h) of the part of the frame's source picture that the sheet keeps, in the source picture's own coordinates: the trimmed box,
    or the whole picture when the frame was not trimmed (or when a hand-made atlas states no source size, the whole cell)."""
    if frame.get("trim"):
        return tuple(frame["trim"])
    size = frame.get("source_size") or frame["rect"][2:]
    return (0, 0, size[0], size[1])


def image_rect(frame):
    """(x, y, w, h) in the sheet of the picture the frame keeps, without the padding around it. This is the rectangle other tools should cut."""
    if not frame.get("source_size") and not frame.get("trim"):
        return tuple(frame["rect"])
    kept_x, kept_y, width, height = source_box(frame)
    offset_x, offset_y = frame.get("source_offset_in_cell", [0, 0])
    return (frame["rect"][0] + offset_x + kept_x, frame["rect"][1] + offset_y + kept_y, width, height)


def _size_text(size):
    return f"{size[0]}x{size[1]}"


def _nine_slice_problems(name, entry):
    margins, size = entry["nine_slice"], entry.get("source_size")
    if not isinstance(margins, list) or len(margins) != 4 or any(type(m) is not int or m < 0 for m in margins):
        return [f"{name}: nine_slice must be four whole numbers of 0 or more [left, top, right, bottom]"]
    problems = []
    if entry.get("trimmed"):
        problems.append(f"{name}: a nine-slice frame cannot be trimmed, because its margins are measured from the whole frame")
    if not size:
        return problems + [f"{name}: a nine-slice frame needs its source_size to check the margins"]
    left, top, right, bottom = margins
    if left + right >= size[0]:
        problems.append(f"{name}: left + right margins ({left} + {right}) leave no stretchable centre in a frame {size[0]} px wide")
    if top + bottom >= size[1]:
        problems.append(f"{name}: top + bottom margins ({top} + {bottom}) leave no stretchable centre in a frame {size[1]} px high")
    return problems


def ui_problems(atlas):
    """Every reason the UI parts of an atlas (nine-slice margins, control states, icon sets) are inconsistent; empty when there are none."""
    frames, problems = atlas["frames"], []
    for entry in frames:
        if "nine_slice" in entry:
            problems += _nine_slice_problems(entry.get("name", entry["index"]), entry)
    declared = {}
    for control in atlas.get("controls", []):
        if control["name"] in declared:
            problems.append(f"control {control['name']!r} is declared twice")
        declared[control["name"]] = control["states"]
        if "normal" not in control["states"]:
            problems.append(f"control {control['name']!r} must declare the normal state")
    members = {}
    for entry in frames:
        name, control, state = entry.get("name", entry["index"]), entry.get("control"), entry.get("state")
        if (control is None) != (state is None):
            problems.append(f"{name}: a state needs a control, and a control needs a state")
            continue
        if control is None:
            continue
        if control not in declared:
            problems.append(f"{name}: control {control!r} is not declared in the atlas controls")
            continue
        if state not in declared[control]:
            problems.append(f"{name}: state {state!r} is not declared for control {control!r}")
        members.setdefault(control, []).append(entry)
    for control, states in declared.items():
        entries = members.get(control, [])
        if not entries:
            problems.append(f"control {control!r} has no frames")
            continue
        seen = {}
        for entry in entries:
            if entry["state"] in seen:
                problems.append(f"control {control!r}: state {entry['state']!r} is used twice ({seen[entry['state']]} and {entry.get('name', entry['index'])})")
            seen.setdefault(entry["state"], entry.get("name", entry["index"]))
        problems += [f"control {control!r}: state {state!r} has no frame" for state in states if state not in seen]
        first = entries[0]
        for entry in entries[1:]:
            name = entry.get("name", entry["index"])
            if entry.get("source_size") != first.get("source_size"):
                problems.append(f"{name}: size {_size_text(entry['source_size'])} differs from {first.get('name', first['index'])} "
                                f"({_size_text(first['source_size'])}); the states of control {control!r} must share one size")
            if entry.get("nine_slice") != first.get("nine_slice"):
                problems.append(f"{name}: nine_slice {entry.get('nine_slice')} differs from {first.get('name', first['index'])} "
                                f"({first.get('nine_slice')}); the states of control {control!r} must share their margins")
    sets = {}
    for entry in frames:
        if entry.get("set") is not None:
            sets.setdefault(entry["set"], []).append(entry)
    for group, entries in sets.items():
        first = entries[0]
        for entry in entries[1:]:
            name = entry.get("name", entry["index"])
            if entry.get("source_size") != first.get("source_size"):
                problems.append(f"set {group!r}: {name} is {_size_text(entry['source_size'])} but {first.get('name', first['index'])} is "
                                f"{_size_text(first['source_size'])} (a set shares one size)")
            if entry.get("source_offset_in_cell") != first.get("source_offset_in_cell"):
                problems.append(f"set {group!r}: {name} has padding {entry.get('source_offset_in_cell')} but {first.get('name', first['index'])} has "
                                f"{first.get('source_offset_in_cell')} (a set shares one padding)")
    return problems
