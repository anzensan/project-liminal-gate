# Install on a physical phone or tablet

> This page is only for the **separate-computer server** layout. If the server
> should start inside the APK, use [Run the server inside the Android APK](on-device-setup.md).
> In that layout `127.0.0.1:8002` is deliberately correct and no LAN address is
> configured.

The emulator path reaches the server through `10.0.2.2`, an alias that only
exists inside an Android emulator. A real device has to be told this machine's
own address on your network instead. **Everything else — the file layout, the
signing key, the server itself — is unchanged.**

A physical device is the better choice if you care about graphics or sound; both
are unreliable under emulation.

This is still a private, local-network setup. Do not port-forward the server,
expose it to the internet, or use it as a hosted service.

## A. Prepare the device

Enable **Developer options** (Settings → About → tap **Build number** seven
times), then turn on **USB debugging** inside Developer options. Connect the
device by USB, and accept the **Allow USB debugging** prompt that appears on the
device screen. Then confirm your computer can see it:

```sh
adb devices -l
```

A physical device shows a hardware serial rather than an `emulator-NNNN` name,
for example `R52T80ABCDE   device  ...`. If it says `unauthorized`, the on-device
prompt has not been accepted yet. If nothing is listed, try a different cable —
charge-only USB cables are a common cause.

## B. Find this machine's network address

```sh
ipconfig getifaddr en0          # macOS, Wi-Fi
hostname -I | awk '{print $1}'  # Linux
```

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -ne 'WellKnown' }
```

You want a private LAN address, normally starting `192.168.`, `10.`, or
`172.16.`–`172.31.`. The phone or tablet must be on **the same network**: the
same router, and not on a guest or client-isolated Wi-Fi network, which blocks
devices from reaching each other.

## C. Keep that address from changing

The server address is compiled into the APK when it is patched. This is the
single most important thing to understand about the device path:

> **If this machine's address changes, the installed app stops working.** It will
> not find the new address by itself. You have to rerun setup and reinstall the
> APK.

Most home routers hand out addresses by DHCP and can change them after a reboot
or a lease expiry. Pick one of these, best first:

1. **Reserve the address on your router (recommended).** In the router's admin
   page, find DHCP reservations (sometimes "static lease" or "bind IP to MAC")
   and reserve the current address for this machine's MAC address. The machine
   keeps using DHCP, so nothing changes locally, but the address stops moving.
2. **Configure a static address on this machine.** Set it manually in your OS
   network settings, choosing an address **outside** the router's DHCP range so
   nothing else is handed the same one.
3. **Do nothing and accept the breakage.** Fine for a single afternoon of
   testing. When the address changes, rerun the setup command with the new one;
   your saved game data in `user-data/` is not affected.

## D. Choose a port with at most four digits

The redirect works by overwriting text already inside the APK, and the
replacement can never be longer than what it replaces. That leaves room for **27
characters total**, counting `http://`, the address, the colon, and the port.

The longest possible IPv4 address is 15 characters, so:

```text
http://192.168.100.100:8696     27 characters  works
http://192.168.100.100:18696    28 characters  rejected
```

Any address on your network fits **as long as the port has four digits or
fewer**. Setup checks this before it touches the APK and tells you the measured
length if it does not fit. Host *names* are usually too long and are not
recommended in any case, because Android does not reliably resolve local `.local`
names.

## E. Run setup against the device

Use the address from step B and the serial from step A:

```sh
python3 -m liminal_gate.tester_setup \
  --device-host 192.168.1.10 \
  --device R52T80ABCDE \
  --port 8696
```

Setup prints the address it baked in, so you can confirm it:

```text
This build reaches the server at http://192.168.1.10:8696 and only that address.
```

`--device` may be omitted when only one device is connected. It accepts an
emulator serial equally well, so `--emulator` still works as an older name for
the same option. To build the APK without installing, add `--prepare-only`.

Setup checks the target before it builds anything. If the selected serial does
not look like an emulator and `--device-host` was left at its emulator-only
default, it stops and says so, rather than producing an APK that cannot reach the
server. An emulator attached over TCP has an address-style serial and can trip
this too; pass `--device-host 10.0.2.2` explicitly in that case.

Addresses meaning "this same device" are also rejected: `localhost`, `127.0.0.1`,
and `0.0.0.0` name the phone or tablet itself from the client's point of view,
never the machine running the server. Pass only the address in `--device-host`,
and set the port with `--port`.

If a build from a different checkout is already installed, Android refuses to
replace it, because each checkout creates its own local test signing key. Add
`--replace-existing` to uninstall it first. That clears the app's local data on
the device, so it downloads resources again and starts a new local account; setup
never does it without being asked.

## F. First run over Wi-Fi

The first launch downloads the whole local resource set — roughly 11,800 files.
Over Wi-Fi this takes noticeably longer than the emulator path, which reads from
this machine's own loopback. Keep the device awake and plugged in, prefer a 5 GHz
network, and let the first run finish before judging performance.

If the app shows Network Error immediately at launch, check in this order: the two
devices are on the same network; the server is running and was started with
`--host 0.0.0.0`; the address printed by setup still matches the output of step B;
and any firewall on this machine allows inbound connections on your chosen port.

## Two players on one server

Two phones or tablets on your network can hold separate saves against one server,
because each device is routed by its own network address. See [Two players on one
server](saves.md#two-players-on-one-server).
