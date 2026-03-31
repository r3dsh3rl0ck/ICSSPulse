try:
    import snap7
    from snap7.type import Block
    SNAP7_AVAILABLE = True
except ImportError:
    SNAP7_AVAILABLE = False

import struct
import socket


# ── Helpers ───────────────────────────────────────────────────────────────────

def _booly(s):
    if isinstance(s, bool):
        return s
    return str(s).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _clean(b):
    """Decode a ctypes bytes field to a readable string."""
    try:
        return b.decode("utf-8").rstrip("\x00").strip()
    except Exception:
        return repr(b)


def _hexdump(data, width=16):
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hex_s = " ".join(f"{b:02X}" for b in chunk)
        asc_s = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"0x{i:04X}  {hex_s:<{width * 3}}  {asc_s}")
    return "\n".join(lines)


# Data type → byte size
_DTYPE_SIZE = {
    "BOOL": 1, "BYTE": 1, "WORD": 2, "INT": 2,
    "DWORD": 4, "DINT": 4, "REAL": 4,
}

_PROTECTION = {
    0: "No protection (full access)",
    1: "Level 1  – Read protected",
    2: "Level 2  – Write protected",
    3: "Level 3  – Full protection",
}

# Common SZL IDs and what they contain
_SZL_NAMES = {
    0x0011: "Module / Order code",
    0x001C: "Component identification (plant name, location)",
    0x0131: "Communication parameters / PDU size",
    0x0174: "Protection level configuration",
    0x0232: "Diagnostic buffer (recent events)",
}


def _pack(data_type: str, value_str: str) -> bytearray:
    """Pack a value string into S7 big-endian bytes."""
    dt = data_type.upper()
    if dt == "BOOL":
        return bytearray([1 if _booly(value_str) else 0])
    elif dt == "BYTE":
        return bytearray([int(value_str, 0) & 0xFF])
    elif dt == "WORD":
        return bytearray(struct.pack(">H", int(value_str, 0)))
    elif dt == "INT":
        return bytearray(struct.pack(">h", int(value_str)))
    elif dt == "DWORD":
        return bytearray(struct.pack(">I", int(value_str, 0)))
    elif dt == "DINT":
        return bytearray(struct.pack(">i", int(value_str)))
    elif dt == "REAL":
        return bytearray(struct.pack(">f", float(value_str)))
    else:
        # RAW — expect hex string like "00 FF A1" or "00FFA1"
        return bytearray.fromhex(value_str.replace(" ", ""))


def _parse(data: bytearray, data_type: str) -> str | None:
    """Interpret bytes as a typed S7 value. Returns None → caller does hex dump."""
    dt = data_type.upper()
    if dt == "BOOL":
        return f"{bool(data[0] & 0x01)}  (raw byte: 0x{data[0]:02X})"
    elif dt == "BYTE":
        return f"{data[0]}  (0x{data[0]:02X})"
    elif dt == "WORD":
        v = struct.unpack(">H", bytes(data[:2]))[0]
        return f"{v}  (0x{v:04X})"
    elif dt == "INT":
        return str(struct.unpack(">h", bytes(data[:2]))[0])
    elif dt == "DWORD":
        v = struct.unpack(">I", bytes(data[:4]))[0]
        return f"{v}  (0x{v:08X})"
    elif dt == "DINT":
        return str(struct.unpack(">i", bytes(data[:4]))[0])
    elif dt == "REAL":
        return f"{struct.unpack('>f', bytes(data[:4]))[0]:.6f}"
    elif dt == "STRING":
        actual = min(data[1], len(data) - 2) if len(data) >= 2 else 0
        return data[2:2 + actual].decode("ascii", errors="replace")
    return None  # RAW → hex dump


# ── Main handler ──────────────────────────────────────────────────────────────

def handle_s7comm(args):
    """
    args fields:
        action     : plc_info | list_blocks | db_list | db_read | db_write
                     area_read | area_write | szl_read
        target     : PLC IP
        port       : TCP port (default 102)
        rack       : rack number (default 0)
        slot       : CPU slot  (default 1)
        timeout    : seconds   (default 5)
        retries    : attempts  (default 2)
        db_number  : int – for db_read / db_write
        start      : byte offset  (default 0)
        size       : bytes to read (default 64)
        data_type  : BOOL/BYTE/WORD/INT/DWORD/DINT/REAL/STRING/RAW
        value      : write value string
        area       : I/Q/M/T/C – for area_read / area_write
        max_dbs    : cap for db_list (default 100)
        szl_id     : hex string e.g. "0x0011" – blank = list known IDs
    """
    if not SNAP7_AVAILABLE:
        return "[Error] python-snap7 is not installed.\nRun: pip install python-snap7"

    output  = ""
    success = False
    port    = int(getattr(args, "port", 102))
    rack    = int(getattr(args, "rack", 0))
    slot    = int(getattr(args, "slot", 1))
    retries = int(getattr(args, "retries", 2))

    for attempt in range(1, retries + 1):
        client = snap7.client.Client()
        try:
            socket.setdefaulttimeout(int(getattr(args, "timeout", 5)))
            client.connect(args.target, rack, slot, tcp_port=port)

            # ── PLC INFO ──────────────────────────────────────────────────
            if args.action == "plc_info":
                try:
                    info = client.get_cpu_info()
                    output += "── CPU Info ──────────────────────────────\n"
                    output += f"Module Type  : {_clean(info.ModuleTypeName)}\n"
                    output += f"Module Name  : {_clean(info.ModuleName)}\n"
                    output += f"Serial Number: {_clean(info.SerialNumber)}\n"
                    output += f"AS Name      : {_clean(info.ASName)}\n"
                    output += f"Copyright    : {_clean(info.Copyright)}\n"
                except Exception as e:
                    output += f"[cpu_info error] {e}\n"

                try:
                    order = client.get_order_code()
                    output += f"\n── Order Code ────────────────────────────\n"
                    output += f"Order Code   : {_clean(order.OrderCode)}\n"
                    output += f"Firmware     : V{order.V1}.{order.V2}.{order.V3}\n"
                except Exception as e:
                    output += f"[order_code error] {e}\n"

                try:
                    state  = client.get_cpu_state()
                    output += f"\n── CPU State ─────────────────────────────\n"
                    output += f"State        : {state}\n"
                except Exception as e:
                    output += f"[cpu_state error] {e}\n"

                try:
                    prot   = client.get_protection()
                    level  = getattr(prot, "sch_schal", "?")
                    output += f"\n── Protection ────────────────────────────\n"
                    output += f"Level        : {level} — {_PROTECTION.get(level, str(level))}\n"
                    output += f"sch_par      : {getattr(prot, 'sch_par', '?')}\n"
                    output += f"sch_rel      : {getattr(prot, 'sch_rel', '?')}\n"
                    if level == 0:
                        output += "\n[!] Protection Level 0 — unauthenticated read/write access.\n"
                except Exception as e:
                    output += f"[protection error] {e}\n"

                success = True

            # ── LIST BLOCKS ───────────────────────────────────────────────
            elif args.action == "list_blocks":
                bl = client.list_blocks()
                output += "Block Type   Count\n"
                output += "─────────────────\n"
                for label, attr in [
                    ("OB  (Org. Blocks)", "OBCount"),
                    ("FB  (Func. Blocks)", "FBCount"),
                    ("FC  (Functions)",   "FCCount"),
                    ("DB  (Data Blocks)", "DBCount"),
                    ("SDB (Sys. DBs)",    "SDBCount"),
                    ("SFB (Sys. FBs)",    "SFBCount"),
                    ("SFC (Sys. FCs)",    "SFCCount"),
                ]:
                    count = getattr(bl, attr, "?")
                    output += f"{label:<22} {count}\n"
                success = True

            # ── DB LIST ───────────────────────────────────────────────────
            elif args.action == "db_list":
                max_dbs = int(getattr(args, "max_dbs", 100))
                raw     = client.list_blocks_of_type(Block.DB, max_dbs)
                dbs     = [int(n) for n in raw if int(n) > 0] if raw else []
                if not dbs:
                    output += "No Data Blocks found.\n"
                else:
                    output += f"Found {len(dbs)} DB(s) (max scanned: {max_dbs}):\n\n"
                    output += "DB Number   Size (bytes)\n"
                    output += "────────────────────────\n"
                    for db_num in sorted(dbs):
                        try:
                            info = client.get_ag_block_info(Block.DB, db_num)
                            size = getattr(info, "MC7Size", "?")
                        except Exception:
                            size = "?"
                        output += f"DB{db_num:<8}  {size}\n"
                success = True

            # ── DB READ ───────────────────────────────────────────────────
            elif args.action == "db_read":
                db_num    = int(getattr(args, "db_number", 1))
                start     = int(getattr(args, "start", 0))
                size      = int(getattr(args, "size", 64))
                data_type = getattr(args, "data_type", "RAW").upper()

                # Clamp read size to data_type minimum if needed
                min_size = _DTYPE_SIZE.get(data_type, size)
                if size < min_size:
                    size = min_size

                data = client.db_read(db_num, start, size)
                output += f"DB{db_num}  offset={start}  size={size}  type={data_type}\n"
                output += "─" * 56 + "\n"

                parsed = _parse(data, data_type)
                if parsed is not None:
                    output += f"Value: {parsed}\n\n"

                output += "Hex dump:\n"
                output += _hexdump(data) + "\n"
                success = True

            # ── DB WRITE ─────────────────────────────────────────────────
            elif args.action == "db_write":
                db_num    = int(getattr(args, "db_number", 1))
                start     = int(getattr(args, "start", 0))
                data_type = getattr(args, "data_type", "RAW").upper()
                value_str = getattr(args, "value", "")

                packed = _pack(data_type, value_str)
                client.db_write(db_num, start, packed)

                # Read back to confirm
                read_back = client.db_read(db_num, start, len(packed))
                parsed    = _parse(read_back, data_type) or _hexdump(read_back)
                output   += f"Write OK — DB{db_num}.DB{_dtype_suffix(data_type)}{start} <= {value_str}\n"
                output   += f"Read-back : {parsed}\n"
                success   = True

            # ── AREA READ ────────────────────────────────────────────────
            elif args.action == "area_read":
                area      = getattr(args, "area", "M").upper()
                start     = int(getattr(args, "start", 0))
                size      = int(getattr(args, "size", 16))
                data_type = getattr(args, "data_type", "RAW").upper()

                _area_read = {
                    "I": client.eb_read,
                    "Q": client.ab_read,
                    "M": client.mb_read,
                    "T": client.tm_read,
                    "C": client.ct_read,
                }
                fn = _area_read.get(area)
                if fn is None:
                    output += f"Unknown area '{area}'. Use I / Q / M / T / C.\n"
                else:
                    data   = fn(start, size)
                    output += f"Area={area}  offset={start}  size={size}  type={data_type}\n"
                    output += "─" * 48 + "\n"
                    parsed = _parse(data, data_type)
                    if parsed is not None:
                        output += f"Value: {parsed}\n\n"
                    output += "Hex dump:\n"
                    output += _hexdump(data) + "\n"
                    success = True

            # ── AREA WRITE ───────────────────────────────────────────────
            elif args.action == "area_write":
                area      = getattr(args, "area", "M").upper()
                start     = int(getattr(args, "start", 0))
                data_type = getattr(args, "data_type", "RAW").upper()
                value_str = getattr(args, "value", "")

                _area_write = {
                    "I": client.eb_write,
                    "Q": client.ab_write,
                    "M": client.mb_write,
                }
                fn = _area_write.get(area)
                if fn is None:
                    output += f"Area '{area}' is read-only or not supported for write. Use I / Q / M.\n"
                else:
                    packed = _pack(data_type, value_str)
                    fn(start, packed)
                    output += f"Write OK — {area}{start} ({data_type}) <= {value_str}\n"
                    success = True

            # ── SZL READ ─────────────────────────────────────────────────
            elif args.action == "szl_read":
                szl_id_str = getattr(args, "szl_id", "").strip()

                if not szl_id_str:
                    # Show known IDs as a guide
                    output += "Common SZL IDs (provide one in the SZL ID field to read):\n\n"
                    output += f"{'SZL ID':<10}  Description\n"
                    output += "─" * 50 + "\n"
                    for id_int, desc in _SZL_NAMES.items():
                        output += f"0x{id_int:04X}    {desc}\n"
                    try:
                        szl_list = client.read_szl_list()
                        ids = [int(szl_list.List[i]) for i in range(szl_list.Header.NDR)
                               if int(szl_list.List[i]) > 0]
                        if ids:
                            output += f"\nAll available SZL IDs on this PLC ({len(ids)} total):\n"
                            output += "  " + "  ".join(f"0x{i:04X}" for i in sorted(ids)) + "\n"
                    except Exception:
                        pass  # Not all PLCs support read_szl_list
                    success = True
                else:
                    szl_id = int(szl_id_str, 16) if szl_id_str.startswith("0x") else int(szl_id_str, 0)
                    szl    = client.read_szl(szl_id, 0)
                    name   = _SZL_NAMES.get(szl_id, "")
                    output += f"SZL 0x{szl_id:04X}"
                    if name:
                        output += f"  ({name})"
                    output += "\n" + "─" * 56 + "\n"
                    try:
                        raw = bytes(szl.Data)
                        output += f"Data ({len(raw)} bytes):\n"
                        output += _hexdump(raw) + "\n"
                        try:
                            decoded = raw.decode("ascii", errors="replace").replace("\x00", " ")
                            output += f"\nASCII view: {decoded}\n"
                        except Exception:
                            pass
                    except Exception as e:
                        output += f"[SZL data error] {e}\n"
                    success = True

            else:
                output += f"Unknown action: {args.action}\n"

        except Exception as e:
            output += f"Attempt {attempt} failed: {e}\n"
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

        if success:
            break

    if not success:
        output += "All retries failed.\n"
    elif not output:
        output = "Operation completed with no output."

    return output


def _dtype_suffix(dt: str) -> str:
    """Return S7 address suffix for a data type (for display only)."""
    return {"BOOL": "X", "BYTE": "B", "WORD": "W", "INT": "W",
            "DWORD": "D", "DINT": "D", "REAL": "D"}.get(dt.upper(), "B")
