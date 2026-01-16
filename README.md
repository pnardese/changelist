# EDL Change List Generator

A Python tool that compares two CMX3600 EDL (Edit Decision List) files and outputs a human-readable change list for video editing workflows.

## Features

- Compares old and new EDL files to detect changes
- Identifies new clips, deleted clips, and modified (trimmed) clips
- Reports head/tail trim details with frame-accurate timecodes
- Outputs tab-separated format suitable for import into other tools

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd changelist

# No external dependencies required - uses Python standard library only
```

## Usage

```bash
python changelist.py <old.edl> <new.edl> <output.txt>
```

### Example

```bash
python changelist.py test/Demo_edit_v1.edl test/Demo_edit_v2.edl output.txt
```

### Output Format

The tool outputs a tab-separated file with the following columns:

```
Type    RecordTC    Format    Color    Description    Flag
```

- **Type**: `New` or `Changed`
- **RecordTC**: Timeline position (record timecode)
- **Description**: Details about the change including clip name and trim information

## EDL Format Support

The tool parses CMX3600 format EDLs with the following structure:

```
TITLE: Project_Name.edl
FCM: NON-DROP FRAME

000001  REEL_NAME  V     C        SOURCE_IN SOURCE_OUT RECORD_IN RECORD_OUT
* FROM CLIP NAME: ClipName.mov
```

### Configuration

- Default frame rate: 24 fps (configurable in code via `EDLParser(fps=)`)
- Timecode format: Non-drop frame (HH:MM:SS:FF)

## How It Works

1. **Parsing**: Reads both EDL files and extracts edit events
2. **Matching**: Compares clips by position, using reel name and source timecodes as identifiers
3. **Change Detection**:
   - **Unchanged**: Same reel and source timecodes at same position
   - **Changed**: Same reel but different source timecodes (head/tail trims)
   - **New**: Different reel at same position or new events added
4. **Output**: Generates a change report with frame-accurate trim details

## Architecture

Single-file Python application with these components:

- `Edit` dataclass: Represents a single EDL event
- `EDLParser`: Parses CMX3600 format EDLs
- `compare_edls()`: Diff algorithm for change detection
- `output_change_list()`: Writes the change report

## License

MIT License
