import time
import threading
import uuid


def handle_mqtt(args):
    try:
        import paho.mqtt.client as mqtt
        from paho.mqtt.enums import CallbackAPIVersion
    except ImportError:
        return "[ERROR] paho-mqtt not installed."

    output    = []
    messages  = []
    connected = threading.Event()
    rc_box    = [None]

    def on_connect(client, userdata, flags, reason_code, properties):
        rc_box[0] = reason_code
        connected.set()

    def on_message(client, userdata, msg):
        messages.append(msg)

    def decode(payload):
        try:
            return payload.decode("utf-8", errors="replace")
        except Exception:
            return repr(payload)

    client_id = getattr(args, "client_id", None) or f"icsspulse-{uuid.uuid4().hex[:6]}"
    client    = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2,
                            client_id=client_id)

    if getattr(args, "username", ""):
        client.username_pw_set(args.username, getattr(args, "password", "") or "")

    if getattr(args, "tls", False):
        client.tls_set()
        client.tls_insecure_set(True)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.target, int(args.port), keepalive=10)
        client.loop_start()

        if not connected.wait(timeout=int(args.timeout)):
            return f"[ERROR] Connection timed out after {args.timeout}s"

        rc_val = rc_box[0].value if hasattr(rc_box[0], "value") else int(rc_box[0])

        # ── broker_info ───────────────────────────────────────────────────────
        if args.action == "broker_info":
            if rc_val != 0:
                return f"[ERROR] Connection refused — reason code: {rc_box[0]}"
            output.append(f"[+] Connected to {args.target}:{args.port}  (client: {client_id})")
            output.append(f"[+] Collecting $SYS/# for up to {args.timeout}s ...\n")
            client.subscribe("$SYS/#", qos=0)
            time.sleep(min(int(args.timeout), 6))
            output.append(f"[SYS] Received {len(messages)} system messages:\n")
            for m in messages:
                output.append(f"  {m.topic}: {decode(m.payload)}")

        # ── check_auth ────────────────────────────────────────────────────────
        elif args.action == "check_auth":
            mode = f"user '{args.username}'" if getattr(args, "username", "") else "anonymous"
            if rc_val == 0:
                output.append(f"[SUCCESS] Connected as {mode}")
                if not getattr(args, "username", ""):
                    output.append("[CRITICAL] Broker allows anonymous access — no credentials required")
                else:
                    output.append("[INFO] Credentials accepted")
            else:
                output.append(f"[FAIL] Connection refused as {mode} — reason code: {rc_box[0]}")

        # ── enumerate ─────────────────────────────────────────────────────────
        elif args.action == "enumerate":
            if rc_val != 0:
                return f"[ERROR] Connection refused — reason code: {rc_box[0]}"
            output.append(f"[+] Subscribing to '#' for {args.timeout}s ...\n")
            client.subscribe("#", qos=0)
            time.sleep(int(args.timeout))
            seen = {}
            for m in messages:
                if m.topic not in seen:
                    seen[m.topic] = (decode(m.payload), m.retain)
            output.append(f"[+] Found {len(seen)} unique topics:\n")
            for topic, (payload, retained) in seen.items():
                tag = "[RETAINED] " if retained else ""
                output.append(f"  {tag}{topic}: {payload[:120]}")

        # ── retained_dump ─────────────────────────────────────────────────────
        elif args.action == "retained_dump":
            if rc_val != 0:
                return f"[ERROR] Connection refused — reason code: {rc_box[0]}"
            output.append(f"[+] Dumping retained messages from '#' ...\n")
            client.subscribe("#", qos=0)
            time.sleep(min(int(args.timeout), 5))
            retained = [m for m in messages if m.retain]
            output.append(f"[+] Found {len(retained)} retained message(s):\n")
            for m in retained:
                output.append(f"  {m.topic}: {decode(m.payload)}")
            if not retained:
                output.append("  None found — broker may have no retained messages.")

        # ── subscribe ─────────────────────────────────────────────────────────
        elif args.action == "subscribe":
            if rc_val != 0:
                return f"[ERROR] Connection refused — reason code: {rc_box[0]}"
            output.append(f"[+] Listening on '{args.topic}' (QoS {args.qos}) for {args.timeout}s ...\n")
            client.subscribe(args.topic, qos=int(args.qos))
            time.sleep(int(args.timeout))
            cap = int(getattr(args, "max_messages", 200))
            output.append(f"[+] Received {len(messages)} message(s):\n")
            for m in messages[:cap]:
                tag = " [RETAINED]" if m.retain else ""
                output.append(f"  QoS{m.qos}{tag} | {m.topic}: {decode(m.payload)}")
            if len(messages) > cap:
                output.append(f"  ... {len(messages) - cap} more messages (increase Max Messages to see all)")

        # ── publish ───────────────────────────────────────────────────────────
        elif args.action == "publish":
            if rc_val != 0:
                return f"[ERROR] Connection refused — reason code: {rc_box[0]}"
            retain = str(getattr(args, "retain", "false")).lower() == "true"
            result = client.publish(args.topic, args.payload,
                                    qos=int(args.qos), retain=retain)
            result.wait_for_publish(timeout=5)
            if result.is_published():
                output.append(f"[SUCCESS] Published to '{args.topic}'")
                output.append(f"  Payload : {args.payload}")
                output.append(f"  QoS     : {args.qos}")
                output.append(f"  Retain  : {retain}")
            else:
                output.append("[FAIL] Message not acknowledged by broker")

        else:
            return f"[ERROR] Unknown action: {args.action}"

    except ConnectionRefusedError:
        return f"[ERROR] Connection refused — is port {args.port} open?"
    except OSError as e:
        return f"[ERROR] Network error: {e}"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    return "\n".join(output)
