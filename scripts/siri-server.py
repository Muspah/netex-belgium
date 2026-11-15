#!/usr/bin/env python3
"""Serve the GTFS.be SIRI stream over HTTP for OpenTripPlanner (siri-et-lite / siri-sx-lite).

Listens on the ZeroMQ feed, keeps the latest EstimatedVehicleJourney per journey and the
latest PtSituationElement per situation, and serves them as one ServiceDelivery:

    GET /siri/et   -> EstimatedTimetableDelivery
    GET /siri/sx   -> SituationExchangeDelivery

Usage: pip install pyzmq && python3 siri-server.py [port]   (default 8080)
"""
import gzip, sys, threading, time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NS = "http://www.siri.org.uk/siri"
S = "{%s}" % NS
ET.register_namespace("", NS)
TTL = 3 * 3600  # ponytail: drop by receive time; use last call time if stale trips ever matter

state = {"et": {}, "sx": {}}  # key -> (received_at, element)
lock = threading.Lock()


def ingest(xml):
    root = ET.fromstring(xml)
    now = time.time()
    with lock:
        for evj in root.iter(S + "EstimatedVehicleJourney"):
            key = (evj.findtext(f"{S}FramedVehicleJourneyRef/{S}DataFrameRef"),
                   evj.findtext(f"{S}FramedVehicleJourneyRef/{S}DatedVehicleJourneyRef")
                   or evj.findtext(S + "DatedVehicleJourneyRef"))
            state["et"][key] = (now, evj)
        for sit in root.iter(S + "PtSituationElement"):
            state["sx"][sit.findtext(S + "SituationNumber")] = (now, sit)
        for d in state.values():
            for k in [k for k, (t, _) in d.items() if now - t > TTL]:
                del d[k]


def render(kind):
    ts = datetime.now(timezone.utc).isoformat()
    siri = ET.Element(S + "Siri", version="2.1")
    sd = ET.SubElement(siri, S + "ServiceDelivery")
    ET.SubElement(sd, S + "ResponseTimestamp").text = ts
    ET.SubElement(sd, S + "ProducerRef").text = "gtfs.be"
    tag, frame = (("EstimatedTimetableDelivery", "EstimatedJourneyVersionFrame") if kind == "et"
                  else ("SituationExchangeDelivery", "Situations"))
    dl = ET.SubElement(sd, S + tag, version="2.1")
    ET.SubElement(dl, S + "ResponseTimestamp").text = ts
    fr = ET.SubElement(dl, S + frame)
    if kind == "et":
        ET.SubElement(fr, S + "RecordedAtTime").text = ts
    with lock:
        fr.extend(e for _, e in state[kind].values())
        return ET.tostring(siri, encoding="utf-8", xml_declaration=True)


def listen():
    import zmq
    sock = zmq.Context().socket(zmq.XSUB)
    sock.connect("tcp://sub.gtfs.be:9200")
    sock.send(b"\x01/SIRI")
    while True:
        frames = sock.recv_multipart()
        try:
            ingest(gzip.decompress(b"".join(frames[1:])))
        except Exception as e:  # one bad message must not kill the feed
            print("skip", frames[0], e, file=sys.stderr)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        kind = {"/siri/et": "et", "/siri/sx": "sx"}.get(self.path.split("?")[0])
        if not kind:
            return self.send_error(404)
        body = render(kind)
        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def selftest():
    msg = (f'<Siri xmlns="{NS}"><ServiceDelivery><EstimatedTimetableDelivery><EstimatedJourneyVersionFrame>'
           '<EstimatedVehicleJourney><FramedVehicleJourneyRef><DataFrameRef>D</DataFrameRef>'
           '<DatedVehicleJourneyRef>J</DatedVehicleJourneyRef></FramedVehicleJourneyRef><LineRef>%s</LineRef>'
           '</EstimatedVehicleJourney></EstimatedJourneyVersionFrame></EstimatedTimetableDelivery></ServiceDelivery></Siri>')
    ingest(msg % "old")
    ingest(msg % "new")
    out = ET.fromstring(render("et"))
    assert [e.text for e in out.iter(S + "LineRef")] == ["new"], "latest journey wins"
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    threading.Thread(target=listen, daemon=True).start()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"Serving on http://0.0.0.0:{port}/siri/et and /siri/sx")
    ThreadingHTTPServer(("", port), Handler).serve_forever()
