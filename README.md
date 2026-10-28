# ownervisor

The debug shell of an iOS guest: **ownervisor**, a small service manager for the owner's services outside launchd, the
**shell** it serves -- applebox, dropbear, zsh, debugserver, libimobiledevice -- and its **built-in services** (ssh,
serial-shell). launchd only runs the labels of its signed job set, so every service of the owner would otherwise need an
unused label of its own; ownervisor is started once at boot as root and supervises the rest.

It is the debug shell of [UniXNU-droidvm](https://github.com/Droid-VM/UniXNU-droidvm), the iPadOS guest of DroidVM,
whose kernel starts ownervisor at boot (`owner-service-manager=1`) and whose Data seed carries what `build.py` makes. The
binaries run on any iOS 17 device that trusts their CDHashes; the paths default to UniXNU-droidvm's
`/private/var/ngpu` (the guest's writable Data volume).

| Part | What | Source |
| --- | --- | --- |
| manager | `ownervisor`, `ownerctl` (its client), `ownertest` (proof that an owner-trusted binary spawns another) | `manager/` |
| applebox | Apple's command-line tools (shell_cmds) as one multicall binary | [Droid-VM/applebox](https://github.com/Droid-VM/applebox), pinned in `build.py` |
| dropbear | the ssh server: keys only, zsh as the login shell, keys and host keys in `/private/var/ngpu/ssh` | `tools/dropbear.py` (dropbear 2022.83) |
| zsh | Apple's zsh 5.9, static modules | `tools/zsh.py` (apple-oss-distributions/zsh) |
| debugserver | LLDB's remote debug stub for `process connect` | `tools/debugserver.py` (llvm-project 19.1.7) |
| libimobiledevice | its 18 tools, iproxy, inetcat and plistutil as one multicall binary, with a link per tool | `tools/libimobiledevice.py` |

applebox and debugserver are signed with `entitlements/debug.plist` (the 109-key debugger and lockdownd set); the
others with no-container (and libimobiledevice the network entitlements).

## Built-in services

`services/NAME.json` are the definitions ownervisor reads from `services.d/`; `services/autostart` lists the ones it
starts at boot.

| Service | Runs | At boot |
| --- | --- | --- |
| `dropbear` | the ssh server on port 2222 | yes |
| `selftest` | `ownertest boot` | yes |
| `serial-shell` | a zsh login shell on `/dev/console` | no: it needs a kernel console on a UART the host can reach, which UniXNU-droidvm's is not yet |

## Build

On a Mac with Xcode (the iphoneos and macOS SDKs):

```sh
python3 build.py out                       # every part
python3 build.py out --only zsh,dropbear   # those again, the others as an earlier build left them
```

`out/bin` holds the binaries and links as they go into `/private/var/ngpu/bin`, `out/services.d` and `out/enabled` the
services as they go under ownervisor's root, and `out/debug-shell.json` every binary's CDHash, which the device has to
trust (an owner trust cache; AMFI checks the hash at exec).

## ownervisor

Under `$OWNERVISOR_ROOT` (default `/private/var/ngpu/ownervisor`):

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
cache lists) and not by a path. Started from the kernel during launchd's exec, ownervisor has no bootstrap port at first;
it waits (up to about 90 s) for the platform to give its task launchd's, so the services it spawns can reach launchd, then
starts them either way.

## License

`manager/`: MIT (LICENSE). The build scripts (`build.py`, `tools/`) come from UniXNU-droidvm and keep its license,
BSD-2-Clause-Patent (LICENSE.BSD-2-Clause-Patent). The tools keep the licenses of their own sources, which are downloaded
at build time and are not part of this repository.
