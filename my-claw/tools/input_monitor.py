"""Input Monitor — reads Scarlett input levels from scsynth via SendReply.

Uses a single UDP socket for both sending OSC and receiving replies.
Registers with /notify so SendReply messages are delivered.

Input mapping (SC bus = output_channels + input_index):
  Bus 6 = Scarlett input 1 = Window contact mic
  Bus 7 = Scarlett input 2 = CypherClaw contact mic
  Bus 8 = Scarlett input 3 = Theramini L
  Bus 9 = Scarlett input 4 = Theramini R
"""
import collections, json, os, socket, struct, time

ROOM_STATE = "/tmp/room_activity.json"
INPUT_STATE = "/tmp/input_levels.json"
SC_ADDR = ("127.0.0.1", 57110)
SYNTH_DEF = "/home/user/cypherclaw/tools/senseweave/synthesis/synthdefs/sw_input_meter.scsyndef"

history = collections.defaultdict(lambda: collections.deque(maxlen=30))
levels = {}

def osc_string(s):
    s = s.encode() + b"\x00"
    s += b"\x00" * ((4 - len(s) % 4) % 4)
    return s

def osc_msg(addr, args):
    msg = osc_string(addr)
    typetag = ","
    argdata = b""
    for a in args:
        if isinstance(a, int):
            typetag += "i"; argdata += struct.pack(">i", a)
        elif isinstance(a, float):
            typetag += "f"; argdata += struct.pack(">f", a)
        elif isinstance(a, str):
            typetag += "s"; argdata += osc_string(a)
        elif isinstance(a, bytes):
            typetag += "b"; argdata += struct.pack(">i", len(a)) + a + b"\x00" * ((4 - len(a) % 4) % 4)
    msg += osc_string(typetag) + argdata
    return msg

def parse_input_level(data):
    """Parse /input_level SendReply: addr, typetag, node_id, reply_id, bus, amp."""
    try:
        end = data.index(b"\x00")
        addr = data[:end].decode()
        if addr != "/input_level":
            return None, None
        # Skip past address + typetag
        i = end + 1
        i += (4 - i % 4) % 4  # align
        # typetag
        tt_end = data.index(b"\x00", i)
        i = tt_end + 1
        i += (4 - i % 4) % 4
        # args: node_id(i), reply_id(i), bus(f), amp(f)
        if i + 16 <= len(data):
            node_id = struct.unpack(">i", data[i:i+4])[0]
            reply_id = struct.unpack(">i", data[i+4:i+8])[0]
            bus = struct.unpack(">f", data[i+8:i+12])[0]
            amp = struct.unpack(">f", data[i+12:i+16])[0]
            return int(bus), amp
    except Exception:
        pass
    return None, None

def median(vals):
    s = sorted(vals)
    return s[len(s) // 2] if s else 0

def write_state(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)

def run():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.1)
    print(f"Input monitor on port {sock.getsockname()[1]}", flush=True)

    send = lambda addr, args: sock.sendto(osc_msg(addr, args), SC_ADDR)

    # Load synthdef
    if os.path.exists(SYNTH_DEF):
        send("/d_recv", [open(SYNTH_DEF, "rb").read()])
        time.sleep(0.3)

    # Register for notifications
    send("/notify", [1])
    time.sleep(0.2)
    # Drain response
    try:
        sock.recvfrom(4096)
    except socket.timeout:
        pass

    # Create meters on inputs 1-4 (SC buses 6-9)
    for i in range(4):
        send("/s_new", ["sw_input_meter", 98000 + i, 1, 0, "in_bus", 6 + i, "reply_id", 100 + i])
    print("Meters on buses 6-9", flush=True)

    last_write = 0
    while True:
        # Read all pending messages
        for _ in range(100):
            try:
                data, addr = sock.recvfrom(4096)
                bus, amp = parse_input_level(data)
                if bus is not None:
                    levels[bus] = amp
                    history[bus].append(amp)
            except socket.timeout:
                break

        now = time.time()
        if now - last_write >= 0.5:
            last_write = now
            w = levels.get(6, 0)
            c_amp = levels.get(7, 0)
            t = levels.get(8, 0)

            w_trans = len(history[6]) > 3 and history[6][-1] > max(0.001, median(list(history[6])[:-1])) * 3
            c_trans = len(history[7]) > 3 and history[7][-1] > max(0.001, median(list(history[7])[:-1])) * 3

            activity = "quiet"
            if w > 0.01 or c_amp > 0.01:
                activity = "active"
            if w > 0.05 or c_amp > 0.05:
                activity = "loud"

            write_state(ROOM_STATE, {
                "timestamp": now,
                "activity_level": activity,
                "window_mic_amp": w,
                "cypherclaw_mic_amp": c_amp,
                "recent_transient": w_trans or c_trans,
                "window_transient": w_trans,
                "claw_transient": c_trans,
            })
            write_state(INPUT_STATE, {
                "timestamp": now,
                "window_contact": w,
                "cypherclaw_contact": c_amp,
                "theramini": t,
                "levels": {str(k): v for k, v in levels.items()},
            })

if __name__ == "__main__":
    run()
