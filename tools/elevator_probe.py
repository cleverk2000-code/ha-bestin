#!/usr/bin/env python3
"""Standalone BESTIN elevator protocol diagnostic: EW11 CTRL / legacy iParkApp.

Does not alter Home Assistant. Sending requires a VERIFIED OWN-UNIT command
and a separate explicit confirmation. No scans, guesses, loops or retries.
"""
import argparse
import getpass
import http.cookiejar
import ipaddress
import json
import os
import re
import socket
import sys
import time
import urllib.parse
import urllib.request

CONFIRM = "SEND_VERIFIED_OWN_UNIT_CALL"
HTTP_ACK = "I_ACCEPT_HTTP_LOGIN"
USER_AGENT = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Version/4.0 Chrome/110.0.0.0 Mobile Safari/537.36")
HEADERS = {"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest",
           "Accept": "application/json, text/javascript, */*; q=0.01"}


def ew11_endpoint(host, port):
    ip = ipaddress.IPv4Address(host)
    if ip not in ipaddress.ip_network("192.168.0.0/16"):
        raise ValueError("EW11 must use your 192.168.x.x home LAN, not the 10.x building network")
    if not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    return host, port


def capture(a):
    if not 1 <= a.seconds <= 60:
        raise ValueError("Capture must be 1..60 seconds")
    with socket.create_connection(ew11_endpoint(a.host, a.port), timeout=4) as conn:
        conn.settimeout(0.5)
        end = time.monotonic() + a.seconds
        while time.monotonic() < end:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break
            print(time.strftime("%H:%M:%S"), data.hex(" ").upper(), flush=True)
    print("End capture: TCP chunks may be partial packets.")


def ew11_send(a):
    host, port = ew11_endpoint(a.host, a.port)
    raw = bytes.fromhex(a.hex.replace("0x", "").replace(",", " "))
    if not 5 <= len(raw) <= 256 or raw[0] != 0x02:
        raise ValueError("Require a real captured 02-prefixed complete frame (5..256 bytes)")
    print("Preview EW11:", raw.hex(" ").upper())
    if a.confirm != CONFIRM:
        print("DRY RUN — no bytes sent; use --confirm " + CONFIRM + " only after verification")
        return
    with socket.create_connection((host, port), timeout=4) as conn:
        conn.sendall(raw)
    print("One write completed; elevator dispatch has NOT been verified")


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, host):
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, url):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname != self.host:
            raise ValueError("Cross-host redirect denied")
        return super().redirect_request(req, fp, code, msg, headers, url)


def site_host(host):
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
        raise ValueError("Use hostname or IP only, no URL/path")
    addresses = [ipaddress.ip_address(item[4][0])
                 for item in socket.getaddrinfo(host, 80, type=socket.SOCK_STREAM)]
    if not addresses or not all(ip.is_global for ip in addresses):
        raise ValueError("Only configured public iParkApp site, never 10.x PC/GW")
    return host


def http_request(opener, host, path, params=None, form=None, ajax=False):
    url = "http://" + host + path
    if params is not None:
        url += "?" + urllib.parse.urlencode(params)
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    headers = HEADERS if ajax else {"User-Agent": USER_AGENT}
    with opener.open(urllib.request.Request(url, headers=headers, data=data),
                     timeout=10) as resp:
        return resp.read(4096)


def login(a):
    if a.ack_http != HTTP_ACK:
        raise ValueError("Legacy login transmits credentials in HTTP; opt in via --ack-http " + HTTP_ACK)
    host = site_host(a.site_host)
    user = os.environ.get("IPARK_USERNAME") or input("iPark username: ")
    password = os.environ.get("IPARK_PASSWORD") or getpass.getpass("iPark password: ")
    if not user or not password:
        raise ValueError("Username/password required")
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        SameHostRedirect(host))
    args = {"device": "WA", "login_ide": user, "login_pwd": password}
    args.update({"SITEWeather": a.weather, "SITELat": a.lat, "SITELng": a.lng})
    http_request(opener, host, "/webapp/login_chk_webapp.php", params=args)
    args = {"device": "WA", "login_ide": user, "login_pwd": password}
    args.update({"siteweather": a.weather, "sitelat": a.lat, "sitelng": a.lng})
    reply = json.loads(http_request(opener, host,
                                   "/webapp/data/getLoginWebApp.php",
                                   form=args, ajax=True))
    if reply.get("ret") != "success":
        raise ValueError("iPark login did not succeed; check site metadata")
    http_request(opener, host, "/webapp/index.php")
    print("iParkApp login OK; no elevator command sent")
    return opener, host


def ipark_send(a, opener, host):
    if not a.path:
        print("DRY RUN — no elevator command endpoint supplied")
        return
    if not re.fullmatch(r"/webapp/data/[A-Za-z0-9_-]+\.php", a.path):
        raise ValueError("Must use a verified /webapp/data/*.php endpoint")
    if re.search("login|auth|admin|delete|reset", a.path, re.I):
        raise ValueError("Administrative path forbidden")
    fields = {}
    for f in a.field:
        if "=" not in f:
            raise ValueError("Each --field must be KEY=VALUE")
        key, value = f.split("=", 1)
        fields[key] = value
    if "elevator" not in (a.path + json.dumps(fields)).lower():
        raise ValueError("Verified request must explicitly identify elevator")
    print("Preview iParkApp POST:", a.path, "field names:", sorted(fields))
    if a.confirm != CONFIRM:
        print("DRY RUN — no command sent; use --confirm " + CONFIRM + " only after verification")
        return
    body = http_request(opener, host, a.path, form=fields, ajax=True)
    print("One authenticated POST completed; response length:", len(body))
    print("This is NOT proof the elevator was called")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("ew11-capture", "ew11-send"):
        p = sub.add_parser(mode)
        p.add_argument("--host", required=True, help="EW11 IP in 192.168.x.x")
        p.add_argument("--port", type=int, default=8899)
        if mode == "ew11-capture":
            p.add_argument("--seconds", type=int, default=15)
        else:
            p.add_argument("--hex", required=True)
            p.add_argument("--confirm", default="")
    for mode in ("ipark-login", "ipark-send"):
        p = sub.add_parser(mode)
        p.add_argument("--site-host", required=True, help="Public site from existing iParkApp config")
        p.add_argument("--weather", default="")
        p.add_argument("--lat", default="")
        p.add_argument("--lng", default="")
        p.add_argument("--ack-http", default="")
        if mode == "ipark-send":
            p.add_argument("--path", default="")
            p.add_argument("--field", action="append", default=[])
            p.add_argument("--confirm", default="")
    a = parser.parse_args()
    try:
        if a.mode == "ew11-capture":
            capture(a)
        elif a.mode == "ew11-send":
            ew11_send(a)
        else:
            opener, host = login(a)
            if a.mode == "ipark-send":
                ipark_send(a, opener, host)
    except Exception as err:
        # Do not print HTTP exception URLs: legacy login embeds credentials in query.
        print("ERROR:", type(err).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
