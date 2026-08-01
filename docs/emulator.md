# Emulator setup

How to create an Android emulator for this build, and what to do about its two
known problems: a black screen and unreliable sound. Neither is a server fault.

If you would rather test on a real phone or tablet, see
[Install on a physical device](device-setup.md) instead.

## Create the emulator

In Android Studio, open **Device Manager**. From the welcome screen, choose
**More Actions → Virtual Device Manager**. With a project open, choose **View →
Tool Windows → Device Manager**. These are the two official ways to open it; see
[Create and manage virtual devices](https://developer.android.com/studio/run/managing-avds).

Choose **Create device**, select a phone profile, choose a system image, and
start the new device. Use a fresh emulator profile for this test build when
possible.

### Choose an Android 14 image with translated ABI support

This is the current recommendation and it matters more than the phone profile.

The app is built for `arm64-v8a` and `armeabi-v7a` only, so on an x86 computer
the emulator has to translate ARM code, and which translator it uses depends on
the Android version: Android 11 through 13 use the older **Houdini**, Android 14
uses **Berberis**, which handles this Unity build and its audio noticeably
better. Reported by a tester and confirmed by another, whose emulator audio had
previously cut out within a minute and then ran uninterrupted on Android 14.

In **Device Manager → Create device**, pick a phone profile, then choose a system
image whose name includes **Translated ABI** (for example *Android 14 ·
arm64-v8a · Translated ABI*).

If installing fails with `INSTALL_FAILED_NO_MATCHING_ABIS: Failed to extract
native libraries, res=-113`, the image has no ARM translation. That is the whole
cause: pick a Translated ABI image and install again. Nothing is wrong with the
APK or the signing.

### Images to avoid

- **Android 16 images using a 16 KB page size.** The original APK is not
  compatible with that emulator configuration.
- Some newer Android API levels have caused the original APK to crash when
  opening game areas **on emulator system images**. This has not been reproduced
  on physical hardware: a Samsung tablet running a current Android release runs
  the same build correctly. Treat it as an emulator image limitation rather than
  a general Android version limit, and not as a local-server response.

Older reports completed the verified path through Chapter 2-1 on a **Pixel 6 with
Android 12**, so that image still works for play, but its audio is unreliable and
it is no longer the suggested starting point.

## Start the emulator with `-gpu swangle`, especially on macOS

The emulator's default graphics backend can leave the app on a **permanently
black screen**. The app has not crashed and the server is not at fault: it
launches, talks to the server, and downloads resources normally, but the
emulator's OpenGL translator cannot complete the framebuffer Unity asks for, so
nothing is ever drawn. On macOS the default `-gpu auto` selects the Apple Metal
GLES translator, which fails this way.

Android Studio's Device Manager gives no way to pass this flag, so start the
emulator from a terminal instead:

```sh
"$HOME/Library/Android/sdk/emulator/emulator" -avd YOUR_AVD_NAME -gpu swangle
```

On Windows and Linux use the `emulator` binary in your own SDK directory. List
your AVD names with `emulator -list-avds`. `swangle` selects ANGLE with
SwiftShader, which renders correctly.

To confirm this is the problem rather than guess, count the framebuffer errors
while the black screen is showing:

```sh
adb logcat -d | grep -c 0x506
```

```powershell
(adb logcat -d | Select-String "0x506").Count
```

Thousands of `0x506` errors from `emuglGLESv2_enc` mean the graphics backend, not
the server. Zero means look elsewhere. This is worth checking early, because the
server log keeps showing successful `200` responses throughout, so the failure
looks like a server problem and is not one.

## Find the emulator serial

Wait until the emulator has finished booting, then confirm that `adb` can see it
and print its serial number:

```sh
adb devices -l
```

The output should contain a line like `emulator-5570 device ...`. The first
column (`emulator-5570`) is the serial needed by the setup command. If it says
`offline` or `unauthorized`, wait for boot to finish and run the command again.

If you have other emulators or Android devices connected, use the intended serial
explicitly:

```sh
export ANDROID_SERIAL=emulator-5556
adb shell getprop ro.product.model
```

Replace `emulator-5556` with your serial. `ANDROID_SERIAL` applies only to the
current terminal, so it will not affect your other projects.

## Sound on the emulator

**Start with an Android 14 Translated ABI image; it fixes the worst of this.**
Emulator audio going silent after a minute or two has been traced to the older
**Houdini** ARM translator used by Android 11 through 13. Android 14's
**Berberis** does not show it: a tester whose audio had reliably died within a
minute ran five minutes uninterrupted after switching. See [Choose an Android 14
image](#choose-an-android-14-image-with-translated-abi-support).

Neither problem below is a server problem: the local resource set delivers every
sound and music file the client asks for, and the same build plays audio
continuously on physical hardware. If you are on an older image and sound matters
to you, test on a real phone or tablet.

### No sound at all: audio output is switched off

Many emulators start this way. Android Studio does not always write
`hw.audioOutput` into a new device's configuration, so whether you get any sound
at all depends on when and how the device was created. Check the file directly:

```text
~/.android/avd/YOUR_AVD.avd/config.ini                      macOS and Linux
%USERPROFILE%\.android\avd\YOUR_AVD.avd\config.ini          Windows
```

You can also reach it from **Device Manager → the device's ⋮ menu → Show on
Disk**. Both of these lines must be present and set to `yes`; add them if they
are missing:

```ini
hw.audioInput=yes
hw.audioOutput=yes
```

Save the file, then **cold boot** the emulator: **Device Manager → the device's ⋮
menu → Cold Boot Now**, or from a terminal:

```sh
"$HOME/Library/Android/sdk/emulator/emulator" -avd YOUR_AVD_NAME -gpu swangle -no-snapshot-load
```

On Windows and Linux use the `emulator` binary in your own SDK directory, as in
the graphics step above.

**Cold booting is the part that is easy to miss.** An ordinary restart uses quick
boot, which restores a saved snapshot of the device and can bring the old, silent
audio device back with it, so the edit looks as though it did nothing.

### Sound starts, then goes silent after several seconds

This happens even while idling at the title screen. Cold booting, increasing the
AVD from four to six cores, and switching away from `swangle` did not change this
cutoff in tester runs. **Do not spend time repeating those changes for this
particular symptom.**

Paired Android audio-state captures show that the app's one audio track remains
active, routed to the speaker, unmuted, and supplied with data after the sound
disappears. Both the client track and Android output continue advancing in real
time with zero underruns. The signal delivered to Android changes from normal
varying program audio to a fixed-power signal. That rules out the earlier
CPU-starvation and Android audio-stream-stall explanation; the failure is at the
old Unity 2017/FMOD producer boundary before Android's mixer.

The failing capture came from an x86_64 AVD translating this ARM-only client.
That translation path and the app's 24 kHz track are leads, not yet confirmed
causes: one tester's Pixel 4 profile kept audio working but its exact system image
and ABI have not been compared. The only reliable workaround currently
demonstrated is a physical phone or tablet.

### Helping diagnose it

If you have one emulator profile where audio works and another where it fails,
capture the discriminator from both:

```sh
adb shell getprop ro.product.cpu.abilist
adb shell getprop ro.dalvik.vm.native.bridge
adb shell getprop ro.build.fingerprint
adb shell dumpsys package com.mistwalkercorp.guardians > terra-battle-package.txt
adb shell dumpsys media.audio_flinger > audio-flinger.txt
```

In PowerShell, the same commands work; use `Out-File` to make the encoding
explicit:

```powershell
adb shell getprop ro.product.cpu.abilist
adb shell getprop ro.dalvik.vm.native.bridge
adb shell getprop ro.build.fingerprint
adb shell dumpsys package com.mistwalkercorp.guardians |
  Out-File -Encoding utf8 terra-battle-package.txt
adb shell dumpsys media.audio_flinger |
  Out-File -Encoding utf8 audio-flinger.txt
```

## Next

Return to the [README](../README.md#5-run-the-setup-command) with your emulator
serial.
