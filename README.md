# ownervisor

A small service manager for the owner debug services of an iOS guest -- an ssh server, a GPU probe, a console
shell -- that run outside launchd. launchd only runs the labels of its signed job set, so each service of the owner
would otherwise need an unused label of its own. ownervisor is started once at boot as root and supervises the rest.

It is the service manager of [UniXNU-droidvm](https://github.com/Droid-VM/UniXNU-droidvm), the iPadOS guest of
DroidVM, where the kernel's launch-policy hook spawns it (`owner-service-manager=1`). Nothing in it is specific to that
guest beyond its default root directory.

| Binary | Use |
| --- | --- |
| `ownervisor` | the manager: starts the enabled services, restarts kept-alive ones, serves the control sockets and the spool |
| `ownerctl` | its client: `ownerctl list`, `ownerctl start NAME`, `ownerctl add NAME --def JSON`, `ownerctl --app ...` |
| `ownertest` | a child that proves an owner-trusted binary can spawn another under AMFI (the `selftest` service) |

## Layout

Under `$OWNERVISOR_ROOT` (default `/private/var/ngpu/ownervisor`, the writable Data volume of UniXNU-droidvm):

| Path | Meaning |
| --- | --- |
| `services.d/NAME.json` | a service: `{"exec": [...], "uid": 0, "keepalive": true, "throttle": 5, "env": {...}}` |
| `enabled/NAME` | present: the service starts at boot |
| `run/ctl.sock` | the control socket, root only: every verb |
| `run/app.sock` | the socket for apps (root:mobile 0660): only peers whose CDHash is in `auth/app-clients`, only the service verbs |
| `control/ID.req`, `ID.rep` | the file spool, for a host that writes into the guest's file system |
| `log/NAME.log`, `state/status.json` | each service's output, the live table |

Verbs (line-JSON on a socket, or a `.req` file): `list`, `status`, `start`, `stop`, `restart`, `enable`, `disable`, `add`,
`remove`, `reload`, `run`. `app.sock` serves `list` through `disable` only: an app is checked by the CDHash of its main
executable through the peer's audit token, not by an entitlement (AMFI grants any entitlement to any binary the trust
cache lists) and not by a path.

Started from the kernel during launchd's exec, ownervisor has no bootstrap port at first; it waits (up to about 90 s)
for the platform to give its task launchd's (UniXNU-droidvm's kernel copies it once launchd is up), so the services it
spawns can reach launchd, then starts them either way.

## Build

On a Mac with Xcode:

```sh
python3 build.py out                         # out/{ownervisor,ownerctl,ownertest}, out/ownervisor.json
python3 build.py out --entitlements ents.plist
```

The binaries are signed ad hoc with 4 KiB pages; `ownervisor.json` records their CDHashes, which the device has to trust
(an owner trust cache), as it has to trust every binary a service runs.

## License

MIT (LICENSE).
