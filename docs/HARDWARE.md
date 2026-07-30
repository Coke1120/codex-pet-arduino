# Hardware, safe wiring, and enclosure

This guide covers the verified hardware variant used during project bring-up:

- Arduino Uno R3 / ATmega328P
- 1.8-inch 128 × 160 SPI TFT
- PCB silk: `Driver IC: ST7735S`
- TFT pin order: `BLK CS DC RST SDA SCL VDD GND`

The TFT photographs show no regulator in the visible `VDD` path and no level-shifting components on `CS`, `DC`, `RST`, `SDA`, or `SCL`. The small `R1/R2/R3/Q1` group appears to serve the backlight, not the five logic lines. Treat this module as 3.3V-only unless the exact seller schematic proves otherwise.

## Minimal bill of materials

If you already have the Uno, TFT, USB cable, wire, soldering supplies, and prototyping jumpers, the minimal additional purchase is:

- 1 × TXS0108E 8-channel level-shifter module, preferably with downward-soldered 2.54 mm pins
- 2.54 mm female header strips, enough to socket the TXS0108E and TFT
- 1 × 2.54 mm single-sided tinned perfboard, approximately 5 × 7 cm

This is enough for initial operation using the Uno's 3.3V output. That rail is limited to about 50 mA, so measure or observe the finished load. Add a dedicated regulated 3.3V supply if the rail sags, the Uno resets, the TFT flickers, the backlight is unstable, or any component becomes unusually warm.

Useful but optional final-build parts include 26–28 AWG colour-coded wire, heat-shrink tubing, nylon standoffs and screws, strain relief, 100 nF and 10 µF decoupling capacitors, and removable connectors.

## TXS0108E wiring

The low-voltage side is **A/VCCA**. The Uno side is **B/VCCB**.

### Power

```text
Uno 3.3V ──┬── TXS0108E VCCA
            ├── TXS0108E OE
            ├── TFT VDD
            └── TFT BLK (initial test)

Uno 5V ─────── TXS0108E VCCB

Uno GND ───┬── TXS0108E GND
            └── TFT GND
```

All grounds must be common. `VCCA` must not exceed `VCCB`. Do not reverse the A and B supplies. Never insert or remove wiring while powered.

### Signals

```text
Uno D10 ── B1 | A1 ── TFT CS
Uno D8  ── B2 | A2 ── TFT DC
Uno D9  ── B3 | A3 ── TFT RST
Uno D11 ── B4 | A4 ── TFT SDA (MOSI)
Uno D13 ── B5 | A5 ── TFT SCL (SCK)
```

Channels 6–8 remain unused. Keep wires short, particularly `SDA` and `SCL`. The project starts at an 8 MHz SPI clock; reduce `SPI_FREQUENCY` in `config/User_Setup.h` to 4 MHz if long prototype wiring produces noise.

## Safe bring-up checklist

1. Leave the TFT disconnected.
2. Compile and upload the sketch to the port that `arduino-cli board list` identifies as Arduino UNO.
3. Verify `ping`, `status`, `running`, `waiting`, `review`, and `idle` over Serial.
4. Disconnect USB power.
5. Wire the common ground, TXS0108E supply rails, and `OE`.
6. Wire all five B-to-A translated signals; check `DC → D8` and `RST → D9` carefully.
7. Connect TFT `VDD` and `BLK` to the 3.3V rail.
8. Inspect every connection for shorts and reversed A/B supplies before reconnecting USB.
9. Power briefly. Stop immediately for heat, smell, resets, flicker, or an unstable USB connection.
10. Test all four display states, orientation, RGB/BGR order, offsets, and continuous operation.

A white illuminated panel only confirms that the backlight is on. It does not confirm controller initialization or correct SPI wiring.

## Perfboard assembly

Prototype on a breadboard first. Once the display is electrically and visually stable:

1. Plan separate 5V, 3.3V, and GND buses on the perfboard.
2. Socket the TXS0108E and TFT with female headers rather than soldering serviceable modules permanently.
3. Keep translated SPI traces short and colour-coded.
4. Add strain relief to cables and use nylon standoffs so no PCB underside contacts the enclosure.
5. Check continuity and absence of shorts with power removed.
6. Repeat the complete Serial and visual test, followed by a continuous run test.

Do not use a perfboard as a substitute for level conversion, and do not use a resistor divider as a regulated TFT power supply.

## Enclosure

Choose or design the case only after the perfboard assembly passes testing. Measure:

- TFT PCB width, height, thickness, mounting-hole spacing, and active-area offset
- final perfboard footprint and component height
- Uno footprint, standoffs, and reset-button position
- USB-B plug insertion and cable-bend clearance

A practical enclosure has a TFT bezel, side USB opening, reset access, ventilation, nylon mounting posts, and a removable screwed back. Avoid permanently burying boards in hot glue; use it only sparingly for wire strain relief.

Suggested stack:

```text
front:  ST7735S and display bezel
middle: perfboard, TXS0108E, and wiring
rear:   Arduino Uno with USB and reset access
```

## Verified boundary

The current reference firmware has been compiled for `arduino:avr:uno`, uploaded to an identified Arduino Uno R3, and exercised over Serial for all four states plus `ping`. The photographed ST7735S now displays the converted custom-pet frames with the expected orientation, colours, compact status bar, and continuous two-frame state loops. The current physical prototype uses the TXS0108E wiring above.

A permanent perfboard/enclosure build still needs its own continuity check, current/voltage measurement, strain relief, and continuous-run verification. Different TFT breakout revisions or user-supplied pet atlases may require different tab, colour-order, electrical, or asset-conversion settings.