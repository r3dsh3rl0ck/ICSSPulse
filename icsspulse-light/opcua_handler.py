from opcua import Client, ua
from opcua.ua.uaerrors import UaStatusCodeError
from collections import deque
import socket
import os

ACCESS_READ  = 0x01  # CurrentRead
ACCESS_WRITE = 0x02  # CurrentWrite

# ── Performance tuning ────────────────────────────────────────────────────────
BROWSE_BATCH = 50    # nodeids per OPC UA Browse request
READ_CHUNK   = 100   # variable nodes per OPC UA Read request

_READ_ATTRS = [
    ua.AttributeIds.DataType,
    ua.AttributeIds.AccessLevel,
    ua.AttributeIds.UserAccessLevel,
    ua.AttributeIds.Value,
]
_N_ATTRS = len(_READ_ATTRS)

_DTYPE_MAP = {
    1:'Boolean',  2:'SByte',     3:'Byte',
    4:'Int16',    5:'UInt16',    6:'Int32',   7:'UInt32',
    8:'Int64',    9:'UInt64',    10:'Float',  11:'Double',
    12:'String',  13:'DateTime', 14:'Guid',   15:'ByteString',
    17:'NodeId',  21:'DataValue',
}


# ── Generic helpers ───────────────────────────────────────────────────────────

def _build_endpoint(target: str, port: int, path: str) -> str:
    path = (path or "").strip("/")
    return f"opc.tcp://{target}:{port}/" + (f"{path}/" if path else "")

def _booly(s):
    if isinstance(s, bool):
        return s
    if s is None:
        return False
    s = str(s).strip().lower()
    return s in {"1", "true", "t", "yes", "y", "on"}

def _cast_for_variant(datatype: ua.VariantType, value_str: str):
    if datatype in (ua.VariantType.Boolean,):
        return _booly(value_str)
    if datatype in (ua.VariantType.SByte, ua.VariantType.Byte,
                    ua.VariantType.Int16, ua.VariantType.UInt16,
                    ua.VariantType.Int32, ua.VariantType.UInt32,
                    ua.VariantType.Int64, ua.VariantType.UInt64):
        return int(value_str)
    if datatype in (ua.VariantType.Float, ua.VariantType.Double):
        return float(value_str)
    if datatype in (ua.VariantType.String,):
        return str(value_str)
    try:
        return int(value_str)
    except Exception:
        try:
            return float(value_str)
        except Exception:
            return str(value_str)

def _enum_name(enum_cls, value):
    try:
        return enum_cls(value).name
    except Exception:
        try:
            return getattr(value, "name")
        except Exception:
            return str(value)

def _dtype_label(dv):
    try:
        nid = dv.Value.Value
        if nid.NamespaceIndex == 0:
            return _DTYPE_MAP.get(nid.Identifier, f'i={nid.Identifier}')
        return nid.to_string()
    except Exception:
        return 'Unknown'

def _format_endpoint(ep):
    toks = []
    toks.append(f"EndpointUrl: {getattr(ep, 'EndpointUrl', 'n/a')}")
    toks.append(f"SecurityPolicyUri: {getattr(ep, 'SecurityPolicyUri', 'n/a')}")
    mode = _enum_name(ua.MessageSecurityMode, getattr(ep, 'SecurityMode', None))
    toks.append(f"SecurityMode: {mode}")
    toks.append("UserIdentityTokens:")
    for t in getattr(ep, 'UserIdentityTokens', []) or []:
        try:
            tok = _enum_name(ua.UserTokenType, t.TokenType)
        except Exception:
            tok = str(getattr(t, 'TokenType', 'Unknown'))
        issued = getattr(t, 'IssuedTokenType', None) or 'n/a'
        toks.append(f"  - {tok} ({issued})")
    return "\n".join(toks)

def _safe_set_timeout(client: Client, timeout_s: int):
    try:
        client.session_timeout = max(10000, timeout_s * 1000)
    except Exception:
        pass
    try:
        client.set_timeout(timeout_s * 1000)
    except Exception:
        pass
    try:
        socket.setdefaulttimeout(timeout_s)
    except Exception:
        pass


# ── Bulk OPC UA operations ────────────────────────────────────────────────────

def _bulk_browse(client, nodeids):
    """
    Single OPC UA Browse request for a list of nodeids.
    BrowseResultMask.All gives NodeClass + BrowseName + DisplayName for FREE.
    Returns list[BrowseResult], one entry per nodeid.
    """
    params = ua.BrowseParameters()
    params.RequestedMaxReferencesPerNode = 0
    params.NodesToBrowse = []
    for nid in nodeids:
        bd = ua.BrowseDescription()
        bd.NodeId          = nid
        bd.BrowseDirection = ua.BrowseDirection.Forward
        bd.ReferenceTypeId = ua.NodeId(ua.ObjectIds.HierarchicalReferences)
        bd.IncludeSubtypes = True
        bd.NodeClassMask   = 0
        bd.ResultMask      = ua.BrowseResultMask.All
        params.NodesToBrowse.append(bd)
    return client.uaclient.browse(params)

def _bulk_read_flat(client, nodeids, attr_ids):
    """
    Single OPC UA Read request for every (nodeid × attr_id) combination.
    Returns flat list: [node0·attr0, node0·attr1, …, nodeN·attrM]
    Index with: flat[i * len(attr_ids) + j]
    """
    params = ua.ReadParameters()
    params.MaxAge = 0
    params.TimestampsToReturn = ua.TimestampsToReturn.Neither
    params.NodesToRead = []
    for nid in nodeids:
        for aid in attr_ids:
            rv = ua.ReadValueId()
            rv.NodeId      = nid
            rv.AttributeId = aid
            params.NodesToRead.append(rv)
    return client.uaclient.read(params)


# ── Optimised Browse (tree) ───────────────────────────────────────────────────

def _browse_tree(client, args):
    max_depth = int(getattr(args, 'max_depth', 3))
    max_nodes = int(getattr(args, 'max_nodes', 200))

    root     = client.get_objects_node()
    root_nid = root.nodeid
    root_s   = root_nid.to_string()

    # BFS state
    queue   = deque([(root_nid, 0)])
    visited = {root_s}
    budget  = [max_nodes]

    # Tree structure: nid_s → ordered list of child tuples
    # (child_nid_s, nclass_s, bname_s, dname)
    children: dict = {root_s: []}

    while queue and budget[0] > 0:
        batch = []
        while queue and len(batch) < BROWSE_BATCH:
            batch.append(queue.popleft())   # (nid, depth)

        if not batch:
            break

        # ── Bulk browse this batch ────────────────────────────────────────
        try:
            results = _bulk_browse(client, [b[0] for b in batch])
        except Exception:
            # Fallback: sequential get_children() for this batch
            for nid, depth in batch:
                try:
                    parent_s = nid.to_string()
                    if parent_s not in children:
                        children[parent_s] = []
                    for ch in client.get_node(nid).get_children():
                        ch_s = ch.nodeid.to_string()
                        if ch_s not in visited and budget[0] > 0:
                            visited.add(ch_s)
                            budget[0] -= 1
                            children[parent_s].append((ch_s, 'Unknown', '?:?', ''))
                            children.setdefault(ch_s, [])
                            if depth + 1 < max_depth:
                                queue.append((ch.nodeid, depth + 1))
                except Exception:
                    pass
            continue

        for (parent_nid, parent_depth), browse_res in zip(batch, results):
            parent_s = parent_nid.to_string()
            if parent_s not in children:
                children[parent_s] = []

            for ref in (browse_res.References or []):
                child_nid   = ref.NodeId
                child_nid_s = child_nid.to_string()

                if child_nid_s in visited or budget[0] <= 0:
                    continue
                visited.add(child_nid_s)
                budget[0] -= 1

                # FREE from BrowseResultMask.All
                try:
                    bname_s = f"{ref.BrowseName.NamespaceIndex}:{ref.BrowseName.Name}"
                except Exception:
                    bname_s = "?:?"
                try:
                    dname = ref.DisplayName.Text or ""
                except Exception:
                    dname = ""

                node_class = getattr(ref, 'NodeClass', ua.NodeClass.Unspecified)
                nclass_s   = _enum_name(ua.NodeClass, node_class)

                children[parent_s].append((child_nid_s, nclass_s, bname_s, dname))
                children.setdefault(child_nid_s, [])

                if parent_depth + 1 < max_depth:
                    queue.append((child_nid, parent_depth + 1))

    # ── Phase 2: DFS output with ASCII tree characters ────────────────────────
    # ├── last-but-one child
    # └── last child
    # │   continuation for non-last ancestors
    lines = [f"Objects: {root_s}\n"]

    def _dfs_output(nid_s: str, prefix: str = ""):
        kids = children.get(nid_s, [])
        for i, (ch_s, nclass_s, bname_s, dname) in enumerate(kids):
            is_last   = (i == len(kids) - 1)
            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "
            lines.append(
                f"{prefix}{connector}[{nclass_s}] {ch_s}"
                f"  BrowseName={bname_s}  DisplayName={dname}"
            )
            _dfs_output(ch_s, prefix + extension)

    _dfs_output(root_s)

    if budget[0] <= 0:
        lines.append("\n[!] Node budget exhausted — increase Max Nodes to see more.")

    return lines


# ── Optimised Enumerate (all / read_only / write_only) ───────────────────────

def _enumerate_variables(client, args, access_filter=None):
    """
    Two-phase enumeration (see previous optimisation for full details).
    access_filter: None = all | 'r' = readable only | 'w' = writable only
    """
    ns_filter = getattr(args, 'namespace', None)
    try:
        ns_filter = int(ns_filter) if ns_filter not in (None, '') else None
    except Exception:
        ns_filter = None

    max_depth = int(getattr(args, 'max_depth', 4))
    max_nodes = int(getattr(args, 'max_nodes', 400))

    # Phase 1: batched BFS browse
    root_nid = client.get_objects_node().nodeid
    queue    = deque([(root_nid, 0)])
    visited  = {root_nid.to_string()}
    var_nodes = []  # (NodeId, bname_s, dname)

    while queue and len(var_nodes) < max_nodes:
        batch = []
        while queue and len(batch) < BROWSE_BATCH:
            batch.append(queue.popleft())
        if not batch:
            break

        try:
            results = _bulk_browse(client, [b[0] for b in batch])
        except Exception:
            for nid, depth in batch:
                try:
                    for ch in client.get_node(nid).get_children():
                        ch_s = ch.nodeid.to_string()
                        if ch_s not in visited and depth + 1 <= max_depth:
                            visited.add(ch_s)
                            queue.append((ch.nodeid, depth + 1))
                except Exception:
                    pass
            continue

        for (parent_nid, parent_depth), browse_res in zip(batch, results):
            for ref in (browse_res.References or []):
                child_nid   = ref.NodeId
                child_nid_s = child_nid.to_string()
                if child_nid_s in visited:
                    continue
                visited.add(child_nid_s)

                try:
                    bname_s = f"{ref.BrowseName.NamespaceIndex}:{ref.BrowseName.Name}"
                except Exception:
                    bname_s = "?:?"
                try:
                    dname = ref.DisplayName.Text or ""
                except Exception:
                    dname = ""

                node_class = getattr(ref, 'NodeClass', ua.NodeClass.Unspecified)

                if node_class == ua.NodeClass.Variable:
                    if ns_filter is None or child_nid.NamespaceIndex == ns_filter:
                        var_nodes.append((child_nid, bname_s, dname))
                        if len(var_nodes) >= max_nodes:
                            break
                if node_class != ua.NodeClass.Variable and parent_depth + 1 <= max_depth:
                    queue.append((child_nid, parent_depth + 1))

    if not var_nodes:
        return []

    # Phase 2: chunked bulk read
    lines = []
    for chunk_start in range(0, len(var_nodes), READ_CHUNK):
        chunk      = var_nodes[chunk_start : chunk_start + READ_CHUNK]
        chunk_nids = [n[0] for n in chunk]

        try:
            flat = _bulk_read_flat(client, chunk_nids, _READ_ATTRS)
        except Exception:
            flat = None

        for i, (nid, bname_s, dname) in enumerate(chunk):
            if flat is not None:
                base   = i * _N_ATTRS
                dv_dt  = flat[base + 0]
                dv_al  = flat[base + 1]
                dv_ual = flat[base + 2]
                dv_val = flat[base + 3]
                try:
                    al      = int(dv_al.Value.Value  or 0)
                    user_al = int(dv_ual.Value.Value or 0)
                except Exception:
                    al = user_al = 0
                if access_filter == 'r' and not (al & ACCESS_READ):
                    continue
                if access_filter == 'w' and not (al & ACCESS_WRITE):
                    continue
                dtype_s = _dtype_label(dv_dt)
                try:
                    val = dv_val.Value.Value
                    if val is None:
                        sc = getattr(dv_val, 'StatusCode', None)
                        if sc and sc.value != 0:
                            val = f"<status: {sc}>"
                except Exception as e:
                    val = f"<error: {e}>"
            else:
                try:
                    node    = client.get_node(nid)
                    al      = node.get_attribute(ua.AttributeIds.AccessLevel).Value.Value
                    user_al = node.get_attribute(ua.AttributeIds.UserAccessLevel).Value.Value
                    if access_filter == 'r' and not (al & ACCESS_READ):
                        continue
                    if access_filter == 'w' and not (al & ACCESS_WRITE):
                        continue
                    dtype_s = _enum_name(ua.VariantType, node.get_data_type_as_variant_type())
                    val     = node.get_value()
                except Exception as e:
                    lines.append(f"{nid.to_string()}  <fallback error: {e}>")
                    continue

            access_str = "/".join(filter(None, [
                "R" if (al & ACCESS_READ)  else "",
                "W" if (al & ACCESS_WRITE) else "",
            ])) or "none"
            lines.append(
                f"{nid.to_string()}  BrowseName={bname_s}  DisplayName={dname}  "
                f"DataType={dtype_s}  Access={access_str}({al})  UserAccess={user_al}  Value={val}"
            )

    return lines


# ── Security setup ────────────────────────────────────────────────────────────

def _setup_security(client: Client, args):
    cert_path     = getattr(args, 'cert_path', None)
    key_path      = getattr(args, 'key_path', None)
    security_mode = int(getattr(args, 'security_mode', 0) or 0)
    if not cert_path or not key_path or security_mode not in (2, 3):
        return
    mode_str = "SignAndEncrypt" if security_mode == 3 else "Sign"
    client.set_security_string(f"Basic256Sha256,{mode_str},{cert_path},{key_path}")
    app_uri = getattr(args, 'app_uri', None) or "urn:ctf:python-opcua-client"
    client.application_uri = app_uri


# ── Main handler ──────────────────────────────────────────────────────────────

def handle_opcua(args):
    output  = ''
    success = False

    endpoint = _build_endpoint(
        args.target,
        int(getattr(args, 'port', 4840)),
        getattr(args, 'endpoint_path', 'freeopcua/server/')
    )
    timeout  = int(getattr(args, 'timeout', 3))
    retries  = int(getattr(args, 'retries', 3))
    username = getattr(args, 'username', '') or None
    password = getattr(args, 'password', '') or None

    for attempt in range(1, retries + 1):
        try:
            # ── DISCOVER ──────────────────────────────────────────────────
            if args.action == 'discover':
                c = Client(endpoint)
                _safe_set_timeout(c, timeout)
                endpoints = c.connect_and_get_server_endpoints()
                try:
                    c.disconnect()
                except Exception:
                    pass
                if not endpoints:
                    output += "No endpoints returned by server.\n"
                else:
                    output += f"Discovered {len(endpoints)} endpoint(s):\n"
                    for idx, ep in enumerate(endpoints, 1):
                        output += f"\n--- Endpoint {idx} ---\n{_format_endpoint(ep)}\n"
                success = True
                break

            client = Client(endpoint)
            _safe_set_timeout(client, timeout)

            try:
                _setup_security(client, args)
            except Exception as e:
                output += f"[Security setup warning] {e}\n"

            if username:
                client.set_user(username)
                client.set_password(password or "")
            else:
                client.set_user("")

            client.connect()

            try:
                ns_array = client.get_node(ua.ObjectIds.Server_NamespaceArray).get_value()
            except Exception:
                ns_array = []
            if ns_array:
                output += "NamespaceArray:\n"
                for i, uri in enumerate(ns_array):
                    output += f"  ns[{i}] = {uri}\n"
                output += "\n"

            # ── BROWSE (tree) ─────────────────────────────────────────────
            if args.action == 'browse':
                lines   = _browse_tree(client, args)
                output += "\n".join(lines) + "\n"
                success = True

            # ── ENUMERATE ALL ─────────────────────────────────────────────
            elif args.action == 'enumerate':
                lines   = _enumerate_variables(client, args, access_filter=None)
                output += ("\n".join(lines) + "\n") if lines else "No variables found.\n"
                success = True

            # ── READABLE ONLY ─────────────────────────────────────────────
            elif args.action == 'read_only':
                output += "=== Readable Variables (AccessLevel & CurrentRead) ===\n\n"
                lines   = _enumerate_variables(client, args, access_filter='r')
                output += ("\n".join(lines) + "\n") if lines else "No readable variables found.\n"
                success = True

            # ── WRITABLE ONLY ─────────────────────────────────────────────
            elif args.action == 'write_only':
                output += "=== Writable Variables (AccessLevel & CurrentWrite) ===\n\n"
                lines   = _enumerate_variables(client, args, access_filter='w')
                output += ("\n".join(lines) + "\n") if lines else "No writable variables found.\n"
                success = True

            # ── READ single node ──────────────────────────────────────────
            elif args.action == 'read':
                nodeid = getattr(args, 'nodeid', None)
                if not nodeid:
                    output += "Error: 'read' requires a NodeId (e.g., ns=2;i=10).\n"
                else:
                    node  = client.get_node(str(nodeid))
                    val   = node.get_value()
                    output += f"Read {nodeid}: {val}\n"
                    success = True

            # ── WRITE single node ─────────────────────────────────────────
            elif args.action == 'write':
                nodeid = getattr(args, 'nodeid', None)
                if not nodeid:
                    output += "Error: 'write' requires a NodeId and value.\n"
                else:
                    node    = client.get_node(str(nodeid))
                    vtype   = node.get_data_type_as_variant_type()
                    py_val  = _cast_for_variant(vtype, getattr(args, 'value', ''))
                    node.set_value(ua.Variant(py_val, vtype))
                    new_val = node.get_value()
                    output += f"Write OK. {nodeid} <= {py_val}  (now: {new_val})\n"
                    success = True

            else:
                output += f"Unsupported action: {args.action}\n"

            try:
                client.disconnect()
            except Exception:
                pass

            if success:
                break

        except (UaStatusCodeError, ConnectionError, OSError, socket.timeout, Exception) as e:
            output += f"Attempt {attempt} failed: {e}\n"

    if not success:
        output += "All retries failed.\n"
    elif not output:
        output = "Operation completed with no output."

    return output
