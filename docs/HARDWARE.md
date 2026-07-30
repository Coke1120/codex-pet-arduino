# Hardware, safe wiring, and enclosure

This guide covers the hardware variant used during project bring-up:

- Arduino Uno R3 / ATmega328P
- 1.8-inch 128 × 160 SPI TFT
- PCB silk: `Driver IC: ST7735S`
- TFT pin order: `BLK CS DC RST SDA SCL VDD GND`

The exact breakout matters more than the controller name. The current photographed module has been user-confirmed to accept 5V at `VDD` and direct Uno GPIO; its verified backlight connection is `BLK → 3.3V`. A generic bare ST7735S controller is normally 3.3V logic, so do not assume another visually similar breakout accepts 5V power or 5V GPIO.

## Minimal bill of materials

For the verified 5V-compatible module:

- Arduino Uno R3
- 1.8-inch ST7735S TFT module
- USB cable
- short Dupont/breadboard wires
- 2.54 mm headers
- optional 2.54 mm perfboard, approximately 5 × 7 cm, for the permanent build

A `TXS0108E` is **not required** for the verified direct-wired module. Use a suitable 5V-to-3.3V translator only when another TFT breakout's logic inputs are not confirmed 5V-compatible.

Useful final-build parts include 26–28 AWG colour-coded wire, heat-shrink tubing, nylon standoffs and screws, strain relief, 100 nF and 10 µF decoupling capacitors, and removable connectors.

## Direct wiring for the verified module

### Power

```text
Uno 5V  ───── TFT VDD
Uno 3.3V ──── TFT BLK
Uno GND ───── TFT GND
```

### Signals

```text
Uno D10 ── TFT CS
Uno D8  ── TFT DC
Uno D9  ── TFT RST
Uno D11 ── TFT SDA (MOSI)
Uno D13 ── TFT SCL (SCK)
```

Keep `SDA` and `SCL` short. The project starts at an 8 MHz SPI clock; reduce `SPI_FREQUENCY` in `config/User_Setup.h` to 4 MHz if long prototype wiring produces noise.

## When a level translator is required

Use a translator such as a push-pull-capable `TXS0108E`-class module when the seller documentation or electrical inspection does **not** establish 5V-compatible TFT logic inputs.

For that optional path:

```text
Uno 3.3V ──┬── translator VCCA
            ├── translator OE
            ├── TFT VDD
            └── TFT BLK (only if appropriate for that module)

Uno 5V ─────── translator VCCB
Uno GND ───┬── translator GND
            └── TFT GND

Uno D10 ── B1 | A1 ── TFT CS
Uno D8  ── B2 | A2 ── TFT DC
Uno D9  ── B3 | A3 ── TFT RST
Uno D11 ── B4 | A4 ── TFT SDA
Uno D13 ── B5 | A5 ── TFT SCL
```

All grounds must be common. Never insert or remove wiring while powered. The Uno's 3.3V rail is limited, so use a properly sized regulated 3.3V supply if the TFT/backlight load causes voltage sag, resets, flicker, or heating.

## Safe bring-up checklist

1. Confirm the exact TFT breakout's power, logic-level, and backlight requirements.
2. Leave the TFT disconnected; compile and upload to the port that `arduino-cli board list` identifies as Arduino UNO.
3. Verify `ping`, `status`, `running`, `waiting`, `review`, and `idle` over Serial.
4. Disconnect USB power.
5. Wire common ground and power for the chosen direct or translated path.
6. Wire `CS`, `DC`, `RST`, `SDA/MOSI`, and `SCL/SCK`; check `DC → D8` and `RST → D9` carefully.
7. Inspect every connection for shorts before reconnecting USB.
8. Power briefly. Stop immediately for heat, smell, resets, flicker, or an unstable USB connection.
9. Test all four display states, orientation, RGB/BGR order, offsets, and continuous operation.

A white illuminated panel only confirms that the backlight is on. It does not confirm controller initialization or correct SPI wiring.

## Perfboard assembly

Prototype on a breadboard first. Once the display is electrically and visually stable:

1. Plan the required power and GND buses for the exact module.
2. Socket the TFT and any optional translator with female headers rather than soldering serviceable modules permanently.
3. Keep SPI traces short and colour-coded.
4. Add strain relief and nylon standoffs so no PCB underside contacts the enclosure.
5. Check continuity and absence of shorts with power removed.
6. Repeat the complete Serial and visual test, followed by a continuous run test.

A perfboard distributes and mounts components; it does not provide voltage regulation or level conversion by itself.

## Enclosure

Choose or design the case only after the final assembly passes testing. Measure:

- TFT PCB width, height, thickness, mounting-hole spacing, and active-area offset
- final perfboard footprint and component height
- Uno footprint, standoffs, and reset-button position
- USB-B plug insertion and cable-bend clearance

A practical enclosure has a TFT bezel, side USB opening, reset access, ventilation, nylon mounting posts, and a removable screwed back. Avoid permanently burying boards in hot glue; use it only sparingly for wire strain relief.

Suggested stack:

```text
front:  ST7735S and display bezel
middle: optional perfboard and short wiring
rear:   Arduino Uno with USB and reset access
```

## Verified boundary

The firmware has been compiled for `arduino:avr:uno`, uploaded to an identified Arduino Uno R3, and exercised over Serial for all four states plus `ping`. The user-confirmed 5V-compatible ST7735S module displays the converted custom-pet frames with the expected orientation, colours, compact status bar, and continuous two-frame state loops.

The direct-wiring instructions apply only to that confirmed breakout: `VDD → 5V`, `BLK → 3.3V`, and the five SPI/control signals directly from Uno GPIO. A permanent perfboard/enclosure build still needs its own continuity check, current/voltage measurement, strain relief, and continuous-run verification. Other TFT breakout revisions may require level translation, different power/backlight wiring, or different tab/colour-order settings.
