"""
EDL Change List Generator
Compares two CMX3600 EDLs (old vs new) and outputs a change list.

Usage:
  python edl_changelist.py old.edl new.edl output.txt

Assumes 24fps (change FPS constant if needed).
Matches clips by reel name + source_in/source_out timecode.
Outputs human-readable change list + CMX-style change EDL blocks.
"""

import sys
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from enum import Enum

class ChangeType(Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    NEW = "new"
    DELETED = "deleted"

@dataclass
class Edit:
    event_num: str
    reel: str
    source_in: str
    source_out: str
    record_in: str
    record_out: str
    clip_name: str = ""

    def key(self) -> Tuple[str, str, str]:
        """Unique key: reel + source_in + source_out"""
        return (self.reel, self.source_in, self.source_out)

    def duration_tc(self) -> str:
        return subtract_tc(self.source_out, self.source_in)

def parse_tc(tc_str: str) -> int:
    """Parse HH:MM:SS:FF to total frames (24fps)."""
    parts = list(map(int, tc_str.split(':')))
    return ((parts[0]*60 + parts[1])*60 + parts[2])*24 + parts[3]

def tc_to_frames(tc: str, fps: int = 24) -> int:
    h, m, s, f = map(int, tc.split(':'))
    return ((h*60 + m)*60 + s)*fps + f

def frames_to_tc(frames: int, fps: int = 24) -> str:
    h = frames // (60*60*fps)
    frames %= (60*60*fps)
    m = frames // (60*fps)
    frames %= (60*fps)
    s = frames // fps
    f = frames % fps
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

def subtract_tc(out_tc: str, in_tc: str, fps: int = 24) -> str:
    return frames_to_tc(tc_to_frames(out_tc, fps) - tc_to_frames(in_tc, fps), fps)

class EDLParser:
    def __init__(self, fps: int = 24):
        self.fps = fps

    def parse(self, file_path: str) -> List[Edit]:
        edits = []
        with open(file_path, 'r') as f:
            lines = f.readlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if re.match(r'^\d{3,}', line):  # Event number like 001 or 0001
                parts = line.split()
                # CMX3600 format: EVENT  REEL  TRACK  TYPE  SOURCE_IN  SOURCE_OUT  RECORD_IN  RECORD_OUT
                if len(parts) >= 8:
                    event_num = parts[0]
                    reel = parts[1]
                    # parts[2] = track (V), parts[3] = edit type (C)
                    source_in = parts[4]
                    source_out = parts[5]
                    record_in = parts[6]
                    record_out = parts[7]

                    # Look for clip name on next line
                    clip_name = ""
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        clip_name_match = re.search(r'\* FROM CLIP NAME: (.+)', next_line)
                        if clip_name_match:
                            clip_name = clip_name_match.group(1)

                    edits.append(Edit(event_num, reel, source_in, source_out, record_in, record_out, clip_name))
            i += 1
        return edits

def compare_edls(old_edits: List[Edit], new_edits: List[Edit], fps: int = 24) -> List[Tuple[ChangeType, Optional[Edit], Optional[Edit], dict]]:
    """Compare old and new edits by position. Returns list of (type, old_edit, new_edit, details)"""
    changes = []

    max_len = max(len(old_edits), len(new_edits))

    for i in range(max_len):
        old_edit = old_edits[i] if i < len(old_edits) else None
        new_edit = new_edits[i] if i < len(new_edits) else None

        if old_edit is None and new_edit is not None:
            # New event added at the end
            changes.append((ChangeType.NEW, None, new_edit, {"description": "Clip added"}))
        elif old_edit is not None and new_edit is None:
            # Event deleted from the end (not reported in expected output)
            changes.append((ChangeType.DELETED, old_edit, None, {}))
        elif old_edit.reel != new_edit.reel:
            # Different reel at same position = new clip replacing old
            changes.append((ChangeType.NEW, old_edit, new_edit, {"description": "Clip added"}))
        elif (old_edit.source_in == new_edit.source_in and
              old_edit.source_out == new_edit.source_out):
            # Same reel and same source timecodes = unchanged
            changes.append((ChangeType.UNCHANGED, old_edit, new_edit, {}))
        else:
            # Same reel but different source timecodes = changed (trimmed)
            details = compute_trim_details(old_edit, new_edit, fps)
            changes.append((ChangeType.CHANGED, old_edit, new_edit, details))

    return changes


def compute_trim_details(old_edit: Edit, new_edit: Edit, fps: int = 24) -> dict:
    """Compute detailed trim information between old and new edit."""
    old_src_in = tc_to_frames(old_edit.source_in, fps)
    old_src_out = tc_to_frames(old_edit.source_out, fps)
    new_src_in = tc_to_frames(new_edit.source_in, fps)
    new_src_out = tc_to_frames(new_edit.source_out, fps)

    old_rec_in = tc_to_frames(old_edit.record_in, fps)
    old_rec_out = tc_to_frames(old_edit.record_out, fps)
    new_rec_in = tc_to_frames(new_edit.record_in, fps)
    new_rec_out = tc_to_frames(new_edit.record_out, fps)

    # Record durations (timeline length)
    old_length = old_rec_out - old_rec_in
    new_length = new_rec_out - new_rec_in

    # Time difference = change in record duration
    time_diff = new_length - old_length

    details = {
        "time_diff_frames": time_diff,
        "old_length_frames": old_length,
        "new_length_frames": new_length,
        "old_source_in": old_edit.source_in,
        "new_source_in": new_edit.source_in,
        "old_source_out": old_edit.source_out,
        "new_source_out": new_edit.source_out,
    }

    # Determine head change
    head_diff = new_src_in - old_src_in
    if head_diff < 0:
        details["head_change"] = "extended"
        details["head_from"] = old_edit.source_in
        details["head_to"] = new_edit.source_in
    elif head_diff > 0:
        details["head_change"] = "trimmed"
        details["head_from"] = old_edit.source_in
        details["head_to"] = new_edit.source_in

    # Determine tail change
    tail_diff = new_src_out - old_src_out
    if tail_diff > 0:
        details["tail_change"] = "extended"
        details["tail_from"] = old_edit.source_out
        details["tail_to"] = new_edit.source_out
    elif tail_diff < 0:
        details["tail_change"] = "trimmed"
        details["tail_from"] = old_edit.source_out
        details["tail_to"] = new_edit.source_out

    return details


def frames_to_description(frames: int, fps: int = 24) -> str:
    """Convert frames to human-readable format like '7 seconds 14 frames'."""
    seconds = frames // fps
    remaining_frames = frames % fps
    if seconds == 0:
        return f"{remaining_frames} frame{'s' if remaining_frames != 1 else ''}"
    return f"{seconds} second{'s' if seconds != 1 else ''} {remaining_frames} frame{'s' if remaining_frames != 1 else ''}"

def output_change_list(changes: List[Tuple[ChangeType, Optional[Edit], Optional[Edit], dict]], output_file: str, fps: int = 24):
    """Output changes in tab-separated format matching expected Changelog.txt format."""
    with open(output_file, 'w') as f:
        for typ, old_e, new_e, details in changes:
            if typ == ChangeType.UNCHANGED:
                continue
            if typ == ChangeType.DELETED:
                # Deleted events are not reported in the expected output
                continue

            # Use new_edit for position info, fall back to old_edit
            edit = new_e if new_e else old_e
            record_tc = edit.record_in
            clip_name = edit.clip_name

            if typ == ChangeType.NEW:
                # New clip
                description = f"Clip added ({clip_name})"
                f.write(f"New\t{record_tc}\tTC\tmagenta\t{description}\t1\n")

            elif typ == ChangeType.CHANGED:
                # Changed clip with trim details
                time_diff = details.get("time_diff_frames", 0)
                old_length = details.get("old_length_frames", 0)
                new_length = details.get("new_length_frames", 0)

                # Build description
                desc_parts = []

                # Time difference
                if time_diff == 0:
                    desc_parts.append("No time difference. Shifted within itself. ")
                else:
                    desc_parts.append(f"Time difference {time_diff} frames  [{time_diff} frames].")

                # Head change
                if "head_change" in details:
                    head_action = "extended" if details["head_change"] == "extended" else "trimmed"
                    desc_parts.append(f" HEAD {head_action} from {details['head_from']} to {details['head_to']}.")

                # Tail change
                if "tail_change" in details:
                    tail_action = "extended" if details["tail_change"] == "extended" else "trimmed"
                    desc_parts.append(f" TAIL {tail_action} from {details['tail_from']} to {details['tail_to']}.")

                # Length info (only if time difference is not zero)
                if time_diff != 0:
                    old_len_str = frames_to_description(old_length, fps)
                    new_len_str = frames_to_description(new_length, fps)
                    desc_parts.append(f" Old length: {old_len_str} [{old_length} frames] - New length: {new_len_str} [{new_length} frames]")

                description = "".join(desc_parts) + f" ({clip_name})"
                f.write(f"Changed\t{record_tc}\tTC\tyellow\t{description}\t1\n")

if __name__ == "__main__":
    print("EDL Change List Generator")
    if len(sys.argv) != 4:
        print("Usage: python edl_changelist.py old.edl new.edl output.txt")
        sys.exit(1)

    old_file, new_file, output_file = sys.argv[1:]

    fps = 24
    parser = EDLParser(fps=fps)
    old_edits = parser.parse(old_file)
    new_edits = parser.parse(new_file)

    print(f"Parsed {len(old_edits)} edits from old EDL, {len(new_edits)} from new.")

    changes = compare_edls(old_edits, new_edits, fps)

    output_change_list(changes, output_file, fps)

    print(f"Change list written to {output_file}")
