# Elevator protocol diagnostics for BESTIN

This is a standalone optional diagnostic script. It does NOT automatically
integrate with HA or establish a proven elevator command. There are no
hard-coded commands or attempts to communicate with building-management IPs.

IMPORTANT: At the time of inspection, this repository's main branch is BESTIN
1.1.9 without an iParkApp client; the installed gateway may be from a DIFFERENT
fork. No existing climate, lighting or ventilation integration is modified.

## EW11 CTRL path

Read-only capture from an EW11 you own (example IP only; confirm actual host):

    python3 tools/elevator_probe.py ew11-capture --host 192.168.0.75 --port 8899 --seconds 15

Capture idle traffic, then traffic while calling from your own wallpad. Some
EW11 devices only allow one TCP client: concurrent capture can conflict with
the current HA integration. Stop/restart the affected connection if necessary.

Preview a COMPLETE, correctly parsed, confirmed own-unit frame only:

    python3 tools/elevator_probe.py ew11-send --host 192.168.0.75 --port 8899 --hex "02 ..."

Actual single transmission requires an additional argument:

    --confirm SEND_VERIFIED_OWN_UNIT_CALL

Never use fabricated frames. TCP receive chunks are not necessarily packet
boundaries. The blog example used a different RS-422 full-duplex bus; existing
EW11 CONTROL might not carry the elevator at all.

## iParkApp path (legacy)

Use the public complex-site host from your ACTIVE iParkApp integration, not
the pictured management PC 10.0.1.10, server 10.0.1.1, or GW 10.6.0.254.
Credentials are prompted, or set IPARK_USERNAME and IPARK_PASSWORD in a LOCAL
terminal environment. NEVER commit credentials or captures to a public repo.

The legacy app uses HTTP without encryption; GET landing also includes
credentials in URL parameters. This is the existing app's documented protocol.
Explicit opt-in is required to attempt login:

    python3 tools/elevator_probe.py ipark-login --site-host YOUR_PUBLIC_SITE --ack-http I_ACCEPT_HTTP_LOGIN

For some sites the same integration metadata must be passed with --weather,
--lat, --lng. This checks authenticated login and DOES NOT call an elevator.

An authenticated request needs the EXACT elevator endpoint and form fields
observed for your own apartment. This is a PREVIEW by default:

    python3 tools/elevator_probe.py ipark-send --site-host YOUR_PUBLIC_SITE --ack-http I_ACCEPT_HTTP_LOGIN --path /webapp/data/VERIFIED_ELEVATOR_HANDLER.php --field device=elevator

The path above is intentionally a placeholder, NOT a real endpoint. Append
--confirm SEND_VERIFIED_OWN_UNIT_CALL only after independently verifying both
the endpoint and payload from supported own-unit traffic. One POST only.
A successful HTTP response does not prove that a car arrived.

## Next evidence needed

1. Verify which 192.168.x.x EW11 is CONTROL and whether the current HA
   integration allows a concurrent TCP client.
2. Capture once at idle and once when the own-unit elevator call button is
   pressed; compare complete frames rather than chunks.
3. If no elevator traffic appears on CTRL, find the physically separate
   wallpad elevator/SMART line and confirm its electrical specification.
4. For iParkApp, identify a legitimate supported own-unit elevator action.
   Login alone provides no evidence of a usable elevator command endpoint.

No management infrastructure scanning, authentication bypass or repeated
elevator dispatch is implemented.
