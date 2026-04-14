import re


def handle_ethernetip(args):
    try:
        from pycomm3 import LogixDriver, CIPDriver
    except ImportError:
        return "[ERROR] pycomm3 not installed"

    output = []

    def _coerce_value(raw):
        if isinstance(raw, str):
            s = raw.strip()
            low = s.lower()
            if low in ("true", "false"):
                return low == "true"
            if re.fullmatch(r"-?\d+", s):
                return int(s)
            if re.fullmatch(r"-?\d+\.\d+", s):
                return float(s)
        return raw

    # ── discover (broadcast — returns a list) ─────────────────────────────────
    if args.action == "discover":
        try:
            output.append(f"[+] Sending ListIdentity broadcast ...\n")
            devices = CIPDriver.discover()
            if not devices:
                output.append("  No EtherNet/IP devices responded.")
            else:
                output.append(f"[+] Found {len(devices)} device(s):\n")
                for d in devices:
                    output.append(f"  IP           : {d.get('ip_address', 'N/A')}")
                    output.append(f"  Product Name : {d.get('product_name', 'N/A')}")
                    output.append(f"  Vendor       : {d.get('vendor', 'N/A')}")
                    output.append(f"  Serial       : {d.get('serial', 'N/A')}")
                    output.append(f"  Revision     : {d.get('revision', 'N/A')}")
                    output.append(f"  Device Type  : {d.get('product_type', d.get('device_type', 'N/A'))}")
                    output.append("")
        except Exception as e:
            return f"[ERROR] Discovery failed: {type(e).__name__}: {e}"
        return "\n".join(output)

    # ── all Logix actions — shared path ───────────────────────────────────────
    slot = getattr(args, "slot", "0") or "0"
    path = f"{args.target}/{slot}"

    # device_info only needs plc.info — tag upload not required
    # list_tags / read_tag / write_tag need init_tags=True because pycomm3
    # requires uploaded type definitions to format read/write requests
    init_tags = args.action in {"list_tags", "read_tag", "write_tag"}

    try:
        with LogixDriver(path, init_tags=init_tags, init_program_tags=False) as plc:

            # ── device_info ───────────────────────────────────────────────────
            if args.action == "device_info":
                info = plc.info
                output.append(f"[+] Connected to {args.target} (slot {slot})\n")
                for key, val in info.items():
                    output.append(f"  {str(key):<22}: {val}")

            # ── list_tags ─────────────────────────────────────────────────────
            elif args.action == "list_tags":
                output.append(f"[+] Enumerating tags on {args.target} ...\n")
                tags = plc.get_tag_list()
                cap = int(getattr(args, "max_tags", 200))
                output.append(f"[+] Found {len(tags)} tag(s):\n")
                for tag in tags[:cap]:
                    name = (
                        tag.get("tag_name")
                        or tag.get("name")
                        or "?"
                    )
                    dtype = (
                        tag.get("data_type_name")
                        or tag.get("data_type")
                        or tag.get("type")
                        or "?"
                    )
                    output.append(f"  {str(name):<45} {dtype}")
                if len(tags) > cap:
                    output.append(f"\n  ... {len(tags) - cap} more (increase Max Tags to see all)")

            # ── read_tag ──────────────────────────────────────────────────────
            elif args.action == "read_tag":
                if not getattr(args, "tag_name", None):
                    return "[ERROR] tag_name is required for read_tag"
                names = [t.strip() for t in args.tag_name.split(",") if t.strip()]
                results = plc.read(*names)
                if not isinstance(results, list):
                    results = [results]
                output.append(f"[+] Read {len(results)} tag(s):\n")
                for r in results:
                    if r.error:
                        output.append(f"  [FAIL] {r.tag}: {r.error}")
                    else:
                        output.append(f"  {str(r.tag):<45} = {r.value}  ({r.type})")

            # ── write_tag ─────────────────────────────────────────────────────
            elif args.action == "write_tag":
                if not getattr(args, "tag_name", None):
                    return "[ERROR] tag_name is required for write_tag"
                if not hasattr(args, "value"):
                    return "[ERROR] value is required for write_tag"
                val = _coerce_value(args.value)
                result = plc.write((args.tag_name, val))
                if not isinstance(result, list):
                    result = [result]
                output.append("[+] Write result:\n")
                for r in result:
                    if r.error:
                        output.append(f"  [FAIL] {r.tag}: {r.error}")
                    else:
                        output.append(f"  [SUCCESS] {r.tag} = {r.value}")

            else:
                return f"[ERROR] Unknown action: {args.action}"

    except Exception as e:
        hint = ""
        if args.action in {"list_tags", "read_tag", "write_tag"}:
            hint = (
                "\n[HINT] list_tags/read_tag/write_tag require a real or well-emulated "
                "Logix controller. Generic EtherNet/IP simulators will not satisfy "
                "pycomm3's tag-upload initialization."
            )
        return f"[ERROR] {type(e).__name__}: {e}{hint}"

    return "\n".join(output)